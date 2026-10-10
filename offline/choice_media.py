"""Pair exact existing source media without modifying a question's labels."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from offline.choice_builder import load, save, save_text, sha
from evaluation.t4_media import extract_frames
from tasks.offline_choice import public_instance, validate_item


def pair_assets(items, manifest_path, output, *, frames=True):
    manifest=load(manifest_path)
    by_id={r['media_asset_id']:r for r in manifest['requests'] if r.get('status')=='generated_structural_pass'}
    batch=Path(manifest['batch_root']);output=Path(output);paired=[];media={};gaps=[]
    cache={}
    for item in items:
        source=item['authoring']['construction_source'];trajectory=load(source['trajectory_path'])
        wanted=[]
        for turn in trajectory['turns'][:2]:
            turn_id='t'+str(turn['turn_id']).removeprefix('t')
            # T2 changes t2; only shared, unedited prefix assets may be reused.
            if item['task']=='T2' and turn_id!='t1':continue
            for ref in turn.get('media',[]):
                record=by_id.get(ref.get('media_asset_id'))
                if record is None:
                    gaps.append({'instance_id':item['instance_id'],'asset_id':ref.get('media_asset_id'),'reason':'exact_source_asset_missing'})
                    continue
                path=batch/record['video_file'];expected=record['video_sha256']
                if not path.is_file() or sha(path)!=expected:
                    raise ValueError('existing asset missing or hash changed')
                ids=['A:'+turn_id,'B:'+turn_id] if item['task']=='T2' else [turn_id]
                if expected not in cache:
                    asset={'path':str(path),'sha256':expected,'source_asset_id':record['media_asset_id'],
                           'human_review':'pending','response_neutral':record.get('response_neutral',False)}
                    if frames:
                        asset['frames']=extract_frames(path,output/'frames'/expected[:16],timestamps=(.25,1.25,2.25,3.25))
                    cache[expected]=asset
                wanted.append({**deepcopy(cache[expected]),'evidence_ids':ids})
        if not wanted:
            gaps.append({'instance_id':item['instance_id'],'reason':'no_matched_source_video'});continue
        text=deepcopy(item);video=deepcopy(item)
        pair_id=item['instance_id']
        for x in (text,video):
            x['metadata']['modality_pair_id']=pair_id
            x['authoring']['media_manifest']={'path':str(manifest_path),'sha256':sha(manifest_path)}
            x['authoring']['media_human_review']='pending'
        video['instance_id']+='-video';video['modality']='text+video'
        video['authoring']['matched_assets']=[{'sha256':a['sha256'],'evidence_ids':a['evidence_ids']} for a in wanted]
        if video['authoring']['answer']!=text['authoring']['answer'] or video['options']!=text['options']:
            raise ValueError('paired label drift')
        validate_item(text);validate_item(video)
        paired.extend([text,video]);media[video['instance_id']]=wanted
    for name,values in [('paired.items.jsonl',paired),('paired.public.jsonl',[public_instance(x) for x in paired])]:
        save_text(output/name,''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in values))
    save(output/'media.json',media)
    source_bytes=''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in items).encode()
    report={'input_item_count':len(items),'items_sha256':hashlib.sha256(source_bytes).hexdigest(),
            'logical_pairs':len(paired)//2,'variants':len(paired),'unique_videos':len(cache),
            'gaps':gaps,'human_media_review':'pending','frame_transport_limit':'sampled visual frames; no audio/prosody evaluation',
            'nonverbal_history_relation':'see each item authoring.nonverbal_history_relation; T2 reuses exact shared-prefix clip on both sides'}
    save(output/'pairing_report.json',report)
    return report
