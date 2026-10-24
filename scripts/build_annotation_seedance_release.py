"""Restore verified Seedance media to an isolated public-context release.

Never edits a deployed bundle, annotation database, or frozen generation input.
Current question text/hash and private evidence remain byte-equivalent; historical
releases and every existing Gate2 bundle remain recoverable.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_research_storage import derive_previous, pack, restore_previous, unpack
from scripts import build_gate2_annotation as gate2
from scripts.export_checkpoint_annotation import replace_media_reviews
from scripts.prepare_human_gt_release import digest

RELEASE = 'annotation400-seedance-public-context-20261024-v1'


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_release(value):
    if value['dataset_sha256'] != digest({k: v for k, v in value.items() if k != 'dataset_sha256'}):
        raise ValueError('Frozen dataset hash mismatch')


def without_context(question):
    result = deepcopy(question)
    result.get('input', {}).pop('context', None)
    return result


def merge_media(current, seedance):
    """Accept changed public context only; bind exact existing history and media."""
    checked_release(current)
    checked_release(seedance)
    context_revision = current.get('public_context_revision', {})
    if (context_revision.get('version') != 1
            or context_revision.get('source_bank_sha256') != seedance['source_bank_sha256']):
        raise ValueError('Public-context source bank lineage mismatch')
    original = {i['id']: i for i in seedance['items']}
    if len(original) != len(seedance['items']) or set(original) != {i['id'] for i in current['items']}:
        raise ValueError('Question ID mismatch')
    revised = deepcopy(current)
    lineage = []
    for item in revised['items']:
        old = original[item['id']]
        if (item['scene_id'] != old['scene_id'] or item['task'] != old['task']
                or without_context(item['public_text']) != without_context(old['public_text'])):
            raise ValueError('Question/history changed beyond public context: ' + item['id'])
        if item['task'] == 'T2':
            if old['media'] or old['public_video'] is not None:
                raise ValueError('Expected frozen T2 text-only condition')
            item.update(public_video=None, media=[], coverage=deepcopy(old['coverage']))
        else:
            if item['task'] not in ('T1', 'T3') or not old['media']:
                raise ValueError('Missing Seedance condition')
            prior_nodes = {m['node_id']: m for m in item['media']}
            for media in old['media']:
                prior = prior_nodes.get(media['node_id'])
                if (media.get('provider') != 'seedance' or not prior
                        or any(media.get(k) != prior.get(k) for k in
                               ('spoken_text', 'full_public_response', 'source_quote', 'evidence_ids'))):
                    raise ValueError('Checkpoint media binding mismatch: ' + item['id'])
            item.update(public_video={**deepcopy(item['public_text']), 'modality': 'text+video'},
                        media=deepcopy(old['media']), coverage=deepcopy(old['coverage']))
        lineage.append(dict(id=item['id'], scene_id=item['scene_id'],
                            current_item_sha256=item['item_sha256'],
                            seedance_source_item_sha256=old['item_sha256'],
                            media_sha256=[m['sha256'] for m in item['media']]))
    revised.update(release=RELEASE, media_readiness=deepcopy(seedance['media_readiness']),
                   media_revision=dict(version=1, source_dataset_sha256=current['dataset_sha256'],
                                       seedance_dataset_sha256=seedance['dataset_sha256'],
                                       public_context_preserved=True, annotations_modified=False))
    revised.pop('dataset_sha256')
    revised['dataset_sha256'] = digest(revised)
    return revised, lineage


def build(source_site, output, seedance_root):
    source_site, output, seedance_root = (Path(p).resolve() for p in (source_site, output, seedance_root))
    if not output.is_relative_to(ROOT / 'build') or output == source_site or output.is_relative_to(source_site):
        raise ValueError('Output must be an isolated build directory')
    data = source_site / 'data'
    paths = [data / n for n in ('research-server.json', 'research-public-context-delta-server.json', 'gate2-review-server.json')]
    paths += [seedance_root / 'release.json', seedance_root / 'manifest.json']
    frozen = {str(p): file_sha(p) for p in paths}
    base = unpack(paths[0].read_bytes())
    current = restore_previous(base, unpack(paths[1].read_bytes()))
    seedance = json.loads(paths[3].read_text())
    revised, lineage = merge_media(current, seedance)
    if len(revised['items']) != 400 or len({i['scene_id'] for i in revised['items']}) != 50:
        raise ValueError('Expected 400 questions in 50 scenarios')
    if sum(i['public_video'] is not None for i in revised['items']) != 300:
        raise ValueError('Expected 300 T1/T3 video questions and 100 T2 text questions')
    manifest = json.loads(paths[4].read_text())
    nodes = {n['node_id']: n for n in manifest['nodes']}
    assets = {m['node_id']: m for i in revised['items'] for m in i['media']}
    if len(assets) != 100 or set(assets) != set(nodes):
        raise ValueError('Expected 100 exact Seedance nodes')
    verified = []
    for node_id, asset in assets.items():
        directory = ROOT / nodes[node_id]['directory']
        receipt = json.loads((directory / 'web-receipt.json').read_text())
        state = json.loads((directory / 'provider-state.json').read_text())
        prompt_sha = file_sha(directory / 'prompt.en.txt')
        if (receipt['web_sha256'] != asset['sha256'] or file_sha(directory / 'web.mp4') != asset['sha256']
                or prompt_sha != asset['prompt_sha256'] or state.get('status') != 'downloaded'
                or receipt['source_native_sha256'] != asset['native_video_sha256']
                or state['video_sha256'] != asset['native_video_sha256']
                or file_sha(directory / 'native.mp4') != asset['native_video_sha256']
                or not receipt['structural_pass']):
            raise ValueError('Seedance generation provenance mismatch: ' + node_id)
        gate2.copy_video(output, directory / 'web.mp4', asset['sha256'], asset['url'])
        verified.append(dict(node_id=node_id, video_sha256=asset['sha256'],
                             native_video_sha256=asset['native_video_sha256'], prompt_sha256=prompt_sha,
                             source_directory=str(directory.relative_to(ROOT))))
    registry = unpack(paths[2].read_bytes())
    expanded = gate2.expand_registry(registry)
    previous = next(v for v in expanded['versions'] if v['sha256'] == expanded['current'])
    if previous['dataset_sha256'] != current['dataset_sha256']:
        raise ValueError('Current Gate2/public-context dataset mismatch')
    new_registry, bundle, coverage, retained = replace_media_reviews(registry, revised, output)
    if new_registry['versions'][:len(expanded['versions'])] != expanded['versions']:
        raise ValueError('Historical Gate2 bundles changed')
    target = output / 'data'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'research-seedance-context-delta-server.json').write_bytes(pack(derive_previous(base, revised)))
    (target / 'research-seedance-original-delta-server.json').write_bytes(pack(derive_previous(base, seedance)))
    gate2.write_registry(target / 'gate2-review-server.json', new_registry)
    (output / 'release.json').write_text(json.dumps(revised, ensure_ascii=False, indent=2) + '\n')
    audit = dict(format='socialflux_seedance_context_restore_v1', release=revised['release'],
                 dataset_sha256=revised['dataset_sha256'], previous_dataset_sha256=current['dataset_sha256'],
                 seedance_dataset_sha256=seedance['dataset_sha256'], gate2_sha256=bundle['sha256'],
                 scenes=50, questions=400, video_questions=300, text_only_t2=100, videos=100,
                 preserved_prior_gate2_versions=len(expanded['versions']), retained_non_media_tasks=retained,
                 media_coverage=coverage, source_files=frozen, verified_assets=verified, question_lineage=lineage,
                 existing_annotations_modified=False, prior_releases_modified=False, deployed=False,
                 human_review='pending_except_previously_approved_pilot')
    for path, sha in frozen.items():
        if file_sha(path) != sha:
            raise ValueError('Source modified during build: ' + path)
    (output / 'manifest.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    return {k: audit[k] for k in ('release', 'dataset_sha256', 'gate2_sha256', 'scenes', 'questions', 'videos', 'preserved_prior_gate2_versions')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-site', type=Path, default=ROOT / 'web/annotation_portable')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seedance-root', type=Path, default=ROOT / 'data/seedance_state_v2_20261023')
    args = parser.parse_args()
    print(json.dumps(build(args.source_site, args.output, args.seedance_root)))
