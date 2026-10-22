"""Independently recheck nonexact local speech transcripts, without rewriting them."""
import argparse
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_annotation400 import OUT, load, save, sha
from scripts.screen_annotation400_av import speech_normalized, critical_content_matches

VERSION = 'local_audio_large_unprompted_review_v1'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--node-id', nargs='*')
    parser.add_argument('--watch-pid', type=int)
    parser.add_argument('--max-wait-seconds', type=int, default=1800)
    args = parser.parse_args()
    from faster_whisper import WhisperModel
    model = WhisperModel('large-v3-turbo', device='cuda', compute_type='float16',
        cpu_threads=2, download_root=str(ROOT / '.local_models/faster-whisper'),
        local_files_only=True)
    rows = load(OUT / 'local_av/manifest.json')['nodes']
    deadline = time.monotonic() + args.max_wait_seconds
    while True:
        for row in rows:
            if args.node_id and row['node_id'] not in args.node_id:
                continue
            request_path = ROOT / row['request_path']
            first_path = request_path.with_name('audio_screen.json')
            if not first_path.exists():
                continue
            first = load(first_path)
            if not args.node_id and first.get('normalized_similarity') == 1 and first.get('machine_screen_passed'):
                continue
            media = request_path.with_name('speech.wav')
            digest = sha(media)
            output = request_path.with_name('audio_large_review.json')
            if output.exists() and load(output).get('sha256') == digest:
                continue
            request = load(request_path)
            segments, info = model.transcribe(str(media), beam_size=5,
                vad_filter=True, condition_on_previous_text=False)
            transcript = ''.join(x.text for x in segments).strip()
            expected = request['source_public_response']
            similarity = SequenceMatcher(None, speech_normalized(expected),
                speech_normalized(transcript), autojunk=False).ratio()
            critical = critical_content_matches(expected, transcript)
            result = {'node_id': row['node_id'], 'sha256': digest,
                'spec_sha256': request['spec_sha256'], 'version': VERSION,
                'expected': expected, 'transcript': transcript, 'language': info.language,
                'normalized_similarity': round(similarity, 4),
                'critical_content_match': critical, 'model': 'large-v3-turbo',
                'device': 'cuda', 'compute_type': 'float16', 'unprompted': True,
                'machine_screen_passed': info.language == 'en' and similarity >= .98 and critical,
                'human_review': 'pending', 'speech_verified': False}
            save(output, result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        if not args.watch_pid or time.monotonic() >= deadline:
            break
        try:
            os.kill(args.watch_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(5)


if __name__ == '__main__':
    main()
