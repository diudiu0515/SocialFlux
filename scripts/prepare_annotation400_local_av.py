"""Freeze public-only local dubbing jobs without modifying the question bank."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_annotation400 import OUT, load, save, sha
from offline.talking_head import public_nodes, canonical_sha

DIRECTORY = OUT / 'local_av'


def prepare():
    rows = [json.loads(line) for line in (OUT / 'items.jsonl').read_text().splitlines()]
    identities = {x['scene']: x for x in load(DIRECTORY / 'identities.json')}
    # Voice casting for fictional characters; it does not estimate personal traits.
    lower_voices = {1, 5, 9, 12, 17, 25, 30, 34, 36, 43, 45, 46, 48}
    jobs = []
    for node in public_nodes(rows):
        identity = identities[node['scenario_id']]
        assert sha(ROOT / identity['identity_path']) == identity['identity_sha256']
        index = int(node['scenario_id'].split('_')[-1])
        expression = node['source_observable_expression']
        style = (expression.get('prosody', '') + ' ' + expression.get('speech_style', '')).lower()
        speed = 1.05 if any(w in style for w in ('quick', 'fast', 'brisk', 'clipped')) else 0.97
        voice = 'am_michael' if index in lower_voices else 'af_sarah'
        spec = {
            'node_id': node['node_id'], 'scenario_id': node['scenario_id'],
            'speaker': node['speaker'], 'location': node['location'],
            'source_public_response': node['source_public_response'],
            'source_observable_expression': expression,
            'identity': identity,
            'voice': voice, 'speed': speed, 'speech_language': 'en',
            'motion_source': 'public_facial_expression_and_gaze_only',
            'method': 'local_photorealistic_dubbing_v1',
            'human_review': 'pending',
        }
        spec['spec_sha256'] = canonical_sha(spec)
        directory = DIRECTORY / node['scenario_id'] / node['node_id']
        directory.mkdir(parents=True, exist_ok=True)
        save(directory / 'request.json', spec)
        jobs.append({'node_id': node['node_id'], 'scenario_id': node['scenario_id'],
                     'request_path': str((directory / 'request.json').relative_to(ROOT)),
                     'spec_sha256': spec['spec_sha256']})
    save(DIRECTORY / 'manifest.json', {
        'format': 'socialflux_local_photorealistic_dubbing_v1',
        'source_bank_sha256': sha(OUT / 'items.jsonl'),
        'nodes': jobs, 'node_count': len(jobs), 'scene_count': len(identities),
        'contains_private_evidence': False, 'human_review': 'pending',
    })
    print(json.dumps({'nodes': len(jobs), 'scenes': len(identities)}))


if __name__ == '__main__':
    prepare()
