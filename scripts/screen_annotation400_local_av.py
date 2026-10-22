"""Unprompted speech verification against frozen English lines, before export."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
import re
import shutil
import threading
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_annotation400 import OUT, load, save, sha
from scripts.screen_annotation400_av import (
    speech_normalized, critical_content_matches as shared_critical_content_matches,
    SCREEN_VERSION as SHARED_GUARD_VERSION,
)

VERSION = 'local_av_unprompted_speech_v5_dual_numeric_ctc'


def legacy_critical_tokens(text):
    """Freeze the v5 numeric/negation Counter, independent of shared updates."""
    text = text.lower().replace('’', "'")
    for source, target in {"can't": 'cannot', "won't": 'will not', "don't": 'do not',
            "doesn't": 'does not', "didn't": 'did not', "isn't": 'is not',
            "aren't": 'are not', "wasn't": 'was not', "weren't": 'were not',
            "haven't": 'have not', "hasn't": 'has not', "hadn't": 'had not',
            "shouldn't": 'should not', "wouldn't": 'would not', "couldn't": 'could not'}.items():
        text = re.sub(r'\b' + re.escape(source) + r'\b', target, text)
    text = re.sub(r'\bcannot\b', 'can not', text)
    units = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    tens = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
            'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90}
    text = re.sub(r'\b(' + '|'.join(tens) + r')(?:[ -](' + '|'.join(units[1:10]) + r'))?\b',
        lambda m: str(tens[m[1]] + (units.index(m[2]) if m[2] else 0)), text)
    text = re.sub(r'\b(' + '|'.join(units) + r')\b', lambda m: str(units.index(m[1])), text)
    return Counter(re.findall(r'\b(?:no|not|never|without)\b|\d+(?:\.\d+)?', text))


def legacy_critical_content_matches(expected, observed):
    return legacy_critical_tokens(expected) == legacy_critical_tokens(observed)


def critical_content_matches(expected, observed):
    # A concurrent shared update cannot relax the original local admission guard.
    return (legacy_critical_content_matches(expected, observed)
            and shared_critical_content_matches(expected, observed))


def ready_media(path, request, stage):
    media = path.parent / ('speech.wav' if stage == 'audio' else 'video.mp4')
    receipt = path.parent / ('speech.json' if stage == 'audio' else 'video.json')
    if not media.exists() or not receipt.exists():
        return media, None, 'waiting_for_completed_media'
    record = load(receipt)
    digest = sha(media)
    if record.get('sha256') != digest or record.get('spec_sha256') != request['spec_sha256']:
        return media, None, 'waiting_for_matching_receipt'
    if stage == 'video' and record.get('audio_sha256') != sha(path.with_name('speech.wav')):
        return media, None, 'waiting_for_current_audio_render'
    return media, digest, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stage', choices=['audio', 'video'], default='audio')
    p.add_argument('--scene', nargs='*')
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    p.add_argument('--compute-type', choices=['int8', 'float16', 'float32', 'int8_float16'])
    p.add_argument('--rescore-existing', action='store_true', help='Re-evaluate archived unprompted transcripts without new inference')
    p.add_argument('--watch', action='store_true', help='Screen finalized renders as the existing queue completes them')
    p.add_argument('--max-wait-seconds', type=int, default=14400)
    a = p.parse_args()
    compute_type = a.compute_type or ('float16' if a.device == 'cuda' else 'int8')
    if not a.rescore_existing:
        from faster_whisper import WhisperModel
        kwargs = dict(device=a.device, compute_type=compute_type, cpu_threads=4, num_workers=a.workers,
                      download_root=str(ROOT / '.local_models/faster-whisper'), local_files_only=True)
        small = WhisperModel('small', **kwargs)
        large = WhisperModel('large-v3-turbo', **kwargs)
        english_path = ROOT / '.local_models/annotation400-asr-small-en'
        english_sha256 = sha(english_path / 'model.bin')
        english = WhisperModel(str(english_path), **kwargs)
    ctc_model = None
    ctc_lock = threading.Lock()

    def check(row):
        path = ROOT / row['request_path']
        request = load(path)
        media, h, pending = ready_media(path, request, a.stage)
        if pending:
            return {'node_id': row['node_id'], 'status': pending}
        output = path.parent / (a.stage + '_screen.json')
        old = load(output) if output.exists() else {}
        if output.exists():
            if (old.get('sha256') == h and old.get('version') == VERSION
                    and old.get('spec_sha256') == request['spec_sha256']
                    and old.get('shared_guard_version') == SHARED_GUARD_VERSION):
                return old
        if a.rescore_existing and not (old.get('sha256') == h and
                old.get('spec_sha256') == request['spec_sha256'] and
                old.get('expected') == request['source_public_response'] and old.get('screens')):
            return {'node_id': row['node_id'], 'status': 'no_current_transcript'}
        if output.exists():
            history = path.parent / 'screen_history' / sha(output)
            history.mkdir(parents=True, exist_ok=True)
            archived = history / output.name
            if not archived.exists():
                shutil.copy2(output, archived)
        expected = request['source_public_response']
        screens = []
        def transcripts():
            nonlocal ctc_model
            if a.rescore_existing:
                yield from old['screens']
                return
            for label, model in [('small', small), ('large-v3-turbo', large), ('small.en', english)]:
                segments, info = model.transcribe(str(media), beam_size=5, vad_filter=True, condition_on_previous_text=False)
                record = {'model': label, 'transcript': ''.join(s.text for s in segments).strip(),
                          'language': info.language, 'device': a.device, 'compute_type': compute_type}
                if label == 'small.en':
                    record.update(checkpoint_repo='Systran/faster-whisper-small.en', checkpoint_sha256=english_sha256)
                yield record
            # This generator reaches CTC only after all Whisper models fail.
            with ctc_lock:
                if ctc_model is None:
                    from scripts.transcribe_annotation400_ctc import CTCTranscriber
                    ctc_model = CTCTranscriber(a.device)
            record = ctc_model.transcribe(media)
            record['recognizer_version'] = record.pop('version')
            yield record

        error = None
        passed = False
        try:
            for record in transcripts():
                text = record['transcript']
                similarity = SequenceMatcher(None, speech_normalized(expected), speech_normalized(text), autojunk=False).ratio()
                legacy = legacy_critical_content_matches(expected, text)
                shared = shared_critical_content_matches(expected, text)
                critical = legacy and shared
                passed = record['language'] == 'en' and similarity >= .98 and critical
                screens.append({**record, 'normalized_similarity': round(similarity, 4),
                    'legacy_critical_content_match': legacy, 'shared_critical_content_match': shared,
                    'critical_content_match': critical})
                if passed:
                    break
        except Exception as exc:
            passed = False
            error = {'type': type(exc).__name__, 'message': str(exc)}
        _, current, pending = ready_media(path, request, a.stage)
        if pending or current != h:
            return {'node_id': row['node_id'], 'status': 'media_changed_during_screen'}
        result = {'node_id': row['node_id'], 'sha256': h, 'version': VERSION,
                  'shared_guard_version': SHARED_GUARD_VERSION,
                  'legacy_guard_version': 'v5_numeric_negation_counter_frozen',
                  'spec_sha256': request['spec_sha256'], 'expected': expected, **(screens[-1] if screens else {}),
                  'screens': screens, 'machine_screen_passed': passed,
                  'human_review': 'pending', 'speech_verified': False}
        if error:
            result['status'] = 'recognizer_error'
            result['error'] = error
        if a.rescore_existing:
            result['transcript_reuse'] = {'source_screen_sha256': sha(output), 'source_version': old['version'],
                                          'new_inference_calls': 0}
        save(output, result)
        return result

    rows = [x for x in load(OUT / 'local_av/manifest.json')['nodes'] if not a.scene or x['scenario_id'] in a.scene]
    deadline = time.monotonic() + a.max_wait_seconds
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        while True:
            results = list(pool.map(check, rows))
            completed = [x for x in results if 'machine_screen_passed' in x]
            pending = [x for x in results if 'machine_screen_passed' not in x]
            summary = {'stage': a.stage, 'required': len(rows),
                'checked': len(completed), 'passed': sum(x['machine_screen_passed'] for x in completed),
                'failed': [x for x in completed if not x['machine_screen_passed']],
                'pending': pending, 'complete': len(completed) == len(rows),
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'human_review': 'pending', 'version': VERSION, 'shared_guard_version': SHARED_GUARD_VERSION}
            save(OUT / 'local_av' / (a.stage + '_screen_summary.json'), summary)
            print(json.dumps({**{k: v for k, v in summary.items() if k not in {'failed', 'pending'}},
                'failed_count': len(summary['failed']), 'pending_count': len(pending)}), flush=True)
            if not a.watch or summary['checked'] == len(rows) or time.monotonic() >= deadline:
                return
            time.sleep(20)


if __name__ == '__main__':
    main()
