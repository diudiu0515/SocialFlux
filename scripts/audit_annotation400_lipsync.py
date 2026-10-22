"""Independent SyncNet measurements of completed local spoken videos."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sys
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_annotation400 import OUT, load, save, sha

TOOL = ROOT / '.local_tools/annotation400-latentsync'
VERSION = 'independent_syncnet_v1'


@contextmanager
def shared_render_lock(directory):
    """Skip a node being rendered; release the shared lock on every exit path."""
    with (directory / 'render.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def current_snapshot(directory, expected_spec):
    """Return a fully bound current render, or None while inputs are changing."""
    try:
        receipts = {name: load(directory / (name + '.json'))
                    for name in ('request', 'speech', 'motion', 'video')}
        hashes = {name: sha(directory / filename) for name, filename in
                  (('audio', 'speech.wav'), ('motion', 'motion.mp4'), ('video', 'video.mp4'))}
        if any(receipt.get('spec_sha256') != expected_spec for receipt in receipts.values()):
            return None
        speech, motion, video = (receipts[name] for name in ('speech', 'motion', 'video'))
        if (speech.get('sha256') != hashes['audio'] or motion.get('sha256') != hashes['motion']
                or video.get('sha256') != hashes['video']
                or motion.get('audio_sha256') != hashes['audio']
                or video.get('audio_sha256') != hashes['audio']
                or video.get('motion_sha256') != hashes['motion']):
            return None
        if not video['structural_metadata']['duration_seconds_actual'] > 0:
            return None
        return {'hashes': hashes, 'video_receipt': video,
                'receipt_sha256': {name: sha(directory / (name + '.json')) for name in receipts}}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # Other asset workers may replace a source receipt independently of the
        # renderer. Incomplete or stale files are retried on the next pass.
        return None


def audit_node(row, *, evaluate, model_hash, sample_seconds=8.0, root=ROOT, tool=TOOL):
    """Measure one stable render; no GPU-specific imports are needed here."""
    request_path = root / row['request_path']
    directory = request_path.parent
    if not directory.is_dir():
        return None
    with shared_render_lock(directory) as acquired:
        if not acquired:
            return None
        snapshot = current_snapshot(directory, row['spec_sha256'])
        if snapshot is None:
            return None
        video = directory / 'video.mp4'
        h = snapshot['hashes']['video']
        output = directory / 'lipsync_screen.json'
        if output.exists():
            try:
                cached = load(output)
            except (OSError, ValueError):
                cached = {}
            if (cached.get('video_sha256') == h and cached.get('version') == VERSION
                    and cached.get('spec_sha256') == row['spec_sha256']
                    and current_snapshot(directory, row['spec_sha256']) == snapshot):
                return cached
        runtime = directory / 'syncnet-runtime'
        runtime.mkdir(exist_ok=True)
        link = runtime / 'checkpoints'
        if not link.exists():
            link.symlink_to(tool / 'checkpoints', target_is_directory=True)
        previous_cwd = Path.cwd()
        try:
            os.chdir(runtime)
            duration = snapshot['video_receipt']['structural_metadata']['duration_seconds_actual']
            sample_duration = min(sample_seconds, duration) if sample_seconds > 0 else duration
            sample_start = max(0.0, (duration - sample_duration) / 2)
            measured_video = video
            if sample_duration < duration:
                measured_video = runtime / 'center-sample.mp4'
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(sample_start),
                    '-i', str(video), '-t', str(sample_duration), '-c:v', 'libx264', '-crf', '18',
                    '-threads', '2', '-c:a', 'aac', '-b:a', '128k', str(measured_video)], check=True)
            offset, confidence = evaluate(str(measured_video), str(runtime / 'temp'))
            result = {'node_id': row['node_id'], 'version': VERSION,
                      'video_sha256': h, 'spec_sha256': row['spec_sha256'],
                      'model': 'SyncNet', 'model_sha256': model_hash,
                      'offset_frames': int(offset), 'frame_rate': 25,
                      'confidence': float(confidence),
                      'measurement_window': {'start_seconds': sample_start, 'duration_seconds': sample_duration,
                                             'complete_clip': sample_duration == duration,
                                             'sample_sha256': sha(measured_video)},
                      'machine_screen_passed': bool(confidence >= 3 and abs(offset) <= 2),
                      'human_review': 'pending'}
            # Recheck the whole chain, including the video SHA, immediately
            # before writing. An out-of-band mutation must not receive a score.
            if current_snapshot(directory, row['spec_sha256']) != snapshot:
                return None
            save(output, result)
            print(json.dumps(result), flush=True)
            return result
        finally:
            os.chdir(previous_cwd)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scene', nargs='*')
    p.add_argument('--watch', action='store_true')
    p.add_argument('--device', default='cuda')
    p.add_argument('--sample-seconds', type=float, default=8.0,
                   help='Centered contiguous sync sample; use 0 for the complete clip')
    a = p.parse_args()
    sys.path.insert(0, str(TOOL))
    from eval.syncnet import SyncNetEval
    from eval.syncnet_detect import SyncNetDetector
    from eval.eval_sync_conf import syncnet_eval
    model = SyncNetEval(device=a.device)
    weights = TOOL / 'checkpoints/auxiliary/syncnet_v2.model'
    model.loadParameters(str(weights))
    model_hash = sha(weights)
    detector = None

    def evaluate(video, temporary):
        nonlocal detector
        if detector is None:
            detector = SyncNetDetector(device=a.device, detect_results_dir='detect_results')
        return syncnet_eval(model, detector, video, temporary)

    rows = [row for row in load(OUT / 'local_av/manifest.json')['nodes']
            if not a.scene or row['scenario_id'] in a.scene]
    while True:
        complete = 0
        results = []
        for row in rows:
            result = audit_node(row, evaluate=evaluate, model_hash=model_hash, sample_seconds=a.sample_seconds)
            if result is None:
                continue
            results.append(result)
            complete += 1
        save(OUT / 'local_av/lipsync_screen_summary.json', {
            'checked': len(results), 'required': len(rows),
            'passed': sum(r['machine_screen_passed'] for r in results),
            'failed': [r for r in results if not r['machine_screen_passed']],
            'human_review': 'pending'})
        if not a.watch or complete == len(rows):
            return
        time.sleep(20)


if __name__ == '__main__':
    main()
