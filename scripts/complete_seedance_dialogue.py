"""Complete exact offline speech using screened silent native continuity clips.

Silent references reuse checked Online outputs; a provider-generated video-only
identity reference is available when every same-scene output retains speech.
No provider rejection or ambiguous submission is retried. Completed clips may
receive at most two explicit quality repairs (the diagnosed pilot at most three).
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
import time

from scripts.seedance_state_batch import ROOT, OUT, load, save, sha, prepare, generate, set_reference, repair_failed_quality, utc_now, silent_reference, native_frame_reference
from offline.revision_checks import audio_evidence_valid, sync_evidence_valid


def quality(directory):
    paths = [directory / 'qa' / name for name in ('audio_screen.json', 'lipsync_screen.json')]
    if not all(p.exists() for p in paths):
        return None
    return audio_evidence_valid(load(paths[0])) and sync_evidence_valid(load(paths[1]))


def complete(row, anchor):
    directory = ROOT / row['directory']
    with (directory / '.pipeline.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if quality(directory) is True:
            return 'already_passed'
        deadline = time.monotonic() + 10800
        reference = None
        frame_reference = row.get('reference_image_directory')
        if frame_reference:
            native_frame_reference(ROOT / frame_reference)
        while reference is None and not frame_reference:
            reference = silent_reference(row['scenario_id'])
            if time.monotonic() > deadline:
                raise TimeoutError('No screened silent native continuity source is available')
            if reference is None:
                time.sleep(15)
        while True:
            state_path = directory / 'provider-state.json'
            state = load(state_path) if state_path.exists() else {}
            if state.get('status') == 'downloaded':
                result = quality(directory)
                if result is True:
                    return 'passed'
                if result is None:
                    if time.monotonic() > deadline:
                        raise TimeoutError('Independent audio/sync checks are incomplete')
                    time.sleep(15)
                    continue
                row, anchor = repair_failed_quality(row['node_id'], silent_reference=reference,
                    max_repairs=3 if row['node_id'] == 'GPT50_003-t2-14ffe66f849cc752' else 2)
                print(json.dumps(dict(node=row['node_id'], stage='repair', continuity='silent_native_output')), flush=True)
            elif not state and not frame_reference:
                row = set_reference(row['node_id'], reference)
            generate(row, anchor, submit_new=True)
            print(json.dumps(dict(node=row['node_id'], stage='downloaded_waiting_checks')), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--node')
    p.add_argument('--location', choices=['t1', 't2'], default='t2')
    p.add_argument('--workers', type=int, default=4)
    args = p.parse_args()
    manifest = prepare()
    anchors = {r['scenario_id']: r for r in manifest['nodes'] if r['location'] == 't1'}
    rows = [r for r in manifest['nodes'] if r['location'] == args.location and (not args.node or r['node_id'] == args.node)]
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, min(8, args.workers))) as pool:
        jobs = {pool.submit(complete, row, anchors[row['scenario_id']]): row for row in rows}
        for future in as_completed(jobs):
            row = jobs[future]
            try:
                print(json.dumps(dict(node=row['node_id'], status=future.result())), flush=True)
            except Exception as exc:
                failed.append(dict(node=row['node_id'], type=type(exc).__name__))
                save(OUT / 'errors' / (row['node_id']+'-complete.json'), dict(type=type(exc).__name__, error=str(exc), at=utc_now()))
                print(json.dumps(dict(node=row['node_id'], status='needs_review', type=type(exc).__name__)), flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
