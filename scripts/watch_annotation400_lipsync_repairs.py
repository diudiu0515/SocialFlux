"""Append bounded 1.0→1.5 repairs and watch current SyncNet results; no GPU work."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_annotation400 import OUT, load, sha
from scripts.audit_annotation400_lipsync import current_snapshot, shared_render_lock, VERSION

DIRECTORY = OUT / 'local_av'
PILOT = OUT / 'local_av_quality/GPT50_002-ending-guidance1p5/comparison_report.json'


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    """Readers see the complete previous or complete new index."""
    path = Path(path)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix=path.name + '.', suffix='.tmp',
                                     encoding='utf-8', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def append_repair(path, node_id, entry):
    """Never replace a pre-existing repair, including one supplied by a human."""
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        index = load(path) if path.exists() else {'format': 'local_lipsync_parameter_repairs_v1', 'nodes': {}}
        if node_id in index['nodes']:
            return False
        index['nodes'][node_id] = entry
        atomic_json(path, index)
        return True


def current_screen(directory, row, snapshot):
    try:
        path = directory / 'lipsync_screen.json'
        raw = path.read_bytes()
        screen = json.loads(raw)
        if (screen.get('video_sha256') != snapshot['hashes']['video'] or screen.get('node_id') != row['node_id']
                or screen.get('spec_sha256') != row['spec_sha256'] or screen.get('version') != VERSION):
            return None
        confidence, offset = float(screen['confidence']), float(screen['offset_frames'])
        if not math.isfinite(confidence) or not math.isfinite(offset) or not offset.is_integer():
            return None
        return {'screen': screen, 'screen_sha256': hashlib.sha256(raw).hexdigest(),
                'passed': confidence >= 3 and abs(offset) <= 2}
    except (OSError, ValueError, TypeError, KeyError):
        return None


def repair_entry(measurement, video, pilot_sha):
    screen = measurement['screen']
    return {'guidance_scale': 1.5,
        'reason': 'Current independent SyncNet confidence is below 3 or absolute offset exceeds 2 frames. '
                  'The controlled GPT50_002 ending comparison improved confidence from 2.6046 to 5.1303 '
                  'with zero offset at guidance 1.5 while retaining appearance. Only guidance changes; '
                  'the frozen speech, motion, identity, seed and 20 inference steps remain unchanged.',
        'original_screen_sha256': measurement['screen_sha256'], 'original_confidence': screen['confidence'],
        'original_offset_frames': screen['offset_frames'], 'original_video_sha256': screen['video_sha256'],
        'original_guidance_scale': video['guidance_scale'], 'spec_sha256': video['spec_sha256'],
        'comparison_evidence_path': str(PILOT.relative_to(ROOT)), 'comparison_evidence_sha256': pilot_sha,
        'created_at': now()}


def scan(rows, state, emit, *, directory=DIRECTORY, root=ROOT, pilot_sha):
    repairs_path = directory / 'lipsync_repairs.json'
    repairs = load(repairs_path).get('nodes', {}) if repairs_path.exists() else {}
    alerts = set(state.get('alerted_screen_sha256', []))
    repaired_passes = set(state.get('reported_repair_pass_video_sha256', []))
    counts = {'required': len(rows), 'stable_videos': 0, 'current_sync_passed': 0,
              'pending_rerender': 0, 'pending_generation': 0, 'awaiting_sync_screen': 0,
              'locked_render_nodes': 0, 'failed_after_guidance1p5': 0}
    pending, failed_after_repair = [], []
    for row in rows:
        node = row['node_id']
        node_directory = (root / row['request_path']).parent
        if not node_directory.is_dir():
            counts['pending_generation'] += 1
            pending.append({'node_id': node, 'status': 'pending_generation'})
            continue
        with shared_render_lock(node_directory) as acquired:
            if not acquired:
                counts['pending_generation'] += 1
                counts['locked_render_nodes'] += 1
                pending.append({'node_id': node, 'status': 'render_locked'})
                continue
            snapshot = current_snapshot(node_directory, row['spec_sha256'])
            if snapshot is None:
                counts['pending_generation'] += 1
                pending.append({'node_id': node, 'status': 'waiting_for_current_render'})
                continue
            counts['stable_videos'] += 1
            video = snapshot['video_receipt']
            measurement = current_screen(node_directory, row, snapshot)
            target = repairs.get(node, {}).get('guidance_scale', 1.0)
            if measurement is not None and current_snapshot(node_directory, row['spec_sha256']) != snapshot:
                counts['stable_videos'] -= 1
                counts['pending_generation'] += 1
                pending.append({'node_id': node, 'status': 'source_changed_during_read'})
                continue
            if measurement is not None and not measurement['passed']:
                if video.get('guidance_scale') == 1.0:
                    entry = repair_entry(measurement, video, pilot_sha)
                    if append_repair(repairs_path, node, entry):
                        repairs[node] = entry
                        target = 1.5
                        emit({'event': 'repair_added', 'node_id': node, **entry})
                elif video.get('guidance_scale') == 1.5:
                    counts['failed_after_guidance1p5'] += 1
                    failure = {'node_id': node, 'video_sha256': snapshot['hashes']['video'],
                        'screen_sha256': measurement['screen_sha256'],
                        'confidence': measurement['screen']['confidence'],
                        'offset_frames': measurement['screen']['offset_frames'], 'guidance_scale': 1.5}
                    failed_after_repair.append(failure)
                    if measurement['screen_sha256'] not in alerts:
                        alerts.add(measurement['screen_sha256'])
                        emit({'event': 'guidance1p5_still_failed', **failure,
                              'action': 'Report to parent; no automatic escalation or threshold change.'})
            needs_render = target != video.get('guidance_scale') or (measurement is not None and not measurement['passed'])
            if needs_render:
                counts['pending_rerender'] += 1
                pending.append({'node_id': node, 'status': 'pending_rerender_or_manual_resolution',
                                'current_guidance': video.get('guidance_scale'), 'target_guidance': target})
            elif measurement is None:
                counts['awaiting_sync_screen'] += 1
                pending.append({'node_id': node, 'status': 'awaiting_current_sync_screen'})
            else:
                counts['current_sync_passed'] += 1
                if node in repairs and snapshot['hashes']['video'] not in repaired_passes:
                    repaired_passes.add(snapshot['hashes']['video'])
                    emit({'event': 'repaired_video_passed', 'node_id': node,
                          'video_sha256': snapshot['hashes']['video'], 'guidance_scale': video['guidance_scale'],
                          'confidence': measurement['screen']['confidence'], 'offset_frames': measurement['screen']['offset_frames']})
    state.update(updated_at=now(), counts=counts, pending_nodes=pending,
                 failed_after_guidance1p5=failed_after_repair, alerted_screen_sha256=sorted(alerts),
                 reported_repair_pass_video_sha256=sorted(repaired_passes))
    if state.get('last_reported_counts') != counts:
        emit({'event': 'progress', **counts})
        state['last_reported_counts'] = counts.copy()
    return counts['current_sync_passed'] == len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', type=float, default=20)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    rows = load(DIRECTORY / 'manifest.json')['nodes']
    assert len(rows) == 150, 'Maintenance is scoped to the frozen 150-node batch'
    pilot_sha = sha(PILOT)
    state_path = DIRECTORY / 'lipsync_maintenance_state.json'
    state = load(state_path) if state_path.exists() else {}
    with (DIRECTORY / 'lipsync_maintenance.lock').open('a') as ownership:
        fcntl.flock(ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)

        def emit(event):
            event = {'time': now(), **event}
            line = json.dumps(event, ensure_ascii=False)
            with (DIRECTORY / 'lipsync_maintenance.events.jsonl').open('a') as log:
                log.write(line + '\n')
            print(line, flush=True)

        while True:
            complete = scan(rows, state, emit, pilot_sha=pilot_sha)
            atomic_json(state_path, state)
            if complete:
                emit({'event': 'all_current_videos_passed', 'nodes': len(rows)})
                return
            if args.once:
                return
            time.sleep(args.interval)


if __name__ == '__main__':
    main()
