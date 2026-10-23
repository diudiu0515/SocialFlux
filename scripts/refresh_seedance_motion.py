"""Replace diagnosed reference-copying with new temporal performances.

Every original output and task ID is archived before one bounded replacement.
The input reference remains an unmodified, provider-generated original video.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import argparse
import fcntl
import json
import math
import os
import shutil
import time
import wave
from array import array
from pathlib import Path

from scripts.seedance_state_batch import (ROOT, OUT, load, save, sha, generate, set_reference,
    native_video_only_reference, native_frame_reference, render_prompt, utc_now)
from scripts.refresh_online_state_videos import TARGET
from environment.online_video_assets import build_online_asset_request
from environment.state_performance import fresh_performance_prompt, still_identity_performance_prompt

AUDIT = ROOT / 'build/seedance-reference-motion-audit-complete-20261023.json'
PLAN = TARGET / 'motion-refresh-plan.json'
CONTRACT = 'next_shot_v1'
STILL_PLAN = TARGET / 'still-refresh-plan.json'


def reference_for(sid, rows):
    direct = TARGET / 'references' / (sid+'--silent_identity')
    if native_video_only_reference(direct):
        return direct
    options = []
    for row in rows:
        if row['scenario_id'] != sid:
            continue
        directory = ROOT / row['directory']
        p = directory / 'qa/audio_screen.json'
        if not p.exists():
            continue
        screen, state = load(p), load(directory / 'provider-state.json')
        if (screen.get('machine_screen_passed') is not True or screen.get('transcript')
            or state.get('status') != 'downloaded'
            or screen.get('source_native_sha256') != state.get('video_sha256')):
            continue
        with wave.open(str(directory / 'qa/speech.wav')) as audio:
            samples = array('h', audio.readframes(audio.getnframes()))
        rms = math.sqrt(sum(x*x for x in samples)/len(samples))
        options.append((rms, str(directory), directory))
    if not options:
        raise ValueError('No checked same-scene reference: '+sid)
    return min(options)[2]


def snapshot(sid, source):
    target = TARGET / 'references' / (sid+'--motion_anchor')
    state = load(source / 'provider-state.json')
    if state.get('status') != 'downloaded' or sha(source / 'native.mp4') != state['video_sha256']:
        raise ValueError('Reference native output changed')
    target.mkdir(parents=True, exist_ok=True)
    native = target / 'native.mp4'
    if not native.exists():
        os.link(source / 'native.mp4', native)
    if sha(native) != state['video_sha256']:
        raise ValueError('Existing stable reference differs')
    state = deepcopy(state)
    state.update(video_file=str(native), original_source_directory=str(source.relative_to(ROOT)))
    save(target / 'provider-state.json', state)
    for name in ('probe.json', 'reference-screen.json', 'qa/audio_screen.json'):
        if (source / name).exists():
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target / name)
    save(target / 'continuity.json', dict(source=str(source.relative_to(ROOT)),
        native_sha256=state['video_sha256'], transform='none; hardlink to original provider output', at=utc_now()))
    return str(target.relative_to(ROOT))


def prepare():
    if PLAN.exists():
        return load(PLAN)
    online, offline = load(TARGET/'manifest.json')['requests'], load(OUT/'manifest.json')['nodes']
    rows = {r['node_id']: r for r in online+offline}
    audit = load(AUDIT)
    if audit['unresolved']:
        raise ValueError('Resolve incomplete motion audit before replacement')
    selected = [r for r in audit['results'] if r.get('reference_motion_suspected')
                and r.get('location') in ('online', 't2')]
    references = {sid: snapshot(sid, reference_for(sid, online)) for sid in sorted({r['scenario'] for r in selected})}
    items = []
    for diagnosis in selected:
        row = rows[diagnosis['node']]
        directory = ROOT / row['directory']
        if sha(directory/'native.mp4') != diagnosis['source_native_sha256']:
            raise ValueError('Output changed after motion audit')
        items.append(dict(node_id=row['node_id'], scenario_id=row['scenario_id'], location=row['location'],
            original_native_sha256=diagnosis['source_native_sha256'], reference_directory=references[row['scenario_id']],
            diagnosis=diagnosis))
    plan = dict(id='seedance-new-shot-20261023', contract=CONTRACT, created_at=utc_now(),
        audit_sha256=sha(AUDIT), references=references, items=items, total=len(items),
        online=sum(r['location']=='online' for r in items), offline=sum(r['location']=='t2' for r in items),
        authorization='User authorized complete replacement; repairs required after detecting copied reference acting')
    save(PLAN, plan)
    return plan


def revise(item, row, anchor, plan):
    directory = ROOT / row['directory']
    with (directory / '.pipeline.lock').open('a') as pipeline:
        fcntl.flock(pipeline, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (directory / '.generation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            audit = load(directory / 'prompt-audit.json')
            if audit.get('motion_refresh_plan') != plan['id']:
                state = load(directory / 'provider-state.json')
                if state.get('status') != 'downloaded' or sha(directory/'native.mp4') != item['original_native_sha256']:
                    raise ValueError('Only the diagnosed complete output can be replaced')
                archive = directory / 'retired_motion' / '01'
                if archive.exists():
                    raise ValueError('Motion archival already started; inspect before resuming')
                archive.mkdir(parents=True)
                keep = {'inputs.json','provenance.json','direction.json','request.json','prompt.en.txt','prompt-audit.json'}
                for path in list(directory.iterdir()):
                    if path.name.startswith('.') or path.name == 'retired_motion':
                        continue
                    if path.name in keep:
                        shutil.copy2(path, archive/path.name)
                    else:
                        shutil.move(str(path), archive/path.name)
                save(archive/'retirement.json', dict(reason='Reference acting copied despite new state/event direction',
                    diagnosis=item['diagnosis'], at=utc_now(), replacement_plan=plan['id']))
                if row['location'] == 'online':
                    inputs = load(directory/'inputs.json')
                    identity = inputs['identity']
                    # Identity is already bound to the frozen scene; no new persona is authored.
                    scenario = dict(scenario_id=row['scenario_id'], environment_agent=dict(persona=dict(
                        name=identity['character_name'], role=identity['character_role'])))
                    request = build_online_asset_request(scenario, row['event_family'],
                        duration_seconds=row['duration_seconds'], identity_override=identity,
                        reference_video_file=str(ROOT/item['reference_directory']/'native.mp4'))
                    prompt = request['prompt']
                    save(directory/'request.json', request)
                else:
                    direction = load(directory/'direction.json')
                    prompt = fresh_performance_prompt(render_prompt(direction, row['exact_line'], True), duration=5)
                    if prompt.count(row['exact_line']) != 1:
                        raise ValueError('Locked dialogue must occur exactly once')
                    set_reference(row['node_id'], item['reference_directory'])
                (directory/'prompt.en.txt').write_text(prompt)
                audit.update(prompt_sha256=sha(directory/'prompt.en.txt'), motion_contract=CONTRACT,
                    motion_refresh_plan=plan['id'], reference_directory=item['reference_directory'],
                    authoring='state_directed_new_temporal_performance', external_text_model_calls=0,
                    implementation_sha256=sha(ROOT/'environment/state_performance.py'), human_review='pending')
                save(directory/'prompt-audit.json', audit)
        generate(dict(row, reference_directory=item['reference_directory']), anchor, submit_new=True)
        print(json.dumps(dict(node=row['node_id'], status='new_performance_downloaded')), flush=True)


def prepare_still(audit_path):
    if STILL_PLAN.exists():
        return load(STILL_PLAN)
    audit_path = ROOT / audit_path
    audit = load(audit_path)
    if audit['unresolved']:
        raise ValueError('Finish active generation before freezing the still-reference repair plan')
    from scripts.complete_seedance_dialogue import quality
    rows = {r['node_id']:r for r in load(OUT/'manifest.json')['nodes']+load(TARGET/'manifest.json')['requests']}
    items = []
    for diagnosis in audit['results']:
        row = rows[diagnosis['node']]
        if row['location'] not in ('online', 't2'):
            continue
        directory = ROOT / row['directory']
        state = load(directory/'provider-state.json')
        if diagnosis.get('source_native_sha256') != state.get('video_sha256'):
            raise ValueError('Motion audit is stale: '+row['node_id'])
        if row['location'] == 'online':
            screen = load(directory/'qa/audio_screen.json')
            bad_audio = screen.get('machine_screen_passed') is not True or bool(screen.get('transcript'))
        else:
            bad_audio = quality(directory) is not True
        if diagnosis.get('reference_motion_suspected') or bad_audio:
            items.append(dict(node_id=row['node_id'], scenario_id=row['scenario_id'], location=row['location'],
                original_native_sha256=sha(directory/'native.mp4'), diagnosis=diagnosis,
                audio_repair_required=bad_audio,
                reference_image_directory=str((TARGET/'references'/(row['scenario_id']+'--original_frame')).relative_to(ROOT))))
    plan = dict(id='seedance-original-still-20261023', created_at=utc_now(), audit_sha256=sha(audit_path),
        contract='original_still_v1', items=items, total=len(items),
        online=sum(i['location']=='online' for i in items), offline=sum(i['location']=='t2' for i in items),
        authorization='Complete user-authorized replacement; repair diagnosed copied motion or invalid audio')
    save(STILL_PLAN, plan)
    return plan


def ensure_original_frame(sid, anchor):
    directory = TARGET/'references'/(sid+'--original_frame')
    directory.mkdir(parents=True, exist_ok=True)
    if (directory/'frame-receipt.json').exists():
        native_frame_reference(directory)
        return
    row = dict(node_id=directory.name, scenario_id=sid, location='identity_reference',
        directory=str(directory.relative_to(ROOT)), duration_seconds=4, return_last_frame=True,
        reference_directory=str((TARGET/'references'/(sid+'--motion_anchor')).relative_to(ROOT)))
    if not (directory/'provider-state.json').exists():
        prompt = ('Preserve this original fictional actor, wardrobe and room. The person finishes the current '
            'thought and becomes a quiet attentive listener with lips gently closed, head upright and eyes '
            'resting on the partner. Their final expression is attentive and composed. One continuous '
            'four-second medium close-up. No words, gestures, captions, cuts or human vocal sounds. '
            'The provider generates video only and returns its original final frame.')
        (directory/'prompt.en.txt').write_text(prompt)
        save(directory/'inputs.json', dict(row=row, purpose='Original provider still preserves identity without a motion timeline'))
        save(directory/'prompt-audit.json', dict(prompt_sha256=sha(directory/'prompt.en.txt'),
            authoring='original_provider_last_frame', output_role='identity_reference_not_published'))
    generate(row, anchor, submit_new=True)
    from scripts.run_autodl_seedance_video import SeedanceClient
    from urllib.parse import urlparse
    state = load(directory/'provider-state.json')
    url = state['latest_query_response']['content']['last_frame_url']
    if urlparse(url).scheme != 'https' or not urlparse(url).netloc:
        raise ValueError('Provider original frame URL is missing')
    config = load(ROOT/'configs/gpt50_experiment/video_completion.active.json')
    client = SeedanceClient(Path(config['key_file']).read_text().strip())
    client.download(url, directory/'native-last-frame.jpg')
    save(directory/'frame-receipt.json', dict(version='provider_native_last_frame_v1',
        source_native_sha256=state['video_sha256'], frame_sha256=sha(directory/'native-last-frame.jpg'),
        provider_return_last_frame=True, transform='none; original provider-returned image',
        source='latest_query_response.content.last_frame_url'))
    native_frame_reference(directory)
    print(json.dumps(dict(scene=sid, status='original_frame_ready')), flush=True)


def revise_still(item, row, anchor, plan):
    directory = ROOT/row['directory']
    reference = item['reference_image_directory']
    native_frame_reference(ROOT/reference)
    with (directory/'.pipeline.lock').open('a') as pipeline:
        fcntl.flock(pipeline, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (directory/'.generation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            audit = load(directory/'prompt-audit.json')
            if audit.get('still_refresh_plan') != plan['id']:
                state = load(directory/'provider-state.json')
                if state.get('status') != 'downloaded' or sha(directory/'native.mp4') != item['original_native_sha256']:
                    raise ValueError('Only the diagnosed completed output can be replaced')
                archive = directory/'retired_still'/'01'
                if archive.exists():
                    raise ValueError('Still archival already started; inspect before resuming')
                archive.mkdir(parents=True)
                keep = {'inputs.json','provenance.json','direction.json','request.json','prompt.en.txt','prompt-audit.json'}
                for path in list(directory.iterdir()):
                    if path.name.startswith(('.', 'retired_')):
                        continue
                    if path.name in keep:
                        shutil.copy2(path, archive/path.name)
                    else:
                        shutil.move(str(path), archive/path.name)
                save(archive/'retirement.json', dict(reason='Reference motion or invalid audio after video-reference generation',
                    diagnosis=item['diagnosis'], at=utc_now(), replacement_plan=plan['id']))
                if row['location'] == 'online':
                    identity = load(directory/'inputs.json')['identity']
                    scenario = dict(scenario_id=row['scenario_id'], environment_agent=dict(persona=dict(
                        name=identity['character_name'], role=identity['character_role'])))
                    request = build_online_asset_request(scenario, row['event_family'],
                        duration_seconds=row['duration_seconds'], identity_override=identity)
                    prompt = still_identity_performance_prompt(request['prompt'],
                        duration=row['duration_seconds'], event_family=row['event_family'])
                    request['prompt'] = prompt
                    save(directory/'request.json', request)
                else:
                    prompt = still_identity_performance_prompt(render_prompt(load(directory/'direction.json'),
                        row['exact_line'], True), duration=5)
                    if prompt.count(row['exact_line']) != 1:
                        raise ValueError('Locked dialogue must occur exactly once')
                    with (OUT/'.manifest.lock').open('a') as manifest_lock:
                        fcntl.flock(manifest_lock, fcntl.LOCK_EX)
                        manifest = load(OUT/'manifest.json')
                        target = next(r for r in manifest['nodes'] if r['node_id']==row['node_id'])
                        target['reference_image_directory'] = reference
                        save(OUT/'manifest.json', manifest)
                (directory/'prompt.en.txt').write_text(prompt)
                audit.update(prompt_sha256=sha(directory/'prompt.en.txt'), motion_contract='original_still_v1',
                    still_refresh_plan=plan['id'], reference_image_directory=reference,
                    authoring='state_directed_original_still_performance', external_text_model_calls=0,
                    implementation_sha256=sha(ROOT/'environment/state_performance.py'), human_review='pending')
                save(directory/'prompt-audit.json', audit)
                # Reuse a checked pilot only when it is this exact request.
                pilot = ROOT/'build/seedance-still-performance-pilot-20261023'/row['node_id']
                pilot_checks = ROOT/'build/seedance-still-pilot-audio-20261023.json'
                if (pilot/'provider-state.json').is_file() and pilot_checks.is_file():
                    source = load(pilot/'provider-state.json')
                    checks = {r['node']:r for r in load(pilot_checks)}
                    check = checks.get(row['node_id'], {})
                    if (source.get('status')=='downloaded' and source.get('prompt_sha256')==sha(directory/'prompt.en.txt')
                        and source.get('video_sha256')==sha(pilot/'native.mp4')==check.get('source_native_sha256')
                        and check.get('machine_screen_passed') is True and not check.get('transcript')
                        and [c['image_url']['url'] for c in source['request']['content'] if c['type']=='image_url']==[native_frame_reference(ROOT/reference)]):
                        os.link(pilot/'native.mp4', directory/'native.mp4')
                        shutil.copy2(pilot/'probe.json', directory/'probe.json')
                        source.update(video_file=str(directory/'native.mp4'), adopted_from=str(pilot.relative_to(ROOT)))
                        save(directory/'provider-state.json', source)
                        request = load(directory/'request.json')
                        request['reference_image_file'] = str(ROOT/reference/'native-last-frame.jpg')
                        save(directory/'request.json', request)
        generate(dict(row, reference_image_directory=reference), anchor, submit_new=True)
        print(json.dumps(dict(node=row['node_id'], status='still_performance_downloaded')), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare','generate','prepare-still','generate-still'])
    parser.add_argument('--workers', type=int, default=32)
    parser.add_argument('--audit', default='build/seedance-motion-audit-final-20261023.json')
    parser.add_argument('--wait-for-frames', action='store_true', help='Reuse an already-running original-frame preparation campaign')
    args = parser.parse_args()
    use_still = args.command.endswith('-still')
    plan = prepare_still(args.audit) if use_still else prepare()
    if args.command.startswith('prepare'):
        print(json.dumps({k:plan[k] for k in ('id','total','online','offline')}))
        return
    offline = load(OUT/'manifest.json')['nodes']
    rows = {r['node_id']:r for r in offline+load(TARGET/'manifest.json')['requests']}
    anchors = {r['scenario_id']:r for r in offline if r['location']=='t1'}
    if use_still and not args.wait_for_frames:
        with ThreadPoolExecutor(max_workers=min(24,max(1,args.workers))) as pool:
            list(pool.map(lambda sid:ensure_original_frame(sid,anchors[sid]), sorted({i['scenario_id'] for i in plan['items']})))
    failures=[]
    def work(item):
        if use_still and args.wait_for_frames:
            reference = ROOT/item['reference_image_directory']
            deadline = time.monotonic()+1800
            while not (reference/'frame-receipt.json').exists():
                state_path = reference/'provider-state.json'
                state = load(state_path) if state_path.exists() else {}
                if state.get('status') in ('failed','cancelled','expired','submission_error_needs_review'):
                    raise ValueError('Original frame preparation failed; do not submit dependent videos')
                if time.monotonic()>deadline:
                    raise TimeoutError('Original provider frame not ready')
                time.sleep(10)
        (revise_still if use_still else revise)(item,rows[item['node_id']],anchors[item['scenario_id']],plan)
    with ThreadPoolExecutor(max_workers=min(40,max(1,args.workers))) as pool:
        jobs={pool.submit(work,item):item for item in plan['items']}
        for future in as_completed(jobs):
            item=jobs[future]
            try:future.result()
            except Exception as exc:
                failures.append(dict(node=item['node_id'],type=type(exc).__name__))
                save(TARGET/'errors'/(item['node_id']+'-motion.json'),dict(error=str(exc),at=utc_now()))
                print(json.dumps(dict(node=item['node_id'],status='needs_review',type=type(exc).__name__)),flush=True)
    save(TARGET/('still-generation-summary.json' if use_still else 'motion-generation-summary.json'),dict(failures=failures,at=utc_now(),plan=plan['id']))
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
