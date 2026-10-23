"""Verify native Seedance outputs and make compact web copies, without new generation."""
from argparse import ArgumentParser
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.seedance_state_batch import OUT, load, save, sha, utc_now


def all_rows(online=False):
    rows = load(OUT / 'manifest.json')['nodes']
    if online:
        p = ROOT / 'data/gpt50/experiment/seedance_state_online_v4/manifest.json'
        if p.exists():
            rows += load(p)['requests']
    return rows


def prepare_qa(row):
    directory = ROOT / row['directory']
    with (directory / '.qa-prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _prepare_qa(row)


def _prepare_qa(row):
    directory = ROOT / row['directory']
    state_path = directory / 'provider-state.json'
    if not state_path.exists() or load(state_path).get('status') != 'downloaded':
        return None
    state = load(state_path)
    native = directory / 'native.mp4'
    if sha(native) != state['video_sha256']:
        raise ValueError('Native source hash mismatch')
    qa = directory / 'qa'
    qa.mkdir(exist_ok=True)
    request = dict(node_id=row['node_id'], scenario_id=row['scenario_id'],
        source_public_response=row.get('exact_line', ''),
        source_native_sha256=sha(native), prompt_sha256=sha(directory / 'prompt.en.txt'),
        target_seconds=row.get('duration_seconds', 5), method='seedance_native_state_v2')
    from offline.talking_head import canonical_sha
    request['spec_sha256'] = canonical_sha(request)
    prior = load(qa / 'request.json') if (qa / 'request.json').exists() else None
    if prior and prior != request:
        raise ValueError('QA inputs changed; preserve prior evidence before rechecking')
    save(qa / 'request.json', request)
    if not (qa / 'speech.wav').exists():
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(native), '-vn', '-ar', '16000', '-ac', '1', str(qa / 'speech.wav')], check=True)
    if not (directory / 'web.mp4').exists():
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(native), '-map', '0:v:0', '-map', '0:a:0',
            '-c:v', 'libx264', '-crf', '25', '-preset', 'medium', '-threads', '2', '-c:a', 'copy',
            '-movflags', '+faststart', str(directory / 'web.tmp.mp4')], check=True)
        (directory / 'web.tmp.mp4').replace(directory / 'web.mp4')
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(directory / 'web.mp4')]))
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    duration = float(probe['format']['duration'])
    target = request['target_seconds']
    passed = (target-.1 <= duration <= target+.2 and abs(float(video['duration'])-float(audio['duration'])) < .2
              and int(video['nb_read_frames']) >= target*23)
    save(directory / 'web-receipt.json', dict(source_native_sha256=sha(native), web_sha256=sha(directory / 'web.mp4'),
        bytes=(directory / 'web.mp4').stat().st_size, duration_seconds=duration, fps=video['avg_frame_rate'],
        frame_count=int(video['nb_read_frames']), structural_pass=passed,
        transform='H.264 CRF25 web compression; original timing, frames and native audio retained', human_review='pending'))
    if not passed:
        raise ValueError('Web AV structure failed')
    return qa


def run_phase(args):
    model = None
    seen = set()
    while True:
        checked = 0
        for row in all_rows(args.online):
            if args.node and row['node_id'] != args.node:
                continue
            if int.from_bytes(row['node_id'].encode(), 'little') % args.shards != args.shard:
                continue
            directory = ROOT / row['directory']
            state_path = directory / 'provider-state.json'
            version = load(state_path).get('video_sha256') if state_path.exists() else None
            media_key = (row['node_id'], version)
            if media_key in seen:
                continue
            try:
                qa = prepare_qa(row)
                if qa is None:
                    continue
                if args.phase == 'asr':
                    screen = qa / 'audio_screen.json'
                    if not screen.exists():
                        if model is None:
                            from offline.native_video_checks import ASR
                            model = ASR()
                        if row['location'] == 'online':
                            segments, info = model.model.transcribe(str(qa / 'speech.wav'), beam_size=5,
                                vad_filter=True, condition_on_previous_text=False)
                            transcript = ''.join(x.text for x in segments).strip()
                            save(screen, dict(version='seedance_nonverbal_asr_v1', transcript=transcript,
                                sha256=sha(qa / 'speech.wav'), source_native_sha256=sha(directory / 'native.mp4'),
                                machine_screen_passed=not transcript, human_review='pending', unprompted=True))
                        else:
                            model.render(qa / 'request.json')
                elif args.phase == 'sync' and row['location'] != 'online':
                    screen = qa / 'lipsync_screen.json'
                    if not screen.exists():
                        if model is None:
                            from offline.native_video_checks import Sync
                            model = Sync()
                        video = qa / 'video.mp4'
                        if not video.exists():
                            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(directory / 'web.mp4'),
                                '-vf', 'fps=25', '-c:v', 'libx264', '-crf', '18', '-threads', '2', '-c:a', 'copy', str(video)], check=True)
                        model.render(qa / 'request.json')
                seen.add(media_key)
                checked += 1
                print(json.dumps(dict(node=row['node_id'], phase=args.phase, status='checked')), flush=True)
            except Exception as exc:
                save(directory / ('qa-error-'+args.phase+'.json'), dict(type=type(exc).__name__, error=str(exc), at=utc_now()))
                seen.add(media_key)
                print(json.dumps(dict(node=row['node_id'], phase=args.phase, status='error', type=type(exc).__name__)), flush=True)
        if not args.watch:
            break
        time.sleep(20)


if __name__ == '__main__':
    p = ArgumentParser()
    p.add_argument('phase', choices=['prepare', 'asr', 'sync'])
    p.add_argument('--online', action='store_true')
    p.add_argument('--watch', action='store_true')
    p.add_argument('--node')
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--shards', type=int, default=1)
    args = p.parse_args()
    if not 0 <= args.shard < args.shards:
        p.error('Invalid shard')
    run_phase(args)
