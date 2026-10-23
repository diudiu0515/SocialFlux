"""Replace online render assets while preserving every trigger/profile binding.

Preserves the new offline fictional actor per scene. Native continuity references
are separate from published assets; no trigger-rule or threshold edits.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.seedance_state_batch import OUT, prepare, load, save, sha, generate, utc_now
from environment.online_video_assets import build_online_asset_request, online_identity_spec

OLD = ROOT / 'data/gpt50/experiment/multimodal_delivery_v1/online_multimodal/manifest.json'
TARGET = ROOT / 'data/gpt50/experiment/seedance_state_online_v4'


def prepare_online():
    offline = prepare()
    target = TARGET / 'manifest.json'
    if target.exists():
        result = load(target)
        if result['source_manifest_sha256'] != sha(OLD):
            raise ValueError('Original online manifest changed during replacement')
        return result
    old = load(OLD)
    anchors = {r['scenario_id']: r for r in offline['nodes'] if r['location'] == 't1'}
    records = []
    for record in old['requests']:
        sid, family = record['scenario_id'], record['event_family']
        anchor = anchors[sid]
        inputs = load(ROOT / anchor['directory'] / 'inputs.json')
        scenario = dict(scenario_id=sid, environment_agent=dict(persona=inputs['persona']))
        identity = online_identity_spec(scenario)
        if sid == 'GPT50_001':
            # The approved text-only pilot introduced this original identity.
            identity.update(appearance='an adult man in his early forties with short curly brown hair and light stubble',
                            wardrobe='an ordinary navy sweater',
                            background='a quiet generic dispatch office with a neutral blurred wall and soft practical side lighting')
        directory = TARGET / 'nodes' / (sid + '--' + family)
        request = build_online_asset_request(scenario, family, duration_seconds=record['duration_seconds'],
            reference_video_file=str(ROOT / anchor['directory'] / 'native.mp4'), identity_override=identity)
        save(directory / 'inputs.json', dict(scenario_id=sid, event_family=family, identity=identity,
            source_profile_sha256=record['scenario_profile_sha256'], response_neutral=True,
            state_scope='unchanged trigger event-family meaning, no invented current-state snapshot'))
        save(directory / 'request.json', request)
        (directory / 'prompt.en.txt').write_text(request['prompt'])
        save(directory / 'prompt-audit.json', dict(prompt_sha256=sha(directory / 'prompt.en.txt'),
            inputs_sha256=sha(directory / 'inputs.json'),
            authoring='local_event_state_direction', external_text_model_calls=0,
            implementation_sha256=sha(ROOT / 'environment/state_performance.py')))
        row = deepcopy(record)
        for key in ('video_sha256', 'video_bytes', 'structural_metadata', 'provider_error'):
            row.pop(key, None)
        row.update(node_id=sid+'--'+family, location='online', directory=str(directory.relative_to(ROOT)),
                   request_file=str((directory / 'request.json').relative_to(ROOT / 'data/gpt50/experiment')),
                   video_file=str((directory / 'web.mp4').relative_to(ROOT / 'data/gpt50/experiment')),
                   status='request_ready', prompt_id=request['prompt_id'], anchor_node_id=anchor['node_id'],
                   source_video_sha256=record.get('video_sha256'))
        records.append(row)
    manifest = deepcopy(old)
    manifest.update(requests=records, prompt_id='online_nonverbal_state_performance_v4',
        active_prompt_id='online_nonverbal_state_performance_v4', asset_version='online_nonverbal_v1',
        generated_count=0, structurally_passed_count=0, human_review_passed_count=0,
        provider_status='request_ready', source_manifest_sha256=sha(OLD),
        state_performance_sha256=sha(ROOT / 'environment/state_performance.py'),
        trigger_policy_unchanged=True, trigger_code_sha256=sha(ROOT / 'environment/online_multimodal.py'),
        trigger_settings=load(ROOT / 'configs/multimodal_generation.json')['online'],
        created_at_utc=utc_now(), native_generated_audio=True, published=False)
    save(target, manifest)
    return manifest


def finalize():
    """Bind only checked native outputs; do not activate a partial inventory."""
    block = TARGET / 'visual-quality-block.json'
    if block.exists() and load(block).get('status') != 'resolved':
        raise ValueError('Online visual quality review is unresolved; publication is blocked')
    manifest = prepare_online()
    visual = load(block) if block.exists() else None
    if visual:
        audit_path = ROOT / visual['motion_audit_file']
        if sha(audit_path) != visual['motion_audit_sha256']:
            raise ValueError('Motion review changed after approval')
        motion = load(audit_path)
        if motion['unresolved']:
            raise ValueError('Motion review contains unresolved videos')
        compared = {r['node']: r for r in motion['results']}
        for row in manifest['requests']:
            evidence = compared[row['node_id']]
            state = load(ROOT / row['directory'] / 'provider-state.json')
            if (evidence.get('status') not in ('compared', 'original_still_reference') or evidence.get('reference_motion_suspected')
                or evidence['source_native_sha256'] != state['video_sha256']):
                raise ValueError('Online motion review failed or stale: '+row['node_id'])
    original = {r['media_asset_id']: r for r in load(OLD)['requests']}
    if (len(manifest['requests']) != 326
        or manifest['trigger_code_sha256'] != sha(ROOT / 'environment/online_multimodal.py')
        or manifest['trigger_settings'] != load(ROOT / 'configs/multimodal_generation.json')['online']):
        raise ValueError('Online count or frozen trigger policy changed')
    assets = TARGET / 'assets'
    assets.mkdir(exist_ok=True)
    for row in manifest['requests']:
        old = original[row['media_asset_id']]
        for key in ('request_id', 'scenario_id', 'event_family', 'media_asset_id', 'scenario_profile_sha256', 'duration_seconds'):
            if old[key] != row[key]:
                raise ValueError('Online trigger binding changed: '+key)
        directory = ROOT / row['directory']
        state = load(directory / 'provider-state.json')
        receipt = load(directory / 'web-receipt.json')
        screen = load(directory / 'qa/audio_screen.json')
        if (state.get('status') != 'downloaded' or sha(directory / 'native.mp4') != state['video_sha256']
            or receipt['source_native_sha256'] != state['video_sha256'] or not receipt['structural_pass']
            or receipt['web_sha256'] != sha(directory / 'web.mp4')
            or screen.get('version') != 'seedance_nonverbal_asr_v1'
            or screen.get('source_native_sha256') != state['video_sha256']
            or screen.get('sha256') != sha(directory / 'qa/speech.wav')
            or screen.get('machine_screen_passed') is not True or screen.get('transcript')
            or screen.get('unprompted') is not True):
            raise ValueError('Online native checks missing, stale or failed: '+row['node_id'])
        target = assets / (receipt['web_sha256']+'.mp4')
        if target.exists():
            if sha(target) != receipt['web_sha256']:
                raise ValueError('Existing delivery asset changed')
        else:
            os.link(directory / 'web.mp4', target)
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(target)]))
        video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
        n, d = map(int, video['avg_frame_rate'].split('/'))
        row.update(video_file=str(target.relative_to(ROOT / 'data/gpt50/experiment')),
            video_sha256=receipt['web_sha256'], video_bytes=target.stat().st_size,
            status='generated_structural_pass', native_video_sha256=state['video_sha256'],
            prompt_sha256=sha(directory / 'prompt.en.txt'), human_review='pending',
            structural_metadata=dict(duration_seconds_actual=receipt['duration_seconds'], width=video['width'],
                height=video['height'], fps=n/d, audio_stream_count=1, audio_codec=audio['codec_name'],
                audio_sample_rate=audio['sample_rate'], audio_channels=audio['channels']))
    manifest.pop('published', None)  # Publication receipts are separate; this bound manifest stays immutable.
    manifest.update(generated_count=326, structurally_passed_count=326, provider_status='complete',
        provider_failure_count=0, provider_failures=[], validation_errors=[], network_requests_performed=True,
        prompt_sha256=sha(ROOT / 'prompts/online_nonverbal_state_performance_v4.txt'),
        active_prompt_sha256=sha(ROOT / 'prompts/online_nonverbal_state_performance_v4.txt'),
        state_performance_sha256=sha(ROOT / 'environment/state_performance.py'),
        motion_review_sha256=sha(block) if visual else None,
        verified_at_utc=utc_now(), publication_state_at_verification='not_published', human_review_passed_count=0)
    from evaluation.t4_asset_coverage import audit_asset_coverage, require_complete_assets
    report = audit_asset_coverage(manifest, ROOT / 'data/gpt50/experiment')
    require_complete_assets(report)
    save(TARGET / 'manifest.json', manifest)
    save(TARGET / 'coverage.json', report)
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['prepare', 'generate', 'finalize'])
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--submit-new', action='store_true')
    p.add_argument('--wait-offline', action='store_true')
    p.add_argument('--wait-for-anchors', action='store_true')
    p.add_argument('--scene')
    args = p.parse_args()
    if args.command == 'finalize':
        finalize()
        print(json.dumps(dict(nodes=326, checked=True, trigger_policy_unchanged=True)))
        return
    manifest = prepare_online()
    if args.command == 'prepare':
        print(json.dumps(dict(nodes=len(manifest['requests']), trigger_policy_unchanged=True)))
        return
    offline = prepare()
    if args.wait_offline:
        # Share the provider's concurrency budget with the offline campaign.
        process = load(ROOT / 'build/seedance-offline-refresh-20261023-process.json')
        while True:
            proc = Path('/proc') / str(process['pid']) / 'cmdline'
            if not proc.exists() or b'seedance_state_batch.py' not in proc.read_bytes():
                break
            time.sleep(20)
    anchors = {r['scenario_id']: r for r in offline['nodes'] if r['location'] == 't1'}
    selected = [r for r in manifest['requests'] if not args.scene or r['scenario_id'] == args.scene]
    # First make one silent native continuity source per scene. Other families
    # then reuse that output, preventing the spoken anchor leaking old dialogue.
    first = {}
    for r in selected:
        first.setdefault(r['scenario_id'], r['event_family'])
    selected.sort(key=lambda r: (r['event_family'] != first[r['scenario_id']], r['scenario_id'], r['event_family']))
    failures = []
    def work(row):
        if args.wait_for_anchors:
            anchor_dir = ROOT / anchors[row['scenario_id']]['directory']
            deadline = time.monotonic() + 7200
            while True:
                p = anchor_dir / 'provider-state.json'
                state = load(p) if p.exists() else {}
                if state.get('status') == 'downloaded':
                    break
                if state.get('status') in {'failed', 'cancelled', 'expired', 'submission_error_needs_review'}:
                    raise ValueError('Scene anchor failed; do not submit dependent tasks')
                if time.monotonic() > deadline:
                    raise TimeoutError('Scene anchor not ready')
                time.sleep(20)
        generate(row, anchors[row['scenario_id']], args.submit_new)
        print(json.dumps(dict(node=row['node_id'], stage='online_generate', status='done')), flush=True)
    with ThreadPoolExecutor(max_workers=min(24, max(1, args.workers))) as pool:
        futures = {pool.submit(work, row): row for row in selected}
        for future in as_completed(futures):
            row = futures[future]
            try:
                future.result()
            except Exception as exc:
                failures.append(dict(node=row['node_id'], type=type(exc).__name__))
                save(TARGET / 'errors' / (row['node_id']+'.json'), dict(error=str(exc)))
                print(json.dumps(dict(node=row['node_id'], status='failed', type=type(exc).__name__)), flush=True)
    save(TARGET / 'generation-summary.json', dict(failures=failures, attempted=len(selected), updated_at=utc_now()))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
