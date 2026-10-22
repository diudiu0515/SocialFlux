"""Prepare source-bound English samples without replacing the frozen question bank."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from environment.online_video_assets import online_identity_spec
from offline.choice_builder import load, save, sha
from offline.talking_head import ROOT, BANK, public_nodes, canonical_sha
from prompts.loader import get_prompt, render_prompt
from scripts.run_multimodal_video_queue import seedance_payload

PROMPT_ID = 'offline_talking_head_english_v1'
PROFILE = 'offline_english_preview_v1'
CONFIG = ROOT / 'configs/offline_talking_preview_en_v1.json'


def prepare(config_path=CONFIG, bank=BANK, output=None):
    config_path, bank = Path(config_path), Path(bank)
    config = load(config_path)
    bank_sha = sha(bank / 'items.jsonl')
    output = Path(output or ROOT / 'data/offline_talking_head_en_v1' / bank_sha[:16])
    prompt_sha = hashlib.sha256(get_prompt(PROMPT_ID).encode()).hexdigest()
    if (output / 'manifest.json').exists():
        previous = load(output / 'manifest.json')
        if (previous['items_sha256'] != bank_sha or previous['translation_config_sha256'] != sha(config_path)
                or previous['prompt_sha256'] != prompt_sha):
            raise ValueError('existing English preview has a different source, translation or prompt')
        return previous
    items = [json.loads(line) for line in (bank / 'items.jsonl').read_text().splitlines() if line.strip()]
    endings = {n['scenario_id']: n for n in public_nodes(items) if n['location'] == 'ending'}
    nodes, requests = [], []
    for translation in config['translations']:
        node = deepcopy(endings[translation['scenario_id']])
        if translation['source_text'] != node['source_public_response']:
            raise ValueError('English translation is bound to a different public source line')
        if not translation['text'].strip() or re.search(r'[\u3400-\u9fff]', translation['text']):
            raise ValueError('English-only dialogue is required')
        source = node['scenario_source']
        scenario_path = ROOT / source['scenario_path']
        if sha(scenario_path) != source['scenario_sha256']:
            raise ValueError('frozen scenario changed')
        node['source_node_id'] = node['node_id']
        node['node_id'] += '-en-' + canonical_sha(translation)[:8]
        node.update(spoken_text=translation['text'], speech_language='en',
                    localization=deepcopy(translation), human_review='pending',
                    continuity_reference=None, identity_continuity='independent_fictional_preview')
        if translation.get('english_source_path'):
            english_path = ROOT / translation['english_source_path']
            source_turns = load(english_path)['turns']
            if not any(t.get('environment_response') == translation['text'] for t in source_turns):
                raise ValueError('verbatim English source response changed')
            node['localization']['english_source_sha256'] = sha(english_path)
        identity = online_identity_spec(load(scenario_path))
        request_id = node['node_id'] + '-s01'
        node['segment_request_ids'] = [request_id]
        request = {'profile': PROFILE, 'prompt_id': PROMPT_ID,
                   'prompt': render_prompt(PROMPT_ID, identity_json=identity,
                       spoken_line=translation['text'], expression_json=translation['expression']),
                   'duration_seconds': translation['duration_seconds'], 'generate_audio': True,
                   'ratio': '16:9', 'identity': identity, 'reference_video_file': None,
                   'audio': {'required': True, 'spoken_content': True, 'language': 'en',
                             'exact_line': translation['text'], 'mode': 'exact_english_with_lip_sync'}}
        seedance_payload(request)
        request_file = output / 'requests' / (request_id + '.json')
        save(request_file, request)
        requests.append({'request_id': request_id, 'scenario_id': node['scenario_id'],
                         'node_id': node['node_id'], 'segment_index': 1, 'segment_count': 1,
                         'request_file': str(request_file.relative_to(ROOT)),
                         'video_file': str((output / 'segments' / (request_id + '.mp4')).relative_to(ROOT)),
                         'source_public_response': node['source_public_response'],
                         'spoken_text': translation['text'], 'status': 'request_ready'})
        nodes.append(node)
    scene_ids = [n['scenario_id'] for n in nodes]
    if len(set(scene_ids)) != len(nodes):
        raise ValueError('duplicate preview scene')
    manifest = {'format': 'socialflux_offline_talking_head_v1', 'profile': PROFILE,
                'preview_only': True, 'speech_language': 'en', 'batch_root': str(ROOT),
                'bank_path': str(bank.relative_to(ROOT)), 'items_sha256': bank_sha,
                'translation_config_sha256': sha(config_path), 'prompt_id': PROMPT_ID,
                'prompt_sha256': prompt_sha,
                'provider': {'model': 'doubao-seedance-2-0-260128', 'resolution': '720p'},
                'item_count': len(items), 'node_count': len(nodes), 'request_count': len(requests),
                'scenario_count': len(nodes), 'missing_reference_scenes': [],
                'human_review': 'pending', 'nodes': nodes, 'requests': requests}
    save(output / 'manifest.json', manifest)
    save(output / 'translations.json', config)
    save(output / 'completed_nodes.json', [])
    save(output / 'preview_selection.json', {
        'items_sha256': bank_sha, 'scene_ids': scene_ids,
        'node_ids': [n['node_id'] for n in nodes],
        'request_ids': [r['request_id'] for r in requests],
        'scope': config['scope'], 'speech_language': 'en', 'human_review': 'pending',
        'identity_policy': 'Independent fictional English previews; full histories remain incomplete.'})
    return manifest


if __name__ == '__main__':
    result = prepare()
    print(json.dumps({k: result[k] for k in ('speech_language', 'node_count', 'request_count', 'items_sha256')}))
