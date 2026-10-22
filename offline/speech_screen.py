"""Local, unprompted ASR comparison; never promotes machine checks to human review."""
import argparse
from difflib import SequenceMatcher
from pathlib import Path
import re

from offline.choice_builder import load, save, sha
from offline.talking_head import ROOT, current_bank


def normalized(text):
    return ''.join(re.findall(r'[a-z0-9\u3400-\u9fff]', text.lower()))


def screen(manifest_path, node_ids=None, *, model_name='small', device='cpu'):
    from faster_whisper import WhisperModel
    manifest_path = Path(manifest_path)
    manifest = load(manifest_path)
    current_bank(manifest)
    directory = manifest_path.parent
    result_path = directory / 'speech_screen.json'
    result = load(result_path) if result_path.exists() else {
        'items_sha256': manifest['items_sha256'],
        'method': 'local_unprompted_transcription', 'human_review': 'pending', 'nodes': {}}
    if result['items_sha256'] != manifest['items_sha256']:
        raise ValueError('ASR report belongs to a different bank')
    nodes = {n['node_id']: n for n in manifest['nodes']}
    completed = load(directory / 'completed_nodes.json')
    model = None
    for row in completed:
        node_id = row['node_id']
        if node_ids and node_id not in node_ids:
            continue
        asset = row['asset']
        if sha(asset['path']) != asset['sha256']:
            raise ValueError('assembled video changed before speech check')
        previous = result['nodes'].get(node_id, {})
        if previous.get('video_sha256') == asset['sha256'] and previous.get('model') == model_name:
            continue
        if model is None:
            model = WhisperModel(model_name, device=device,
                                 compute_type='int8' if device == 'cpu' else 'float16', cpu_threads=8,
                                 download_root=str(ROOT / '.local_models/faster-whisper'), local_files_only=True)
        expected = nodes[node_id].get('spoken_text', nodes[node_id]['source_public_response'])
        segments, info = model.transcribe(asset['path'], beam_size=5, word_timestamps=True,
                                          condition_on_previous_text=False, vad_filter=True)
        segments = list(segments)
        transcript = ''.join(s.text for s in segments).strip()
        source, observed = normalized(expected), normalized(transcript)
        ratio = SequenceMatcher(None, source, observed, autojunk=False).ratio()
        record = {'video_sha256': asset['sha256'], 'model': model_name, 'expected': expected, 'transcript': transcript,
                  'language': info.language, 'normalized_similarity': round(ratio, 4),
                  'status': 'asr_text_match' if source == observed else 'asr_difference_review_required',
                  'status_label': '转写与原文一致' if source == observed else '转写有差异，需听辨',
                  'human_review': 'pending', 'speech_verified': False,
                  'segments': [{'start': s.start, 'end': s.end, 'text': s.text} for s in segments]}
        result['nodes'][node_id] = record
        save(result_path, result)
        print(node_id, record['status'], record['normalized_similarity'], transcript, flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--node-id', action='append')
    parser.add_argument('--model', default='small')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--watch-preview', action='store_true', help='Screen newly assembled selected preview nodes until complete')
    args = parser.parse_args()
    if args.watch_preview:
        import time
        selection = load(args.manifest.parent / 'preview_selection.json')
        if selection['items_sha256'] != load(args.manifest)['items_sha256']:
            raise ValueError('preview selection belongs to a different bank')
        selected = set(selection['node_ids'])
        while True:
            result = screen(args.manifest, selected, model_name=args.model, device=args.device)
            completed = {r['node_id']: r['asset']['sha256'] for r in load(args.manifest.parent / 'completed_nodes.json')}
            if all(result['nodes'].get(n, {}).get('video_sha256') == completed.get(n)
                   and result['nodes'].get(n, {}).get('model') == args.model for n in selected):
                break
            time.sleep(30)
    else:
        screen(args.manifest, args.node_id, model_name=args.model, device=args.device)
