"""Frozen state -> detailed acting direction -> resumable native Seedance AV.

Separate candidate revision: no annotation-bank mutation or automatic publication.
Only an unmodified, original model output is used as a continuity reference.
No automatic retry of a rejected or ambiguous paid submission.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import requests
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from offline.talking_head import public_nodes, canonical_sha
from shared.artifacts import atomic_json
from environment.state_performance import local_direction, cast_text, fresh_performance_prompt, still_identity_performance_prompt
from environment.online_video_assets import online_identity_spec
from scripts.run_multimodal_video_queue import seedance_payload
from scripts.run_autodl_seedance_video import (
    SeedanceClient, materialize_local_references, validate_payload, video_url, utc_now,
)

BANK = ROOT / 'data/offline_annotation400_en_20261022/items.jsonl'
BASELINE = ROOT / 'data/offline_checkpoint_v2_20261022/manifest.json'
OUT = ROOT / 'data/seedance_state_v2_20261023'
PILOT = ROOT / 'build/seedance-state-pilot-20261023'
DIRECTOR = ROOT / 'prompts/seedance_state_director_v2.txt'
PILOT_NODE = 'GPT50_001-t1-e30dc6556d3865ac'
CAST = ('An original fictional adult man named Elias, an ambulance dispatcher in his early forties. '
        'Short curly brown hair, light stubble, an ordinary navy sweater, natural facial asymmetry. '
        'A quiet generic dispatch office with a neutral blurred wall and soft practical side lighting. '
        'A low, clear conversational English voice. Only Elias is visible, addressing one unseen '
        'conversation partner near the lens. Preserve the approved generated identity and voice.')


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, value)


def frozen(path, expected):
    path = ROOT / path
    if sha(path) != expected:
        raise ValueError(f'Frozen source hash mismatch: {path.name}')
    return load(path)


def inputs_for(node, request, by_id):
    """Whitelist current/past inputs; never export question/answer/oracle packet."""
    bound = [by_id[b['instance_id']] for b in node['bindings']]
    source = node['scenario_source']
    scenario = frozen(source['scenario_path'], source['scenario_sha256'])
    trajectory = frozen(source['trajectory_path'], source['trajectory_sha256'])
    result = dict(speaker=request['speaker'], persona=scenario['environment_agent']['persona'],
                  context=bound[0]['input']['context'],
                  exact_line=request['source_public_response'],
                  public_expression=request['source_observable_expression'],
                  duration_seconds=5)
    evidence = dict(scenario_sha256=source['scenario_sha256'],
                    trajectory_sha256=source['trajectory_sha256'])
    if node['location'] == 'ending':
        # Public expression is deliberately identical in both conditions. Do not
        # average incompatible states or choose one oracle replay for the face.
        result['mode'] = 'shared_public_ending'
        result['current_public_response'] = request['full_public_response']
        evidence['state_scope'] = 'shared public cues only; no branch-specific state'
    else:
        location = node['location']
        candidates = []
        for item in bound:
            if item['task'] == 'T2':
                continue
            history = item['input']['history']
            for i, turn in enumerate(history):
                if turn['turn_id'] == location:
                    if turn['environment_character'] != node['source_public_response']:
                        raise ValueError('Public turn/node mismatch')
                    candidates.append(history[:i + 1])
        if not candidates or len({canonical_sha(c) for c in candidates}) != 1:
            raise ValueError('Missing or conflicting current public prefix')
        current = next(t for t in trajectory['turns'] if t['turn_id'] == location)
        # All bound base trajectories must agree on this exact checkpoint.
        states = {canonical_sha({k: current[k] for k in ('state_before', 'state_after')})}
        for item in bound:
            other_source = item['authoring']['construction_source']
            if other_source['trajectory_sha256'] == source['trajectory_sha256']:
                continue
            other = frozen(other_source['trajectory_path'], other_source['trajectory_sha256'])
            t = next(t for t in other['turns'] if t['turn_id'] == location)
            states.add(canonical_sha({k: t[k] for k in ('state_before', 'state_after')}))
        if len(states) != 1:
            raise ValueError('Conflicting current private states for one public node')
        result.update(mode='current_state', public_prefix=candidates[0],
                      **{k: current[k] for k in ('state_before', 'state_after',
                                                'dynamics_before', 'dynamics_after')})
        evidence['state_scope'] = f'{location} current state and public prefix only'
        evidence['state_sha256'] = next(iter(states))
    return result, evidence


def prepare(output=OUT):
    output = Path(output)
    manifest_path = output / 'manifest.json'
    if manifest_path.exists():
        manifest = load(manifest_path)
        if manifest['bank_sha256'] != sha(BANK) or manifest['director_sha256'] != sha(DIRECTOR):
            raise ValueError('Existing batch source/template changed')
        # User explicitly limited offline video to T1/T3. Retire unsubmitted
        # shared-ending preparations; never remove an existing paid task.
        if manifest.get('offline_tasks') != ['T1', 'T3']:
            for row in manifest['nodes']:
                if row['location'] == 'ending':
                    directory = ROOT / row['directory']
                    if (directory / 'provider-state.json').exists():
                        raise ValueError('Ending already submitted; review before retiring')
                    shutil.rmtree(directory)
            manifest['nodes'] = [r for r in manifest['nodes'] if r['location'] != 'ending']
            manifest.update(offline_tasks=['T1', 'T3'], t2_mode='text_only',
                            node_count=len(manifest['nodes']), max_new_video_tasks=len(manifest['nodes'])-1)
            save(manifest_path, manifest)
        return manifest
    items = [json.loads(s) for s in BANK.read_text().splitlines() if s.strip()]
    by_id = {i['instance_id']: i for i in items}
    baseline = {n['node_id']: n for n in load(BASELINE)['nodes']}
    rows = []
    for node in public_nodes(items):
        if node['location'] == 'ending':
            continue
        old_path = Path(baseline[node['node_id']]['request_path'])
        old = load(old_path)
        inputs, evidence = inputs_for(node, old, by_id)
        directory = output / 'nodes' / node['node_id']
        save(directory / 'inputs.json', inputs)
        save(directory / 'provenance.json', dict(**evidence,
            baseline_request_path=str(old_path.relative_to(ROOT)), baseline_request_sha256=sha(old_path),
            inputs_sha256=sha(directory / 'inputs.json'), bindings=node['bindings'],
            method='native_seedance_detailed_state_direction_v2',
            future_state_included=False, question_or_answer_included=False))
        rows.append(dict(node_id=node['node_id'], scenario_id=node['scenario_id'],
                         location=node['location'], mode=inputs['mode'],
                         directory=str(directory.relative_to(ROOT)),
                         exact_line=inputs['exact_line']))
    rows.sort(key=lambda n: (n['scenario_id'], {'t1': 0, 't2': 1, 'ending': 2}[n['location']]))
    manifest = dict(format='seedance_state_native_v2', bank_sha256=sha(BANK),
                    offline_tasks=['T1', 'T3'], t2_mode='text_only',
                    director_sha256=sha(DIRECTOR), nodes=rows, node_count=len(rows),
                    scenario_count=len({n['scenario_id'] for n in rows}),
                    max_new_video_tasks=len(rows)-1, human_review='pilot_method_approved_only',
                    approval=dict(user_message='好多了，就这么做', scope='approved native pilot and method rollout'),
                    published=False, release_eligible=False, created_at=utc_now())
    save(manifest_path, manifest)
    # Adopt the accepted, untouched clip without charging for it again.
    row = next(r for r in rows if r['node_id'] == PILOT_NODE)
    directory = ROOT / row['directory']
    state = load(PILOT / 'provider-state.text-only.json')
    if state['status'] != 'downloaded' or sha(PILOT / 'seedance-native.mp4') != state['video_sha256']:
        raise ValueError('Approved pilot integrity failure')
    shutil.copy2(PILOT / 'seedance-native.mp4', directory / 'native.mp4')
    shutil.copy2(PILOT / 'prompt.text-only.en.txt', directory / 'prompt.en.txt')
    state.update(video_file=str(directory / 'native.mp4'), adopted_existing_task=True)
    save(directory / 'provider-state.json', state)
    save(directory / 'direction.json', dict(cast=CAST, adopted_approved_pilot=True))
    save(directory / 'prompt-audit.json', dict(prompt_sha256=sha(directory / 'prompt.en.txt'),
         inputs_sha256=sha(directory / 'inputs.json'), director_sha256=sha(DIRECTOR),
         human_review='approved', user_message='好多了，就这么做',
         adopted_from=str(PILOT.relative_to(ROOT))))
    result = load(PILOT / 'result.json')
    result.update(human_review='approved_by_user', user_feedback='好多了，就这么做',
                  approval_scope='this native pilot and rollout method; not unseen batch outputs')
    save(PILOT / 'result.json', result)
    return manifest


def render_prompt(direction, line, reference):
    continuity = (
        'Use the supplied unmodified, original model-generated video ONLY as the identity, voice, '
        'wardrobe, lighting and camera reference. This is a NEW dialogue shot of that same fictional adult. '
        'Do not replay its words, mouth shapes or emotional sequence. Preserve the same face, hairstyle, '
        'voice timbre, setting and framing while performing the new line and current thought below. '
        'The reference is not a starting frame that must be copied or an event to re-enact.\n'
    ) if reference else (
        'Create a new original fictional adult from this casting description; do not reproduce any real person.\n'
    )
    return (
        'HIGHEST PRIORITY: EXACT NEW DIALOGUE\n'
        'The visible character speaks ONLY the following English sentence, exactly once, verbatim:\n'
        '<spoken_line>' + line + '</spoken_line>\n'
        'Every word is mandatory and the wording is locked. Do not paraphrase, substitute a pronoun, '
        'replace a contraction, insert conjunctions, add an acknowledgement, or borrow any words from '
        'the reference soundtrack. All other text below is silent actor direction. '
        'The reference soundtrack is an OLD TAKE with DIFFERENT WORDS: discard its dialogue completely. '
        'Compose fresh synchronized voice and mouth movement for this new sentence. '
        'Start speaking within the first half-second and finish the complete sentence before the shot ends.\n\n'
        'Create one continuous five-second photorealistic dramatic dialogue shot. Generate acting, '
        'breathing, voice and lip motion together as one connected performance.\n\nCHARACTER AND FRAME\n'
        + continuity + direction['cast'] + '\n'
        'Fixed eye-level medium close-up, upper chest to above the head; enough room to read breath '
        'through neck and shoulders. One visible person addresses an unseen partner near the lens. '
        'Soft practical lighting, quiet blurred background, no camera movement.\n\nWHAT HAS JUST HAPPENED\n'
        + direction['situation'] + '\n\nPRIVATE ACTOR DIRECTION, NEVER SPOKEN OR SHOWN\n'
        + direction['psychology'] + '\n\nIMMEDIATE OBJECTIVE\n' + direction['objective']
        + '\n\nCONTINUOUS PERFORMANCE, IN THIS ORDER\n' + '\n\n'.join(direction['beats'])
        + '\n\nVOICE AND PACE\n' + direction['voice']
        + '\nBegin soon enough to finish every word within five seconds, leaving a brief reaction '
        'and a short listening tail. Do not clip or rush the last word. Only the locked spoken_line at the top may be spoken.\n'
        '\nSCENE-SPECIFIC LIMITS\n' + direction['avoid']
        + '\n\nPERFORMANCE AND IMAGE FINISH\nNatural live-action dramatic acting: connected facial movement, '
        'small asymmetries, stable gaze, real skin texture, coherent neck and shoulder motion. Expression '
        'must read at normal viewing size. Keep the person responsive through the last frame; avoid '
        'eyebrow pumping, mechanical blinking, head bobbing, pasted-on lips or a frozen torso. Hands '
        'stay out of frame. No added props, cuts, zoom, music, other speech, subtitles, captions, logos, '
        'names, state labels, scores or visible writing. All context and acting directions remain off screen.\n'
    )


def author(row, anchor, index=0):
    directory = ROOT / row['directory']
    if (directory / 'prompt.en.txt').exists():
        audit = load(directory / 'prompt-audit.json')
        if audit['prompt_sha256'] != sha(directory / 'prompt.en.txt') or audit['inputs_sha256'] != sha(directory / 'inputs.json'):
            raise ValueError('Existing prompt or inputs changed')
        return
    inputs = load(directory / 'inputs.json')
    reference = row['location'] != 't1'
    cast = (load(ROOT / anchor['directory'] / 'direction.json')['cast'] if reference else
            cast_text(online_identity_spec(dict(scenario_id=row['scenario_id'],
                                               environment_agent=dict(persona=inputs['persona'])))))
    value = local_direction(inputs, cast)
    save(directory / 'direction.json', value)
    prompt = render_prompt(value, inputs['exact_line'], reference)
    if row.get('reference_image_directory'):
        prompt = still_identity_performance_prompt(prompt, duration=5)
    elif reference:
        prompt = fresh_performance_prompt(prompt, duration=5)
    if prompt.count(inputs['exact_line']) != 1:
        raise ValueError('Dialogue must occur once')
    (directory / 'prompt.en.txt').write_text(prompt)
    save(directory / 'prompt-audit.json', dict(prompt_sha256=sha(directory / 'prompt.en.txt'),
        inputs_sha256=sha(directory / 'inputs.json'), director_sha256=sha(DIRECTOR),
        mode=inputs['mode'], prompt_words=len(prompt.split()), human_review='pending',
        authoring='local_state_interpretation', dialogue_contract='verbatim_first_v3', external_text_model_calls=0,
        motion_contract='original_still_v1' if row.get('reference_image_directory') else ('next_shot_v1' if reference else 'text_only_native_v1'),
        reference_image_directory=row.get('reference_image_directory'),
        implementation_sha256=sha(ROOT / 'environment/state_performance.py')))


def revise_unsubmitted(manifest):
    """Refresh local prompts only where no paid submission has ever started."""
    anchors = {r['scenario_id']: r for r in manifest['nodes'] if r['location'] == 't1'}
    for row in manifest['nodes']:
        directory = ROOT / row['directory']
        if (directory / 'provider-state.json').exists():
            continue
        for name in ('prompt.en.txt', 'prompt-audit.json', 'direction.json'):
            (directory / name).unlink(missing_ok=True)
        author(row, anchors[row['scenario_id']])


def set_reference(node_id, directory):
    with (OUT / '.manifest.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest = load(OUT / 'manifest.json')
        row = next(r for r in manifest['nodes'] if r['node_id'] == node_id)
        row['reference_directory'] = directory
        save(OUT / 'manifest.json', manifest)
        return row


def silent_reference(sid, exclude_node=None):
    base = ROOT / 'data/gpt50/experiment/seedance_state_online_v4/nodes'
    candidates = sorted(base.glob(sid+'--*'), key=lambda p: (
        {'guarded_withdrawal': 0, 'firm_boundary': 1, 'open_engagement': 2}.get(p.name.split('--')[-1], 3), p.name))
    for directory in candidates:
        if directory.name == exclude_node:
            continue
        screen, state = directory / 'qa/audio_screen.json', directory / 'provider-state.json'
        if not screen.exists() or not state.exists():
            continue
        a, s = load(screen), load(state)
        if (s.get('status') == 'downloaded' and a.get('machine_screen_passed') is True
            and not a.get('transcript') and a.get('source_native_sha256') == s.get('video_sha256')
            and sha(directory / 'native.mp4') == s['video_sha256']):
            return str(directory.relative_to(ROOT))
    directory = ROOT / 'data/gpt50/experiment/seedance_state_online_v4/references' / (sid+'--silent_identity')
    if native_video_only_reference(directory):
        return str(directory.relative_to(ROOT))
    return None


def native_video_only_reference(directory):
    state_path, screen_path = directory / 'provider-state.json', directory / 'reference-screen.json'
    if not state_path.exists() or not screen_path.exists():
        return False
    state, screen = load(state_path), load(screen_path)
    return (state.get('status') == 'downloaded' and state.get('request', {}).get('generate_audio') is False
        and screen.get('version') == 'provider_native_video_only_v1' and screen.get('audio_stream_count') == 0
        and screen.get('provider_generate_audio') is False
        and sha(directory / 'native.mp4') == state.get('video_sha256') == screen.get('source_native_sha256'))


def native_frame_reference(directory):
    """Trust only the provider-returned original frame, never a local extraction."""
    paths = [directory / name for name in ('provider-state.json', 'frame-receipt.json', 'native-last-frame.jpg')]
    if not all(path.is_file() for path in paths):
        raise ValueError('Original provider frame is incomplete')
    state, receipt = load(paths[0]), load(paths[1])
    url = state.get('latest_query_response', {}).get('content', {}).get('last_frame_url', '')
    if (state.get('status') != 'downloaded' or state.get('request', {}).get('return_last_frame') is not True
        or receipt.get('version') != 'provider_native_last_frame_v1'
        or receipt.get('provider_return_last_frame') is not True
        or receipt.get('source_native_sha256') != state.get('video_sha256')
        or sha(directory / 'native.mp4') != state['video_sha256']
        or receipt.get('frame_sha256') != sha(paths[2])
        or urlparse(url).scheme != 'https' or not urlparse(url).netloc):
        raise ValueError('Original provider frame provenance or integrity failed')
    return url


def repair_failed_quality(node_id, silent_reference=None, max_repairs=2):
    """Explicit, bounded retry of a completed output; preserve all old evidence."""
    from offline.revision_checks import audio_evidence_valid, sync_evidence_valid
    if max_repairs not in (1, 2, 3):
        raise ValueError('Quality repair limit must be bounded by three')
    if silent_reference:
        reference = ROOT / silent_reference
        if not reference.resolve().is_relative_to(ROOT / 'data/gpt50/experiment/seedance_state_online_v4'):
            raise ValueError('Use a current original online model output as the silent reference')
        if not native_video_only_reference(reference):
            screen, native_state = load(reference / 'qa/audio_screen.json'), load(reference / 'provider-state.json')
            if (screen.get('machine_screen_passed') is not True or screen.get('transcript')
                or screen.get('source_native_sha256') != sha(reference / 'native.mp4')
                or native_state.get('status') != 'downloaded' or native_state['video_sha256'] != sha(reference / 'native.mp4')):
                raise ValueError('Silent native continuity reference has not passed screening')
    manifest = prepare()
    row = next(r for r in manifest['nodes'] if r['node_id'] == node_id)
    directory = ROOT / row['directory']
    with (directory / '.generation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = load(directory / 'provider-state.json')
        if state.get('status') != 'downloaded' or sha(directory / 'native.mp4') != state['video_sha256']:
            raise ValueError('Only a completed, intact output can be explicitly repaired')
        audio = load(directory / 'qa/audio_screen.json')
        sync = load(directory / 'qa/lipsync_screen.json')
        if audio_evidence_valid(audio) and sync_evidence_valid(sync):
            raise ValueError('Passing output does not require a quality repair')
        attempts = directory / 'attempts'
        number = len(list(attempts.glob('*'))) + 1
        if number > max_repairs:
            raise ValueError('Quality repairs exhausted; inspect before further generation')
        archive = attempts / f'{number:02d}'
        archive.mkdir(parents=True)
        for path in list(directory.iterdir()):
            if path.name in {'inputs.json', 'provenance.json', 'attempts'} or path.name.startswith('.'):
                continue
            shutil.move(str(path), archive / path.name)
        for name in ('inputs.json', 'provenance.json'):
            shutil.copy2(directory / name, archive / name)
        save(archive / 'retirement.json', dict(reason='independent_native_audio_or_lipsync_screen_failed',
            audio_pass=audio_evidence_valid(audio), sync_pass=sync_evidence_valid(sync),
            retired_at=utc_now(), replacement_attempt=number+1))
        if silent_reference or row['location'] == 't1':
            # Keep the same original fictional actor even when the anchor's
            # spoken words were incorrect. No modified reference is submitted.
            row['reference_directory'] = silent_reference or str(archive.relative_to(ROOT))
            set_reference(node_id, row['reference_directory'])
        anchor = next(r for r in manifest['nodes'] if r['scenario_id'] == row['scenario_id'] and r['location'] == 't1')
        if row['location'] == 't1':
            inputs = load(directory / 'inputs.json')
            direction = local_direction(inputs, load(archive / 'direction.json')['cast'])
            save(directory / 'direction.json', direction)
            (directory / 'prompt.en.txt').write_text(render_prompt(direction, row['exact_line'], True))
            save(directory / 'prompt-audit.json', dict(prompt_sha256=sha(directory / 'prompt.en.txt'),
                inputs_sha256=sha(directory / 'inputs.json'), director_sha256=sha(DIRECTOR),
                human_review='pending', authoring='local_state_interpretation', dialogue_contract='verbatim_first_v3',
                external_text_model_calls=0, implementation_sha256=sha(ROOT / 'environment/state_performance.py')))
        else:
            author(row, anchor)
        previous_audit = load(archive / 'prompt-audit.json')
        if previous_audit.get('motion_refresh_plan') or previous_audit.get('still_refresh_plan'):
            current_audit = load(directory / 'prompt-audit.json')
            for key in ('motion_refresh_plan', 'still_refresh_plan'):
                if previous_audit.get(key):
                    current_audit[key] = previous_audit[key]
            save(directory / 'prompt-audit.json', current_audit)
    return row, anchor


def generate(row, anchor, submit_new=False):
    directory = ROOT / row['directory']
    state_path = directory / 'provider-state.json'
    output = directory / 'native.mp4'
    # Kernel lock prevents two CLI sessions from creating duplicate paid tasks.
    with (directory / '.generation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = load(state_path) if state_path.exists() else {}
        if state.get('status') == 'downloaded':
            if sha(output) != state['video_sha256']:
                raise ValueError('Downloaded video integrity mismatch')
            return
        if state and not state.get('task_id'):
            raise ValueError('Prior submission has no task ID; investigate, never auto-resubmit')
        config = load(ROOT / 'configs/gpt50_experiment/video_completion.active.json')
        client = SeedanceClient(Path(config['key_file']).read_text().strip())
        if not state.get('task_id'):
            if not submit_new:
                raise ValueError('--submit-new required for a new paid task')
            prompt_path = directory / 'prompt.en.txt'
            audit = load(directory / 'prompt-audit.json')
            if sha(prompt_path) != audit['prompt_sha256']:
                raise ValueError('Prompt changed after authoring')
            spec = dict(prompt=prompt_path.read_text(), duration_seconds=row.get('duration_seconds', 5),
                        generate_audio=row.get('location') != 'identity_reference', ratio='16:9')
            frame_url = None
            if row.get('reference_image_directory'):
                frame_dir = ROOT / row['reference_image_directory']
                frame_url = native_frame_reference(frame_dir)
                if row['location'] == 'online':
                    request = load(directory / 'request.json')
                    request.pop('reference_video_file', None)
                    request['reference_image_file'] = str(frame_dir / 'native-last-frame.jpg')
                    save(directory / 'request.json', request)
            elif row['location'] != 't1' or row.get('reference_directory'):
                reference_dir = row.get('reference_directory')
                if row['location'] == 'online' and not reference_dir:
                    reference_dir = silent_reference(row['scenario_id'], row['node_id'])
                anchor_dir = ROOT / (reference_dir or anchor['directory'])
                anchor_state = load(anchor_dir / 'provider-state.json')
                if anchor_state['status'] != 'downloaded' or sha(anchor_dir / 'native.mp4') != anchor_state['video_sha256']:
                    raise ValueError('Native anchor not ready or altered')
                spec.update(reference_video_file=str(anchor_dir / 'native.mp4'),
                            reference_video_transport='provided_url',
                            reference_video_url=video_url(anchor_state['latest_query_response']))
                if row['location'] == 'online':
                    request = load(directory / 'request.json')
                    request['reference_video_file'] = spec['reference_video_file']
                    save(directory / 'request.json', request)
            payload = validate_payload(materialize_local_references(
                seedance_payload(spec, model=config['model'], resolution='720p', reference_root=ROOT)))
            if row.get('return_last_frame') is True:
                payload['return_last_frame'] = True
            if frame_url:
                payload['content'].append(dict(type='image_url', role='reference_image', image_url=dict(url=frame_url)))
            state = dict(status='submitting', request=payload, node_id=row['node_id'],
                         prompt_sha256=audit['prompt_sha256'], submission_started_at=utc_now(),
                         max_new_tasks=1, authorization='User approved all offline and online replacements: 全部完成，标价先不考虑')
            save(state_path, state)  # Durable before POST: ambiguous submissions never retry.
            try:
                response = client.submit(payload)
            except Exception as exc:
                state.update(status='submission_error_needs_review', error=str(exc)[:2500])
                save(state_path, state)
                raise
            state.update(task_id=response['id'], submit_response=response, status='submitted')
            save(state_path, state)
        deadline = time.monotonic() + 1800
        while True:
            try:
                result = client.query(state['task_id'])
            except requests.RequestException:
                if time.monotonic() > deadline:
                    raise
                time.sleep(15)
                continue
            state.update(latest_query_response=result, status=result.get('status'), last_polled_at=utc_now())
            save(state_path, state)
            if state['status'] == 'succeeded':
                break
            if state['status'] in {'failed', 'cancelled', 'expired'}:
                raise ValueError(f'Provider terminal status: {state["status"]}')
            if time.monotonic() > deadline:
                raise TimeoutError('Existing task still running; resume by task ID')
            time.sleep(15)
        client.download(video_url(result), output)
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
            '-show_format', '-of', 'json', str(output)]))
        state.update(status='downloaded', video_file=str(output), video_sha256=sha(output),
                     video_bytes=output.stat().st_size, downloaded_at=utc_now())
        save(state_path, state)
        save(directory / 'probe.json', probe)
        duration = row.get('duration_seconds', 5)
        if not duration-.1 <= float(probe['format']['duration']) <= duration+.2:
            raise ValueError('Native duration outside requested tolerance')
        streams = {s['codec_type'] for s in probe['streams']}
        if row.get('location') == 'identity_reference':
            if streams != {'video'}:
                raise ValueError('Native silent reference must contain video only')
            save(directory / 'reference-screen.json', dict(version='provider_native_video_only_v1',
                source_native_sha256=state['video_sha256'], audio_stream_count=0,
                provider_generate_audio=False, method='Original provider output; no audio removed locally'))
        elif not {'video', 'audio'} <= streams:
            raise ValueError('Missing native video/audio stream')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'author', 'generate', 'status'])
    parser.add_argument('--scene', action='append')
    parser.add_argument('--node')
    parser.add_argument('--location', choices=['t1', 't2'])
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--submit-new', action='store_true')
    args = parser.parse_args()
    manifest = prepare()
    nodes = manifest['nodes']
    if args.command in {'prepare', 'status'}:
        from collections import Counter
        states = Counter(load(ROOT / n['directory'] / 'provider-state.json')['status']
            if (ROOT / n['directory'] / 'provider-state.json').exists() else 'not_submitted' for n in nodes)
        print(json.dumps(dict(nodes=len(nodes), prompts=sum((ROOT / n['directory'] / 'prompt.en.txt').exists()
            for n in nodes), video_states=dict(states)), ensure_ascii=False))
        return
    scenes = sorted({n['scenario_id'] for n in nodes if not args.scene or n['scenario_id'] in args.scene})
    def work(scene):
        scene_nodes = [n for n in nodes if n['scenario_id'] == scene]
        anchor = next(n for n in scene_nodes if n['location'] == 't1')
        for row in scene_nodes:
            if args.node and args.node != row['node_id']:
                continue
            if args.location and row['location'] != args.location:
                continue
            if args.command == 'author':
                author(row, anchor)
            else:
                generate(row, anchor, args.submit_new)
            print(json.dumps(dict(node=row['node_id'], stage=args.command, status='done')), flush=True)
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        jobs = {pool.submit(work, scene): scene for scene in scenes}
        for f in as_completed(jobs):
            try:
                f.result()
            except Exception as exc:
                # Error text is persisted privately; URLs are not printed.
                failed.append(dict(scene=jobs[f], error_type=type(exc).__name__))
                save(OUT / 'errors' / f'{jobs[f]}-{args.command}.json', dict(error=str(exc)))
                print(json.dumps(dict(scene=jobs[f], stage=args.command, status='failed', error_type=type(exc).__name__)), flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
