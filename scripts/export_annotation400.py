"""Export the frozen English 400-item release and verified spoken-video bindings.

Only public projections and complete audio/video nodes enter blind materials.
Existing T4 packets and scores remain byte-equivalent at the object level.
"""
import argparse
import base64
import gzip
from collections import Counter
from copy import deepcopy
from difflib import SequenceMatcher
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import wave

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_annotation400 import OUT, load, save, sha, jsonl, QUOTAS
from scripts.prepare_human_gt_release import digest, packed
from offline.talking_head import public_nodes, canonical_sha
from tasks.offline_choice import public_instance, validate_item
from web.offline_review import item_digest
from web.annotation_sessions import private_evidence
from pipeline.localization import CJK
from scripts.screen_annotation400_local_av import (
    VERSION as LOCAL_SCREEN_VERSION, speech_normalized, critical_content_matches,
)


class LocalAssetError(ValueError):
    """A local render cannot yet be bound to the frozen public node."""


def _require(condition, reason):
    if not condition:
        raise LocalAssetError(reason)


def validate_local_asset(node, directory, *, expected_spec_sha256, root=ROOT):
    """Read-only validation of the complete local identity → speech → video chain.

    A request's own checksum is not sufficient: both the current bank projection
    and the frozen local job index must agree. No legacy segment metadata is
    invented for this independently rendered local pipeline.
    """
    directory, root = Path(directory), Path(root)
    names = ('request.json', 'speech.wav', 'speech.json', 'motion.mp4',
             'motion.json', 'video.mp4', 'video.json', 'audio_screen.json', 'video_screen.json',
             'lipsync_screen.json')
    for name in names:
        _require((directory / name).is_file(), 'missing_' + name)
    try:
        documents = {name: load(directory / name) for name in names if name.endswith('.json')}
        request = documents['request.json']
        spec = request.get('spec_sha256')
        _require(spec == expected_spec_sha256 and spec == canonical_sha(
            {k: v for k, v in request.items() if k != 'spec_sha256'}), 'request_spec_mismatch')
        for key in ('node_id', 'scenario_id', 'source_public_response',
                    'source_observable_expression', 'speaker', 'location'):
            _require(request.get(key) == node[key], 'public_input_mismatch_' + key)
        _require(request.get('speech_language') == 'en' and
                 request.get('method') == 'local_photorealistic_dubbing_v1', 'unsupported_local_method')
        identity = request['identity']
        _require(identity['scene'] == node['scenario_id'], 'identity_scene_mismatch')
        _require(identity['source_kind'] in ('existing_original_nonverbal_video', 'generated_english_anchor'),
                 'unsupported_identity_source')
        for key in ('source', 'identity'):
            path = root / identity[key + '_path']
            _require(path.is_file() and sha(path) == identity[key + '_sha256'], key + '_hash_mismatch')
        hashes = {name: sha(directory / name) for name in names}
        speech, motion, video = (documents[name + '.json'] for name in ('speech', 'motion', 'video'))
        for name, receipt, filename in (('speech', speech, 'speech.wav'),
                                         ('motion', motion, 'motion.mp4'), ('video', video, 'video.mp4')):
            _require(receipt.get('spec_sha256') == spec, name + '_spec_mismatch')
            _require(receipt.get('sha256') == hashes[filename], name + '_hash_mismatch')
        for name, receipt in (('speech', speech), ('video', video)):
            _require(receipt.get('spoken_text') == node['source_public_response'] and
                     receipt.get('speech_language') == 'en', name + '_public_line_mismatch')
            model_hash = receipt.get('model_sha256', '')
            _require(bool(receipt.get('model')) and len(model_hash) == 64 and
                     all(c in '0123456789abcdef' for c in model_hash), name + '_model_provenance_missing')
        _require(speech.get('voice') == request['voice'], 'speech_voice_mismatch')
        voice_hash = speech.get('voice_sha256', '')
        _require(len(voice_hash) == 64 and all(c in '0123456789abcdef' for c in voice_hash),
                 'speech_voice_provenance_missing')
        _require(motion.get('method') == 'LivePortrait_public_cues_v1', 'unsupported_motion_method')
        # Pronunciation repairs may adjust delivery speed, but must preserve the
        # frozen line, voice and spec; record their separate generation checksum.
        if 'generation_spec' in speech or 'generation_sha256' in speech:
            generation = speech['generation_spec']
            _require(canonical_sha(generation) == speech['generation_sha256'], 'speech_generation_hash_mismatch')
            for key in ('spec_sha256', 'model_sha256', 'voice_sha256', 'speed'):
                _require(generation[key] == speech[key], 'speech_generation_mismatch_' + key)
        for name, receipt in (('motion', motion), ('video', video)):
            _require(receipt.get('audio_sha256') == hashes['speech.wav'], name + '_audio_hash_mismatch')
            _require(receipt.get('identity_sha256') == identity['identity_sha256'], name + '_identity_hash_mismatch')
        _require(video.get('motion_sha256') == hashes['motion.mp4'], 'video_motion_hash_mismatch')
        for stage, filename in (('audio', 'speech.wav'), ('video', 'video.mp4')):
            screen = documents[stage + '_screen.json']
            _require(screen.get('version') == LOCAL_SCREEN_VERSION and
                     screen.get('node_id') == node['node_id'] and screen.get('spec_sha256') == spec and
                     screen.get('sha256') == hashes[filename] and
                     screen.get('expected') == node['source_public_response'], stage + '_screen_stale')
            transcript = screen.get('transcript', '')
            similarity = SequenceMatcher(None, speech_normalized(node['source_public_response']),
                                         speech_normalized(transcript), autojunk=False).ratio()
            _require(screen.get('machine_screen_passed') is True and screen.get('language') == 'en' and
                     screen.get('normalized_similarity', 0) >= .98 and similarity >= .98 and
                     abs(screen['normalized_similarity'] - similarity) <= .000051 and
                     screen.get('critical_content_match') is True and
                     critical_content_matches(node['source_public_response'], transcript), stage + '_screen_failed')
        lipsync = documents['lipsync_screen.json']
        _require(lipsync.get('version') == 'independent_syncnet_v1' and
                 lipsync.get('node_id') == node['node_id'] and
                 lipsync.get('spec_sha256') == spec and
                 lipsync.get('video_sha256') == hashes['video.mp4'], 'lipsync_screen_stale')
        _require(lipsync.get('machine_screen_passed') is True and
                 isinstance(lipsync.get('confidence'), (int, float)) and
                 math.isfinite(lipsync['confidence']) and lipsync['confidence'] >= 3 and
                 isinstance(lipsync.get('offset_frames'), int) and
                 abs(lipsync['offset_frames']) <= 2 and lipsync.get('frame_rate') == 25,
                 'lipsync_screen_failed')
        with wave.open(str(directory / 'speech.wav')) as audio:
            speech_duration = audio.getnframes() / audio.getframerate()
        _require(speech_duration > 0 and abs(speech_duration - speech['duration_seconds']) < .001,
                 'speech_duration_mismatch')
        _require(motion['fps'] > 0 and motion['frames'] == math.ceil(speech_duration * motion['fps']),
                 'motion_duration_mismatch')
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
            '-show_format', '-of', 'json', str(directory / 'video.mp4')], text=True))
        videos = [s for s in probe['streams'] if s['codec_type'] == 'video']
        audios = [s for s in probe['streams'] if s['codec_type'] == 'audio']
        _require(len(videos) == 1 and len(audios) == 1, 'video_requires_one_audio_and_video_stream')
        metadata = {'duration_seconds_actual': float(probe['format']['duration']),
                    'video_duration_seconds': float(videos[0]['duration']),
                    'audio_duration_seconds': float(audios[0]['duration']),
                    'audio_stream_count': len(audios), 'video_stream_count': len(videos)}
        for key, value in metadata.items():
            _require(abs(value - video['structural_metadata'][key]) < .001, 'video_metadata_mismatch_' + key)
        _require(metadata['duration_seconds_actual'] > 0 and
                 abs(metadata['video_duration_seconds'] - metadata['audio_duration_seconds']) < .15 and
                 abs(metadata['audio_duration_seconds'] - speech_duration) < .05 and
                 abs(metadata['video_duration_seconds'] - speech_duration) < .15, 'video_audio_duration_mismatch')
    except LocalAssetError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError,
            subprocess.SubprocessError, wave.Error) as exc:
        raise LocalAssetError('invalid_local_artifact: ' + str(exc)) from exc
    return {'path': str(directory / 'video.mp4'), 'sha256': hashes['video.mp4'],
            'source_asset_id': node['node_id'], 'media_kind': 'talking_head', 'response_neutral': False,
            'provider': 'local', 'method': request['method'], 'spec_sha256': spec,
            'spoken_text': node['source_public_response'], 'source_public_response': node['source_public_response'],
            'source_observable_expression': deepcopy(node['source_observable_expression']),
            'speaker': deepcopy(node['speaker']), 'location': node['location'],
            'speech_language': 'en', 'audio_required': True, 'human_review': 'pending', 'speech_verified': False,
            'structural_metadata': metadata,
            'provenance': {'request_path': str(directory / 'request.json'), 'artifact_sha256': hashes,
                'identity': deepcopy(identity), 'speech': deepcopy(speech), 'motion': deepcopy(motion),
                'lipsync': deepcopy(video),
                'screening': {stage: deepcopy(documents[stage + '_screen.json']) for stage in ('audio', 'video', 'lipsync')}}}


def _legacy_asset(node, gaps):
    """Retain the existing Seedance segment/version and speech acceptance rules."""
    directory=OUT/'audio_video'/node['scenario_id']
    source_manifest=load(directory/'manifest.json') if (directory/'manifest.json').exists() else {'nodes':[]}
    candidate=next((n for n in source_manifest['nodes'] if n['node_id']==node['node_id']),None)
    completed=load(directory/'completed_nodes.json') if (directory/'completed_nodes.json').exists() else []
    complete=next((n for n in completed if n['node_id']==node['node_id']),None)
    if not complete or not candidate:
        gaps.append({'scene':node['scenario_id'],'location':node['location'],'node_id':node['node_id'],'reason':'audio_video_not_completed'})
        return None
    if source_manifest.get('human_reference_images_unavailable') and source_manifest.get('reference_mode')!='silent_video':
        gaps.append({'scene':node['scenario_id'],'location':node['location'],'node_id':node['node_id'],'reason':'character_consistency_pending'})
        return None
    if [x['request_id'] for x in complete['asset'].get('boundary_silence_edits',[])]!=candidate['segment_request_ids']:
        gaps.append({'scene':node['scenario_id'],'location':node['location'],'node_id':node['node_id'],'reason':'current_identity_version_not_assembled'})
        return None
    for k in ('source_public_response','source_observable_expression','speaker','location'):
        assert candidate[k]==node[k],(node['node_id'],k)
    asset=complete['asset'];path=Path(asset['path']);assert sha(path)==asset['sha256']
    assert asset['spoken_text']==node['source_public_response'] and asset['speech_language']=='en'
    speech=load(directory/'speech_screen.json').get('nodes',{}).get(node['node_id'],{}) if (directory/'speech_screen.json').exists() else {}
    if speech.get('video_sha256')!=asset['sha256'] or speech.get('language')!='en' or speech.get('normalized_similarity',0)<0.98 or speech.get('critical_content_match') is not True:
        gaps.append({'scene':node['scenario_id'],'location':node['location'],'node_id':node['node_id'],'reason':'speech_check_not_passed'})
        return None
    metadata=asset['structural_metadata'];assert metadata['audio_stream_count']>=1 and metadata['duration_seconds_actual']>0
    return asset

def media_snapshot(release):
    return {'release': release['release'], 'dataset_sha256': release['dataset_sha256'],
        'source_bank_sha256': release['source_bank_sha256'], 'assignments': release['assignments'],
        'items': [{'id': x['id'], 'item_sha256': x['item_sha256'], 'has_video': bool(x['public_video']),
                   'media': x['media'], 'coverage': x['coverage']} for x in release['items']]}


def export(site, allow_partial=False):
    rows=[json.loads(s) for s in (OUT/'items.jsonl').read_text().splitlines()]
    manifest=load(OUT/'manifest.json');bank_sha=sha(OUT/'items.jsonl')
    assert manifest['items_sha256']==bank_sha and len(rows)==400
    old=load(ROOT/'data/human_gt_20261022/release.json')
    result={k:deepcopy(v) for k,v in old.items() if k not in ('items','private','evidence_blobs','assignments','dataset_sha256','release','source_bank_sha256')}
    result.update(release=manifest['release'],source_bank_sha256=bank_sha,items=[],private={},evidence_blobs={},assignments=[],language='en',task_difficulty=QUOTAS)
    expected=public_nodes(rows)
    local_manifest_path=OUT/'local_av/manifest.json'
    local_index={}
    if local_manifest_path.exists():
        local_manifest=load(local_manifest_path)
        if local_manifest.get('source_bank_sha256')!=bank_sha:
            raise ValueError('Local audio/video jobs belong to a different frozen question bank')
        local_index={n['node_id']:n for n in local_manifest['nodes']}
        if len(local_index)!=len(local_manifest['nodes']):
            raise ValueError('Duplicate nodes in local audio/video job index')
    assets={};gaps=[];media={};coverage=[];local_media={};completed_nodes=[]
    hosted_root=ROOT/'data/offline_talking_head_en_v1'/bank_sha[:16]
    for node in expected:
        local_directory=OUT/'local_av'/node['scenario_id']/node['node_id']
        if node['node_id'] in local_index or local_directory.exists():
            try:
                job=local_index.get(node['node_id'],{})
                _require(job.get('scenario_id')==node['scenario_id'] and
                         (ROOT/job.get('request_path','')).resolve()==(local_directory/'request.json').resolve(),
                         'local_job_index_mismatch')
                asset=validate_local_asset(node,local_directory,expected_spec_sha256=job.get('spec_sha256'))
            except LocalAssetError as exc:
                gaps.append({'scene':node['scenario_id'],'location':node['location'],'node_id':node['node_id'],
                             'reason':'local_audio_video_not_ready','detail':str(exc)})
                continue
            path=Path(asset['path']);metadata=asset['structural_metadata']
        else:
            asset=_legacy_asset(node,gaps)
            if asset is None:continue
            path=Path(asset['path']);metadata=asset['structural_metadata']
        target=site/'public/media'/(asset['sha256']+'.mp4');target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copyfile(path,target)
        assert sha(target)==asset['sha256']
        a={'asset_id':'video-'+asset['sha256'][:16],'sha256':asset['sha256'],'url':'/media/'+target.name,
           'speech_language':'en','audio_required':True,'spoken_text':asset['spoken_text'],'duration_seconds':metadata['duration_seconds_actual'],
           'media_kind':'talking_head','human_review':'pending','speech_verified':False}
        if asset.get('provider')=='local':
            a.update(provider='local',method=asset['method'],spec_sha256=asset['spec_sha256'])
        assets[node['node_id']]=a
        local_target=hosted_root/'assets'/(node['node_id']+'-'+asset['sha256'][:16]+'.mp4')
        local_target.parent.mkdir(parents=True,exist_ok=True)
        if not local_target.exists():shutil.copyfile(path,local_target)
        assert sha(local_target)==asset['sha256']
        local_asset={**deepcopy(asset),'path':str(local_target.relative_to(ROOT))}
        if asset.get('provider')=='local':
            from evaluation.t4_media import extract_frames
            duration=metadata['duration_seconds_actual']
            local_asset['frames']=extract_frames(local_target,hosted_root/'frames'/asset['sha256'],
                tuple(round(duration*fraction,3) for fraction in (.1,.35,.6,.85)))
        completed_nodes.append({'node_id':node['node_id'],'asset':local_asset,'bindings':node['bindings']})
        for binding in node['bindings']:
            media.setdefault(binding['instance_id'],[]).append({**a,'evidence_ids':binding['evidence_ids']})
            local_media.setdefault(binding['instance_id']+'-video',[]).append({**local_asset,'evidence_ids':binding['evidence_ids']})

    requirements={}
    for node in expected:
        for b in node['bindings']:requirements.setdefault(b['instance_id'],set()).add(node['node_id'])
    if gaps and not allow_partial:raise ValueError(f'{len(gaps)} of {len(expected)} audio/video nodes are incomplete; refusing full-ready export')
    complete_scenes={scene for scene in {x['story_id'] for x in rows}
        if all(requirements[x['instance_id']] <= assets.keys() for x in rows if x['story_id']==scene)}
    for item in rows:
        validate_item(item);ident=item['instance_id'];public=public_instance(item)
        assert not CJK.search(json.dumps(public,ensure_ascii=False))
        ready=item['story_id'] in complete_scenes
        clips=media.get(ident,[]) if ready else []
        video=deepcopy(public) if ready else None
        if video:video['modality']='text+video'
        evidence_ids=sorted({e for v in clips for e in v['evidence_ids']})
        result['items'].append({'id':ident,'scene_id':item['story_id'],'task':item['task'],'item_sha256':item_digest(item),
            'public_text':public,'public_video':video,'media':clips,'coverage':{'complete':ready,'media_kind':'talking_head',
            'speech_language':'en','audio_required':True,'covered_evidence_ids':evidence_ids,'human_review':'pending'}})
        coverage.append({'instance_id':ident,'scene':item['story_id'],'task':item['task'],'audio_video_complete':ready,'video_count':len(clips)})
        evidence=private_evidence(item,bank_sha)
        evidence['scope_note']='T1 uses history only up to the checkpoint; T2 uses the controlled histories and identical ending; T3 uses the common prefix and branches within the stated prediction window. Simulator evidence is not human-verified ground truth.'
        for key,value in list(evidence.items()):
            if isinstance(value,(dict,list)):
                h=digest(value);result['evidence_blobs'].setdefault(h,packed(value));evidence[key]={'$ref':h}
        author=item['authoring'];machine={k:author[k] for k in ('answer','rationale','evidence_ids','option_errors','option_variable_map','oracle_reference','api_screening') if k in author}
        result['private'][ident]=packed({'evidence':evidence,'machine':machine,'machine_status':'machine_candidates_not_human_GT'})
    for mode in ('offline_video','offline_text'):
        scenes=sorted({x['scene_id'] for x in result['items']})
        if mode=='offline_video':scenes=[s for s in scenes if all(x['public_video'] for x in result['items'] if x['scene_id']==s)]
        for i in range(0,len(scenes),5):
            group=scenes[i:i+5]
            result['assignments'].append({'id':f'{mode}-{i//5+1:02}','track':mode,
                'label':f'T1–3 · {"English text + video + audio" if mode=="offline_video" else "English text"} · Group {i//5+1}',
                'scene_ids':group,'item_ids':[x['id'] for x in result['items'] if x['scene_id'] in group]})
    result['assignments'].extend(deepcopy(a) for a in old['assignments'] if a['track']=='t4')
    result['media_readiness']={'required_nodes':len(expected),'completed_nodes':len(assets),'complete_items':sum(x['audio_video_complete'] for x in coverage),'gaps':gaps,'audio_required':True,'human_review':'pending'}
    pairs=[];complete_ids={x['instance_id'] for x in coverage if x['audio_video_complete']}
    for item in rows:
        if item['instance_id'] not in complete_ids:continue
        text=deepcopy(item);video=deepcopy(item)
        for variant in (text,video):variant['metadata']['modality_pair_id']=item['instance_id']
        video.update(instance_id=item['instance_id']+'-video',modality='text+video')
        video['authoring']['matched_assets']=[{'sha256':a['sha256'],'evidence_ids':a['evidence_ids']} for a in local_media[video['instance_id']]]
        validate_item(video);pairs.extend([text,video])
    local_media={k:v for k,v in local_media.items() if k.removesuffix('-video') in complete_ids}
    save(OUT/'media.json',local_media);jsonl(OUT/'paired.items.jsonl',pairs);jsonl(OUT/'paired.public.jsonl',map(public_instance,pairs))
    save(hosted_root/'completed_nodes.json',completed_nodes)
    save(hosted_root/'manifest.json',{'format':'socialflux_annotation400_audio_video_v1','bank_path':str(OUT.relative_to(ROOT)),
        'items_sha256':bank_sha,'speech_language':'en','audio_required':True,'nodes':expected,'human_review':'pending'})
    save(OUT/'pairing_report.json',{'items_sha256':bank_sha,'media_sha256':sha(OUT/'media.json'),'input_item_count':400,
        'logical_pairs':len(complete_ids),'variants':len(pairs),'unique_videos':len(assets),'media_kind':'talking_head',
        'audio_required':True,'coverage_counts':{'complete':len(complete_ids),'missing':400-len(complete_ids)},'gaps':gaps,'human_media_review':'pending'})
    result['dataset_sha256']=digest(result)
    first_snapshot=site/'data/research-annotation400-first-overlay.json'
    snapshot=load(first_snapshot) if first_snapshot.exists() else {}
    if snapshot:
        assert snapshot['source_bank_sha256']==bank_sha,'Published English questions changed; freeze a full additional release instead'
        assert {x['id']:x['item_sha256'] for x in snapshot['items']}=={x['id']:x['item_sha256'] for x in result['items']}
    elif gaps and allow_partial:
        save(OUT/'release.first-media.json',result)
        save(first_snapshot,{'release':result['release'],'dataset_sha256':result['dataset_sha256'],'source_bank_sha256':bank_sha,
            'assignments':result['assignments'],'items':[{'id':x['id'],'item_sha256':x['item_sha256'],'has_video':bool(x['public_video']),
            'media':x['media'],'coverage':x['coverage']} for x in result['items']]})
    previous_path=site/'data/research-server.json'
    history_path=site/'data/research-media-history.json'
    history=load(history_path) if history_path.exists() else []
    if previous_path.exists():
        previous=json.loads(gzip.decompress(base64.b64decode(load(previous_path)['gzip_base64'])))
        if previous['source_bank_sha256']==bank_sha and previous['dataset_sha256']!=result['dataset_sha256']:
            if previous['dataset_sha256'] not in {h['dataset_sha256'] for h in history}:
                history.append(media_snapshot(previous))
    save(history_path,history)
    save(OUT/'release.json',result)
    save(site/'data/research-server.json',{'gzip_base64':packed(result)})
    # Gate2 independently freezes its own tasks and retains prior packet hashes.
    # Each media release has a new dataset hash, so bind its review bundle too.
    from scripts.build_gate2_annotation import build as build_gate2
    build_gate2(site)
    save(OUT/'media_coverage.json',{'summary':result['media_readiness'],'items':coverage})
    save(ROOT/'reports/experiments/2026-10-22_annotation400_release.json',{'release':result['release'],'dataset_sha256':result['dataset_sha256'],'source_bank_sha256':bank_sha,'items':400,'scenes':50,'language':'en','task_difficulty':QUOTAS,'media_readiness':result['media_readiness']})
    print(json.dumps({'release':result['release'],'items':400,'audio_video_items':result['media_readiness']['complete_items'],'audio_video_nodes':len(assets),'missing_nodes':len(gaps),'dataset_sha256':result['dataset_sha256']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--site-dir',type=Path,default=ROOT/'build/annotation400-site');p.add_argument('--allow-partial-media',action='store_true');a=p.parse_args();export(a.site_dir,a.allow_partial_media)
