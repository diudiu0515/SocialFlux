"""Bounded quality repair of completed Online clips that contain speech."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
import shutil
import time

from scripts.seedance_state_batch import ROOT, OUT, load, save, sha, generate, silent_reference, native_video_only_reference, native_frame_reference, utc_now
from scripts.refresh_online_state_videos import TARGET


def repair(row, anchor, max_repairs=2, reference_override=None, allow_spoken_reference=False):
    if max_repairs not in (1, 2, 3, 4):
        raise ValueError("Quality repair limit must be bounded by four")
    directory = ROOT / row['directory']
    frame_reference = load(directory / 'prompt-audit.json').get('reference_image_directory')
    if frame_reference:
        native_frame_reference(ROOT / frame_reference)
        row = dict(row, reference_image_directory=frame_reference)
    deadline = time.monotonic() + 3600
    with (directory / '.pipeline.lock').open('a') as pipeline:
        fcntl.flock(pipeline, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            state = load(directory / 'provider-state.json')
            if state.get('status') != 'downloaded':
                generate(row, anchor, submit_new=False)
                continue
            p = directory / 'qa/audio_screen.json'
            if not p.exists():
                if time.monotonic() > deadline:
                    raise TimeoutError('Online audio check incomplete')
                time.sleep(15)
                continue
            screen = load(p)
            if screen.get('source_native_sha256') != state['video_sha256'] or sha(directory / 'native.mp4') != state['video_sha256']:
                raise ValueError('Stale or changed Online input')
            if screen.get('machine_screen_passed') is True and not screen.get('transcript'):
                return
            reference = frame_reference or reference_override or silent_reference(row['scenario_id'], row['node_id'])
            if reference_override and not frame_reference:
                candidate = (ROOT / reference_override).resolve()
                if (candidate.parent not in {(TARGET / 'nodes').resolve(), (TARGET / 'references').resolve()}
                    or not candidate.name.startswith(row['scenario_id']+'--')
                    or candidate.name == row['node_id']):
                    raise ValueError('Reference override must be another native output from the same scene')
                if not native_video_only_reference(candidate):
                    rs, ra = load(candidate / 'provider-state.json'), load(candidate / 'qa/audio_screen.json')
                    if (rs.get('status') != 'downloaded'
                        or (not allow_spoken_reference and (ra.get('machine_screen_passed') is not True or ra.get('transcript')))
                        or sha(candidate / 'native.mp4') != rs['video_sha256']
                        or ra.get('source_native_sha256') != rs['video_sha256']):
                        raise ValueError('Reference override is changed or has not passed its required input checks')
            if not reference:
                raise ValueError('No screened silent source; inspect scene before repair')
            with (directory / '.generation.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                attempts = directory / 'attempts'
                number = len(list(attempts.glob('*'))) + 1
                if number > max_repairs:
                    raise ValueError("Silent quality repairs exhausted; inspect before further generation")
                archive = attempts / f'{number:02d}'
                archive.mkdir(parents=True)
                for path in list(directory.iterdir()):
                    if path.name == 'attempts' or path.name.startswith('.'):
                        continue
                    if path.name in {'inputs.json', 'request.json', 'prompt.en.txt', 'prompt-audit.json'}:
                        shutil.copy2(path, archive / path.name)
                    else:
                        shutil.move(str(path), archive / path.name)
                save(archive / 'retirement.json', dict(reason='Unrequested speech detected in native output',
                    at=utc_now(), reference_directory=reference, reference_scope='original_still' if frame_reference else 'visual_only',
                    reference_audio_screen_required=not allow_spoken_reference, replacement_attempt=number+1))
                prompt_path = directory / 'prompt.en.txt'
                prompt = prompt_path.read_text()
                # The native model can turn breath direction into a voiced syllable.
                # Preserve facial acting and regenerate a room-tone-only soundtrack.
                prompt = prompt.replace('with synchronized nonverbal audio', 'with a quiet room-tone soundtrack')
                start = prompt.index('NATIVE AUDIO\n')
                end = prompt.index('\n\nIMAGE AND PERFORMANCE FINISH', start)
                prompt = prompt[:start] + (
                    'NATIVE AUDIO\nGenerate only faint continuous indoor room tone for the entire shot. '
                    'No human voice or human vocal sound at any point: no words, syllables, whispers, '
                    'murmurs, humming, audible breath, sighs, laughter or offscreen speaker. '
                    'Breathing is visible only in the small natural chest movement. The lips stay gently '
                    'closed throughout. Replace the reference soundtrack completely; retain only the '
                    'fictional visual identity. Keep this a silent listening reaction.'
                ) + prompt[end:]
                if reference_override:
                    prompt = ('SOUNDTRACK CONTRACT: faint steady indoor HVAC room tone only. '
                        'The actor keeps their lips gently closed for all four seconds and makes no '
                        'human vocal sound. Discard the reference audio entirely. Expression comes '
                        'from brows, eyes, jaw tension, gaze and posture.\n\n' + prompt)
                    prompt = prompt.replace('or parts only for an unvoiced breath', 'throughout the reaction')
                prompt_path.write_text(prompt)
                audit = load(directory / 'prompt-audit.json')
                audit.update(prompt_sha256=sha(prompt_path), native_audio_contract='room_tone_only_v1',
                             quality_repair=number)
                save(directory / 'prompt-audit.json', audit)
                request = load(directory / 'request.json')
                request['prompt'] = prompt
                save(directory / 'request.json', request)
            row = dict(row, reference_directory=reference)
            generate(row, anchor, submit_new=True)
            print(json.dumps(dict(node=row['node_id'], stage='repaired_waiting_checks')), flush=True)


def main():
    manifest = load(TARGET / 'manifest.json')
    anchors = {r['scenario_id']: r for r in load(OUT / 'manifest.json')['nodes'] if r['location'] == 't1'}
    rows = []
    for r in manifest['requests']:
        p = ROOT / r['directory'] / 'qa/audio_screen.json'
        if p.exists() and load(p).get('machine_screen_passed') is not True:
            rows.append(r)
    failures = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(repair, r, anchors[r['scenario_id']]): r for r in rows}
        for f in as_completed(jobs):
            row = jobs[f]
            try:
                f.result()
                print(json.dumps(dict(node=row['node_id'], status='passed')), flush=True)
            except Exception as exc:
                failures.append(row['node_id'])
                save(TARGET / 'errors' / (row['node_id']+'-quality.json'), dict(error=str(exc), at=utc_now()))
                print(json.dumps(dict(node=row['node_id'], status='needs_review', type=type(exc).__name__)), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
