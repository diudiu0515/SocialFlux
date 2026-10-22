"""Bounded four-request audio/video queue; resumes existing provider task IDs."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import json
import hashlib
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.prepare_annotation400_av import prepare_scene, AV, OUT, load, save
from scripts.run_multimodal_video_queue import run_record, DEFAULT_KEY_FILE
from offline.talking_head import finalize
from prompts.loader import render_prompt

ASR=ROOT/'.local_models/offline-asr-env/bin/python'

def record_run(m,r):
    control=load(AV/'generation_control.json') if (AV/'generation_control.json').exists() else {'submit_new':False}
    return run_record(ROOT,r,key_file=DEFAULT_KEY_FILE,model=m['provider']['model'],resolution=m['provider']['resolution'],submit_new=control.get('submit_new') is True,poll_seconds=15,max_wait_seconds=1800)

def check_segment(path,r):
    subprocess.run([str(ASR),str(ROOT/'scripts/screen_annotation400_av.py'),'--manifest',str(path),'--request-id',r['request_id']],check=True,stdout=subprocess.DEVNULL)
    return load(path.parent/'segment_speech_screen.json')[r['request_id']]

def replacement(path,m,record,*,text_only,reason):
    """Keep prior paid artifacts immutable; bind a documented new attempt."""
    attempt=record.get('annotation400_attempt',1)+1
    if attempt>3:raise RuntimeError('Three generation attempts exhausted: '+record['request_id'])
    r=deepcopy(record);request=load(ROOT/r['request_file'])
    prior=r['request_id'];r['request_id']+=('-text' if text_only else '-speech')+str(attempt)
    r['annotation400_attempt']=attempt
    r['request_file']=str((path.parent/'requests'/(r['request_id']+'.json')).relative_to(ROOT))
    r['video_file']=str((path.parent/'segments'/(r['request_id']+'.mp4')).relative_to(ROOT))
    if text_only:
        request['reference_video_file']=None;request['reference_image_file']=None
        node=next(n for n in m['nodes'] if n['node_id']==r['node_id'])
        request['prompt']=render_prompt('offline_talking_head_english_v1',identity_json=request['identity'],spoken_line=request['audio']['exact_line'],expression_json=node['source_observable_expression'])
        request['prompt_id']='annotation400_text_identity_english_v1'
    request['prompt']+='\nPronounce every technical term and name clearly, using the exact written words. Complete the line once before the clip ends.'
    request['duration_seconds']=15
    request['prompt_sha256']=hashlib.sha256(request['prompt'].encode()).hexdigest()
    save(ROOT/r['request_file'],request)
    m.setdefault('superseded_requests',[]).append({'record':record,'reason':reason,'replacement':r['request_id']})
    m['requests']=[r if x['request_id']==prior else x for x in m['requests']]
    for n in m['nodes']:n['segment_request_ids']=[r['request_id'] if x==prior else x for x in n['segment_request_ids']]
    save(path,m);return r

def checked_record(path,m,r):
    while True:
        if m.get('human_reference_images_unavailable') and load(ROOT/r['request_file']).get('reference_image_file'):
            r=replacement(path,m,r,text_only=True,reason='text_only_fictional_character_after_reference_transport_rejection')
        outcome=record_run(m,r)
        if outcome['status']!='downloaded':
            if 'InputImageSensitiveContentDetected.PrivacyInformation' in json.dumps(outcome):
                # The provider does not accept human reference images. Use an
                # original text-only fictional character, without that image.
                m['human_reference_images_unavailable']=True
                r=replacement(path,m,r,text_only=True,reason='provider_disallows_human_reference_image');continue
            raise RuntimeError('Video incomplete: '+json.dumps(outcome))
        check=check_segment(path,r)
        if check['machine_screen_passed']:return r
        request=load(ROOT/r['request_file'])
        r=replacement(path,m,r,text_only=not (request.get('reference_image_file') or request.get('reference_video_file')),reason='unprompted_speech_check_failed')

def silent_requests(path):
    refs=load(OUT/'silent_identity_references/manifest.json')
    if not refs.get('hosted') or not refs.get('pilot_verified'):
        raise RuntimeError('Silent identity references must be hosted and the pilot verified first')
    m=load(path);scene=m['nodes'][0]['scenario_id'];ref=next(r for r in refs['references'] if r['scene']==scene)
    if m.get('reference_mode')=='silent_video' and m.get('identity_reference_sha256')==ref['sha256']:return m
    save(path.with_name('manifest.before_silent_reference.json'),m)
    records=[];mapping={}
    for old in m['requests']:
        original_request=load(ROOT/old['request_file']);state_path=path.parent/'provider_states'/(old['request_id']+'.json');state=load(state_path) if state_path.exists() else {}
        same_anchor=state.get('status')=='downloaded' and state.get('video_sha256')==ref['source_sha256']
        same_image=state.get('status')=='downloaded' and original_request.get('reference_image_file') and not m.get('human_reference_images_unavailable') and ref['source_kind']=='generated_english_anchor'
        if same_anchor or same_image:
            records.append(old);mapping[old['request_id']]=old['request_id'];continue
        r=deepcopy(old);r['request_id']+='-silentweb-v1';r['annotation400_attempt']=1
        r['request_file']=str((path.parent/'requests'/(r['request_id']+'.json')).relative_to(ROOT));r['video_file']=str((path.parent/'segments'/(r['request_id']+'.mp4')).relative_to(ROOT))
        request=deepcopy(original_request);request.update(reference_image_file=None,reference_video_file=ref['path'],reference_video_transport='provided_url',reference_video_url=ref['url'],prompt_id='annotation400_silent_synthetic_identity_v1')
        node=next(n for n in m['nodes'] if n['node_id']==r['node_id'])
        request['prompt']='Use the supplied original generated fictional-adult video ONLY to preserve the SAME person, age, face, hairstyle, wardrobe, setting and framing. The reference has NO AUDIO. Create new mouth movements and natural English speech for exactly the new line below; do not infer or copy any dialogue from the reference. Accurate lip sync, natural connected phrases, clear technical words, no additions or repetitions. One continuous shot; no other speaker, music, voiceover, subtitles or text. Finish all words, then remain silent.\nExact new line: '+json.dumps(request['audio']['exact_line'])+'\nPublic expression and delivery: '+json.dumps(node['source_observable_expression'])
        request['prompt_sha256']=hashlib.sha256(request['prompt'].encode()).hexdigest();save(ROOT/r['request_file'],request)
        records.append(r);mapping[old['request_id']]=r['request_id'];m.setdefault('superseded_requests',[]).append({'record':old,'reason':'retain_original_character_with_silent_reference','replacement':r['request_id']})
    for n in m['nodes']:n['segment_request_ids']=[mapping[x] for x in n['segment_request_ids']]
    m.update(requests=records,reference_mode='silent_video',identity_reference_sha256=ref['sha256'],identity_reference_source_sha256=ref['source_sha256'])
    save(path,m);return m

def image_requests(path):
    m=load(path)
    if m.get('reference_mode')=='image_only':return m
    anchor=m['requests'][0]
    anchor=checked_record(path,m,anchor)
    image=path.parent/'identity.png'
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-ss','2','-i',str(ROOT/anchor['video_file']),'-frames:v','1',str(image)],check=True)
    backup=path.with_name('manifest.before_image_reference.json')
    if not backup.exists():save(backup,m)
    records=[anchor];mapping={anchor['request_id']:anchor['request_id']}
    for previous in m['requests'][1:]:
        r=deepcopy(previous);request=load(ROOT/r['request_file']);node=next(n for n in m['nodes'] if n['node_id']==r['node_id'])
        r['request_id']+='-image-v2';mapping[previous['request_id']]=r['request_id']
        r['request_file']=str((path.parent/'requests'/(r['request_id']+'.json')).relative_to(ROOT))
        r['video_file']=str((path.parent/'segments'/(r['request_id']+'.mp4')).relative_to(ROOT))
        request['reference_video_file']=None;request['reference_image_file']=str(image.relative_to(ROOT))
        request['prompt_id']='annotation400_image_identity_english_v1'
        request['prompt']='Use the supplied still image only as the identity, wardrobe, background and framing reference for this original fictional adult. Maintain that appearance and style. Create a NEW continuous conversational shot with natural English speech and precise lip sync. No source audio is supplied. Use a natural adult voice appropriate to the character. Say exactly this line once, without addition, omission or repetition: '+json.dumps(request['audio']['exact_line'])+'\nPublic expression and delivery: '+json.dumps(node['source_observable_expression'])+'\nSpeak in connected, unhurried phrases. Finish all words, then remain silent. No other speakers, music, voiceover, subtitles, text, or camera movement.'
        request['prompt_sha256']=hashlib.sha256(request['prompt'].encode()).hexdigest()
        save(ROOT/r['request_file'],request);records.append(r)
    for n in m['nodes']:n['segment_request_ids']=[mapping[x] for x in n['segment_request_ids']]
    m.update(requests=records,reference_mode='image_only',missing_reference_scenes=[])
    save(path,m)
    # Adopt the independently checked image-reference pilot without paying for
    # the same line again; request bytes and fingerprint remain identical.
    pilot=OUT/'audio_video_image_pilot'/m['nodes'][0]['scenario_id']
    if (pilot/'manifest.json').exists():
        pm=load(pilot/'manifest.json')
        for pr in pm['requests']:
            target=next((r for r in records if r['request_id']==pr['request_id']),None)
            if not target:continue
            state=load(pilot/'provider_states'/(pr['request_id']+'.json'))
            if state.get('status')!='downloaded':continue
            original_request=load(ROOT/pr['request_file'])
            save(ROOT/target['request_file'],original_request)
            destination=ROOT/target['video_file'];destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/pr['video_file'],destination)
            save(path.parent/'provider_states'/(pr['request_id']+'.json'),state)
    return m

def run(scene):
    path=prepare_scene(scene)
    m=silent_requests(path)
    for record in list(m['requests']):
        checked_record(path,m,record)
        finalize(path)
    result=finalize(path)
    subprocess.run([str(ASR),'-m','offline.speech_screen','--manifest',str(path),'--model','large-v3-turbo'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    from difflib import SequenceMatcher
    from scripts.screen_annotation400_av import speech_normalized,critical_content_matches,SCREEN_VERSION
    report=load(path.parent/'speech_screen.json')
    for row in report['nodes'].values():
        row['raw_normalized_similarity']=row['normalized_similarity']
        row['normalized_similarity']=round(SequenceMatcher(None,speech_normalized(row['expected']),speech_normalized(row['transcript']),autojunk=False).ratio(),4)
        row['screen_version']=SCREEN_VERSION
        row['critical_content_match']=critical_content_matches(row['expected'],row['transcript'])
    save(path.parent/'speech_screen.json',report)
    failures=[]
    for p in (path.parent/'provider_states').glob('*.json'):
        if p.stem not in {r['request_id'] for r in m['requests']}:continue
        state=load(p)
        if state.get('status')!='downloaded':failures.append({'request':p.stem,'status':state.get('status'),'error':state.get('last_queue_error') or state.get('latest_query_response',{}).get('error')})
    output={'scene':scene,'result':result,'failures':failures}
    save(path.parent/'run_result.json',output)
    return output

def main():
    scenes={f'GPT50_{i:03}' for i in range(1,51)}
    outcomes=[];started=set();blocked=False;deadline=time.monotonic()+8*3600
    with ThreadPoolExecutor(max_workers=4) as pool:
        active={}
        while len(started)<50 or active:
            if time.monotonic()>deadline:raise RuntimeError('Queue deadline reached; resume from provider task IDs')
            control=load(AV/'generation_control.json') if (AV/'generation_control.json').exists() else {}
            if control.get('submit_new') is not True:blocked=True
            if not blocked:
                for scene in sorted(scenes-started):
                    if len(active)>=4:break
                    if not (OUT/'scenes'/scene/'translated.items.json').exists():continue
                    started.add(scene);active[pool.submit(run,scene)]=scene
            if not active:
                if blocked:break
                time.sleep(15);continue
            done,_=wait(active,timeout=20,return_when=FIRST_COMPLETED)
            for future in done:
                scene=active.pop(future)
                try:result=future.result()
                except Exception as e:result={'scene':scene,'error':str(e),'error_type':type(e).__name__}
                outcomes.append(result)
                text=json.dumps(result).lower()
                if any(s in text for s in ('insufficient balance','insufficient_quota','unauthorized','invalid api key','status_code\": 401')):
                    blocked=True;save(AV/'generation_control.json',{'submit_new':False,'reason':'provider_account_failure'})
                save(AV/'queue_status.json',{'outcomes':outcomes,'active':list(active.values()),'started':sorted(started),'account_blocked':blocked})
                print(json.dumps({'scene':scene,'finished_scenes':len(outcomes),'account_blocked':blocked}),flush=True)
    if blocked:raise SystemExit('Provider account blocked; no further requests submitted')

if __name__=='__main__':main()
