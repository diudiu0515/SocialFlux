"""Bind verified short checkpoints to an isolated copy of the 400-question site.

This adapter does not render media, publish a site, or change frozen releases.
The full public question remains unchanged; only the spoken-video condition and
its post-answer media reviews receive new versions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from offline.talking_head import public_nodes
from scripts import build_gate2_annotation as gate2
from scripts import package_checkpoint_revision as preview
from scripts.prepare_human_gt_release import digest as research_digest, packed

RELEASE = 'annotation400-checkpoint-20261023-v2'
SCOPE_NOTE = ('The video speaks one short checkpoint sentence. It does not read '
              'the complete response; the full public dialogue remains in the question.')


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def media_snapshot(release):
    return {k: deepcopy(release[k]) for k in ('release', 'dataset_sha256', 'source_bank_sha256', 'assignments')} | {
        'items': [{k: deepcopy(item[k]) for k in ('id', 'item_sha256', 'media', 'coverage')} |
                  {'has_video': bool(item['public_video'])} for item in release['items']]}


def validate_lineage(row, request, node, original_job):
    """Require the exact frozen public node, even if a new request is self-consistent."""
    if (row['node_id'] != node['node_id'] or row['scenario_id'] != node['scenario_id']
            or request.get('source_spec_sha256') != original_job.get('spec_sha256')
            or request.get('full_public_response') != node['source_public_response']
            or any(request.get(k) != node[k] for k in
                   ('node_id', 'scenario_id', 'speaker', 'location', 'source_observable_expression'))):
        raise ValueError('Checkpoint frozen public-node lineage mismatch: ' + row['node_id'])
    line = request.get('checkpoint_line', {})
    if (line.get('checkpoint_text') != request.get('source_public_response')
            or line.get('original_response') != node['source_public_response']
            or not isinstance(line.get('source_quote'), str) or not line['source_quote']
            or line['source_quote'] not in node['source_public_response']
            or (line.get('verbatim_excerpt') is True and line['checkpoint_text'] not in line['source_quote'])):
        raise ValueError('Checkpoint source quote mismatch: ' + row['node_id'])


def replace_media(research, nodes, assets):
    """Keep questions, item hashes, assignments, private packets, and T4 unchanged."""
    result = deepcopy(research)
    bindings = {}
    items = {item['id']: item for item in research['items']}
    for node in nodes:
        for binding in node['bindings']:
            item = items.get(binding['instance_id'])
            if (item is None or item['scene_id'] != node['scenario_id']
                    or binding['item_sha256'] != item['item_sha256']):
                raise ValueError('Checkpoint question binding mismatch: ' + binding['instance_id'])
            bindings.setdefault(binding['instance_id'], []).append(
                deepcopy(assets[node['node_id']]) | {'evidence_ids': binding['evidence_ids'][:]})
    if set(bindings) != set(items):
        raise ValueError('Checkpoint media do not cover every frozen question')
    for item in result['items']:
        if not item['public_video']:
            raise ValueError('Source question has no frozen video condition')
        item['media'] = bindings[item['id']]
        item['coverage'] = deepcopy(item['coverage']) | {
            'spoken_scope': 'checkpoint_sentence', 'full_reply_text_preserved': True,
            'complete_spoken_response': False, 'scope_note': SCOPE_NOTE, 'human_review': 'pending'}
    result['release'] = RELEASE
    result['media_readiness'] = deepcopy(research['media_readiness']) | {
        'required_nodes': len(nodes), 'completed_nodes': len(assets), 'complete_items': len(items),
        'gaps': [], 'human_review': 'pending', 'spoken_scope': 'checkpoint_sentence',
        'full_reply_text_preserved': True, 'complete_spoken_response': False,
        'scope_note': SCOPE_NOTE, 'published': False, 'release_eligible': False}
    result.pop('dataset_sha256', None)
    result['dataset_sha256'] = research_digest(result)
    return result


def replace_media_reviews(registry, research, site, cards=()):
    """Append a new bundle; existing bundle/task bytes and non-media tasks survive."""
    expanded = gate2.expand_registry(registry)
    # Validate every old task before accepting a registry as a frozen source.
    gate2.compact_registry(registry)
    current = next(v for v in expanded['versions'] if v['sha256'] == expanded['current'])
    for version in expanded['versions']:
        if version['sha256'] != gate2.digest({k: v for k, v in version.items() if k != 'sha256'}):
            raise ValueError('Frozen Gate2 bundle hash mismatch')
    tasks = [deepcopy(t) for t in current['tasks'] if t['kind'] != 'media-quality']
    retained_count = len(tasks)
    frame_reviews = {card['node_id']: card['frame_review'] for card in cards if card.get('frame_review')}

    def add(ident, sid, kind, title, evidence, questions, stage='review', **extra):
        if evidence.get('spoken_scope') == 'checkpoint_sentence':
            evidence['note'] += ' 视频只朗读 checkpoint 短句；完整回复仍由题面文字提供，不要求短片读完完整回复。'
            frame = frame_reviews.get(evidence.get('node_id'))
            if frame:
                evidence['frame_review'] = deepcopy(frame) | {
                    'scope_note': '帧级抽查，非完整观感验收；请独立完整播放后判断。', 'human_review': 'pending'}
        task = dict(id=ident, scene_id=sid, kind=kind, title=title, stage=stage,
                    evidence=evidence, questions=questions, **extra)
        task['sha256'] = gate2.digest(task)
        tasks.append(task)
        return task

    coverage = gate2.add_current_media(research, site, add)
    if len({task['id'] for task in tasks}) != len(tasks):
        raise ValueError('Duplicate checkpoint review task IDs')
    bundle = {k: deepcopy(v) for k, v in current.items() if k not in ('tasks', 'sha256', 'dataset_sha256')}
    bundle.update(dataset_sha256=research['dataset_sha256'], tasks=tasks)
    bundle['sha256'] = gate2.digest(bundle)
    versions = deepcopy(expanded['versions'])
    if bundle['sha256'] not in {v['sha256'] for v in versions}:
        versions.append(bundle)
    return dict(current=bundle['sha256'], versions=versions), bundle, coverage, retained_count


def export(site, output, *, source_site=None, manifest=None, bank=None, root=ROOT, visual_review=None):
    root, site, output = Path(root).resolve(), Path(site).resolve(), Path(output).resolve()
    source_site = Path(source_site or root / 'web/participant_demo').resolve()
    manifest = Path(manifest or root / 'data/offline_checkpoint_v2_20261022/manifest.json').resolve()
    bank = Path(bank or root / 'data/offline_annotation400_en_20261022').resolve()
    # Only an isolated build checkout may be mutated. Frozen sources are read-only.
    if (not site.is_relative_to(root / 'build') or site == source_site
            or not output.is_relative_to(root / 'data')
            or not output.name.startswith('offline_checkpoint_annotation_')
            or output.is_relative_to(bank) or output.is_relative_to(manifest.parent)):
        raise ValueError('Use an isolated build site and a separate checkpoint annotation output directory')
    source = gate2.unpack(read(source_site / 'data/research-server.json')['gzip_base64'])
    if source['dataset_sha256'] != research_digest({k: v for k, v in source.items() if k != 'dataset_sha256'}):
        raise ValueError('Frozen research dataset hash mismatch')
    registry = gate2.unpack(read(source_site / 'data/gate2-review-server.json')['gzip_base64'])
    original_bundle = next(v for v in gate2.expand_registry(registry)['versions'] if v['sha256'] == registry['current'])
    if original_bundle['dataset_sha256'] != source['dataset_sha256']:
        raise ValueError('Source research/Gate2 dataset mismatch')
    rows = [json.loads(line) for line in (bank / 'items.jsonl').read_text().splitlines() if line.strip()]
    jobs = read(bank / 'local_av/manifest.json')
    revision = read(manifest)
    bank_sha = preview.file_sha(bank / 'items.jsonl')
    if (source['source_bank_sha256'] != bank_sha or revision['source_bank_sha256'] != bank_sha
            or jobs['source_bank_sha256'] != bank_sha or revision.get('version') != 'checkpoint_4s5s_v2'):
        raise ValueError('Checkpoint source bank mismatch')
    nodes = public_nodes(rows)
    by_node = {node['node_id']: node for node in nodes}
    original_jobs = {node['node_id']: node for node in jobs['nodes']}
    if (len(source['items']) != 400 or len(nodes) != 150 or len(revision['nodes']) != 150
            or len({n['node_id'] for n in revision['nodes']}) != 150
            or {n['node_id'] for n in revision['nodes']} != set(by_node)
            or not set(by_node) <= set(original_jobs)):
        raise ValueError('Expected the complete 400-question / 150-node frozen release')
    tracked = {p: preview.file_sha(p) for p in (manifest, bank / 'items.jsonl',
        bank / 'local_av/manifest.json', source_site / 'data/research-server.json',
        source_site / 'data/gate2-review-server.json', source_site / 'data/research-media-history.json')}
    original_assets = {asset['spec_sha256']: asset['sha256']
                       for item in source['items'] for asset in item['media']}
    original_media = {}
    for node_id in by_node:
        job = original_jobs[node_id]
        path = (root / job['request_path']).resolve().parent / 'video.mp4'
        expected = original_assets.get(job['spec_sha256'])
        if not path.is_relative_to(bank) or not expected or preview.file_sha(path) != expected:
            raise ValueError('Frozen original video changed: ' + node_id)
        original_media[path] = expected
    old_media = {p: preview.file_sha(p) for p in (site / 'public/media').glob('*.mp4')}
    cards, assets = [], {}
    with tempfile.TemporaryDirectory(prefix='checkpoint-export-') as temporary:
        staging = Path(temporary)
        for row in revision['nodes']:
            request_path = Path(row['request_path'])
            if not request_path.is_absolute():
                request_path = root / request_path
            request_path = request_path.resolve()
            if not request_path.is_relative_to(manifest.parent):
                raise ValueError('Checkpoint request outside revision directory')
            request = read(request_path)
            validate_lineage(row, request, by_node[row['node_id']], original_jobs[row['node_id']])
            card = preview.build_card(row, manifest.parent, staging, root=root)
            if card['status'] != 'passed' or not card['video']:
                raise ValueError('Checkpoint machine checks not current/passed: ' + row['node_id'] + ' ' + str(card['checks']))
            cards.append(card)
            sha = card['hashes']['video.mp4']
            assets[row['node_id']] = dict(asset_id='video-' + sha[:16], node_id=row['node_id'], sha256=sha,
                url='/media/' + sha + '.mp4', speech_language='en', audio_required=True,
                spoken_text=request['source_public_response'], spoken_scope='checkpoint_sentence',
                full_public_response=request['full_public_response'], source_quote=request['checkpoint_line']['source_quote'],
                duration_seconds=card['duration_seconds'], media_kind='talking_head', human_review='pending',
                speech_verified=False, provider='local', method='checkpoint_4s5s_v2', spec_sha256=row['spec_sha256'])
        if len({a['sha256'] for a in assets.values()}) != 150:
            raise ValueError('Expected 150 distinct current video hashes')
        preview.attach_frame_reviews(cards, read(visual_review) if visual_review else None)
        research = replace_media(source, nodes, assets)
        for card in cards:
            asset = assets[card['node_id']]
            gate2.copy_video(site, staging / card['video'], asset['sha256'], asset['url'])
        new_registry, bundle, coverage, retained = replace_media_reviews(registry, research, site, cards)
        if any(preview.file_sha(p) != sha for p, sha in tracked.items()):
            raise ValueError('Frozen inputs changed during checkpoint export')
        if any(not p.is_file() or preview.file_sha(p) != sha for p, sha in old_media.items()):
            raise ValueError('Existing candidate-site media changed during export')
        if any(preview.file_sha(p) != sha for p, sha in original_media.items()):
            raise ValueError('Frozen original videos changed during export')
        history = read(source_site / 'data/research-media-history.json')
        if source['dataset_sha256'] not in {snapshot['dataset_sha256'] for snapshot in history}:
            history.append(media_snapshot(source))
        write(site / 'data/research-media-history.json', history)
        write(site / 'data/research-server.json', {'gzip_base64': packed(research)})
        registry_stats = gate2.write_registry(site / 'data/gate2-review-server.json', new_registry)
        write(output / 'release.json', research)
        write(output / 'gate2-release.json', bundle)
        summary = dict(format='socialflux_checkpoint_annotation_candidate_v1', release=RELEASE,
            source_dataset_sha256=source['dataset_sha256'], dataset_sha256=research['dataset_sha256'],
            source_bank_sha256=bank_sha, manifest_sha256=tracked[manifest],
            items=len(research['items']), scenes=len({i['scene_id'] for i in research['items']}),
            videos=len(assets), machine_checks_passed=len(cards), video_seconds=sum(c['duration_seconds'] for c in cards),
            gate2_sha256=bundle['sha256'], gate2_counts=dict(Counter(t['kind'] for t in bundle['tasks'])),
            unchanged_non_media_tasks=retained, prior_gate2_versions_preserved=len(registry['versions']),
            registry=registry_stats, existing_site_media_unchanged=len(old_media),
            frozen_original_media_unchanged=len(original_media),
            source_files_unchanged=len(tracked), frame_samples_current=sum(bool(c.get('frame_review')) for c in cards),
            priority_visual_rewatch=sum(c.get('frame_review', {}).get('priority') == 'priority_visual_rewatch' for c in cards),
            human_review='pending', published=False, release_eligible=False)
        write(output / 'summary.json', summary)
        write(output / 'coverage_manifest.json', dict(dataset_sha256=research['dataset_sha256'],
            release_sha256=bundle['sha256'], current_media=coverage,
            unchanged_non_media_task_hashes={t['id']: t['sha256'] for t in bundle['tasks'] if t['kind'] != 'media-quality'},
            human_review='pending', published=False))
        write(output / 'source_preservation.json', {
            'source_files': {str(p.relative_to(root)): sha for p, sha in tracked.items()},
            'existing_site_media': {p.name: sha for p, sha in old_media.items()},
            'frozen_original_media': {str(p.relative_to(root)): sha for p, sha in original_media.items()},
            'all_sha256_unchanged': True})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/offline_checkpoint_annotation_20261023')
    parser.add_argument('--source-site', type=Path, default=ROOT / 'web/participant_demo')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/offline_checkpoint_v2_20261022/manifest.json')
    parser.add_argument('--visual-review', type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.site, args.output, source_site=args.source_site,
                            manifest=args.manifest, visual_review=args.visual_review), ensure_ascii=False))


if __name__ == '__main__':
    main()
