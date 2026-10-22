"""Validate and install the staged English dataset without new model calls.

The migration keeps source hashes, not extra Chinese dataset copies. It does not
promote translated machine references to human ground truth.
"""
from collections import Counter
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.localize_current_data import (
    ACTIVE, BANK, STAGE, CJK, clean, digest, documents_for, load,
    same_structure, sha, strings, translate_tree,
)
from pipeline.localization import atomic_json, export_projection
from pipeline.translation_checks import check_export
from offline.choice_builder import write_bundle, save_text
from offline.choice_media import turn_matches
from tasks.offline_choice import public_instance, validate_item, answer_prompt
from tasks.offline_design import grouped_record

RELEASE = STAGE / 'release'


def item_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def english_only(value):
    return not any(CJK.search(s) for s in strings(value))


def replace_values(value, mapping):
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, dict):
        return {k: replace_values(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [replace_values(v, mapping) for v in value]
    return value


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def rebind_documents(documents, source_hashes):
    """Resolve content-hash dependencies before writing any installed artifact."""
    by_hash = {}
    for path, old_sha in source_hashes.items():
        by_hash.setdefault(old_sha, []).append(path)
    resolved, mapping, pending = {}, {}, set()

    def resolve(path):
        if path in resolved:
            return resolved[path]
        if path in pending:
            raise ValueError('Cycle in source file bindings: ' + path)
        pending.add(path)
        value = documents[path]
        referenced = set(strings(value)) & by_hash.keys()
        for old_sha in referenced:
            targets = by_hash[old_sha]
            if path in targets:
                continue  # An embedded historical source hash is not a self-checksum.
            candidates = {hashlib.sha256(encode(resolve(target))).hexdigest() for target in targets}
            if len(candidates) != 1:
                raise ValueError('Identical source files produced different translations')
            mapping[old_sha] = candidates.pop()
        value = replace_values(value, mapping)
        resolved[path] = value
        pending.remove(path)
        mapping[source_hashes[path]] = hashlib.sha256(encode(value)).hexdigest()
        return value

    for path in documents:
        resolve(path)
    return resolved, mapping


def english_examples(items):
    lines = ['# SocialFlux offline T1–T3: English question bank', '',
             '300 questions across 50 scenarios. Reference answers and translations remain pending human review.',
             'Answer with one option letter, or JSON such as {"answer":"B"}.', '']
    for item in items:
        lines += [f"## {item['instance_id']} · {item['task']} / {item['subtype']}", '',
                  'Design difficulty: ' + item['analysis']['design_difficulty'], '',
                  '```json', json.dumps(public_instance(item), ensure_ascii=False, indent=2), '```', '',
                  '**Reference answer (pending review): ' + item['authoring']['answer'] + '**', '',
                  item['authoring']['rationale'], '',
                  'Difficulty rationale: ' + (item['analysis']['difficulty_reason'] or 'Direct, consistent evidence.'), '']
    return '\n'.join(lines)


def prepare():
    completed = STAGE / 'release_report.json'
    if completed.exists() and load(completed).get('status') == 'installed':
        return load(completed)
    original = [json.loads(s) for s in (BANK / 'items.jsonl').read_text().splitlines() if s]
    original_by_id = {x['instance_id']: x for x in original}
    original_bank_sha = sha(BANK / 'items.jsonl')
    scenes = sorted({x['story_id'] for x in original})
    if len(original) != 300 or len(scenes) != 50:
        raise ValueError('Unexpected current bank scope')
    items, documents, source_hashes, caches = [], {}, {}, {}
    for scene in scenes:
        directory = STAGE / 'scenes' / scene
        status = load(directory / 'status.json')
        rows = [x for x in original if x['story_id'] == scene]
        if status['status'] != 'staged' or status['source_items_sha256'] != digest(rows):
            raise ValueError('Staged question source changed: ' + scene)
        alignment = load(directory / 'evidence_alignment.json')
        if any(sha(STAGE / 'files' / path) != expected
               for path, expected in alignment['aligned_file_hashes'].items()):
            raise ValueError('Evidence alignment is stale: ' + scene)
        localized = load(directory / 'items.json')
        same_structure(rows, localized)
        items.extend(localized)
        caches[scene] = load(directory / 'cache.json')
        _, expected = documents_for(scene, rows)
        for path in expected:
            relative = str(path.relative_to(ROOT))
            old_sha = status['source_files'][relative]
            if sha(path) != old_sha:
                raise ValueError('Source changed during translation: ' + relative)
            translated = clean(load(STAGE / 'files' / relative))
            same_structure(clean(load(path)), translated)
            if relative in documents and documents[relative] != translated:
                raise ValueError('Conflicting translation of shared source: ' + relative)
            documents[relative], source_hashes[relative] = translated, old_sha
    documents, mapping = rebind_documents(documents, source_hashes)
    file_bindings = {}
    for relative, value in documents.items():
        if not english_only(value):
            raise ValueError('Non-English source remains: ' + relative)
        target = RELEASE / relative
        atomic_json(target, value)
        file_bindings[relative] = {'original_sha256': source_hashes[relative], 'english_sha256': sha(target)}
    # Gate2 stores another full copy of the same source trajectory. Translate its
    # text too; retain its historical audit hash rather than granting a new review.
    for path in sorted((ACTIVE / 'gate2_followup/rollouts').glob('*/trajectory.json')):
        source = clean(load(path))
        localized = translate_tree(source, caches[source['scenario_id']])
        from scripts.align_english_evidence import visit_pair
        corrections = load(STAGE / 'scenes' / source['scenario_id'] / 'evidence_alignment.json')['corrections']
        for before, after in visit_pair(source, localized):
            if isinstance(before, dict) and isinstance(before.get('evidence_span'), str):
                key = digest([before['evidence_span'], after['evidence_span']])
                if key in corrections:
                    after['evidence_span'] = corrections[key]
        same_structure(source, localized)
        relative = str(path.relative_to(ROOT))
        atomic_json(RELEASE / relative, localized)
        file_bindings[relative] = {'original_sha256': sha(path), 'english_sha256': sha(RELEASE / relative)}
    items = replace_values(items, mapping)
    for item in items:
        previous = original_by_id[item['instance_id']]
        item['metadata']['language'] = 'en'
        item['metadata']['localization'] = {
            'source_item_sha256': item_sha(previous), 'source_bank_sha256': original_bank_sha,
            'kind': 'faithful_translation', 'semantic_equivalence_review': 'pending',
        }
        assert item['authoring']['answer'] == previous['authoring']['answer']
        assert item['analysis']['design_difficulty'] == previous['analysis']['design_difficulty']
        assert item['ground_truth'] == previous['ground_truth']
        validate_item(item)
        if not english_only(item) or CJK.search(answer_prompt(item)):
            raise ValueError('Non-English question or evaluation prompt')
        source = item['authoring']['construction_source']
        for path_key, hash_key in (('trajectory_path', 'trajectory_sha256'), ('scenario_path', 'scenario_sha256'),
                                   ('replay_path', 'replay_sha256')):
            if source.get(path_key):
                p = RELEASE / source[path_key]
                if not p.exists():
                    p = ROOT / source[path_key]
                if sha(p) != source[hash_key]:
                    raise ValueError('Unbound source: ' + source[path_key])
        oracle = item['authoring']['oracle_reference']
        if sha(RELEASE / oracle['packet_path']) != oracle['packet_sha256']:
            raise ValueError('Oracle packet binding changed')
    items.sort(key=lambda item: list(original_by_id).index(item['instance_id']))
    output = RELEASE / BANK.relative_to(ROOT)
    manifest = write_bundle(items, output)
    prior_manifest = load(BANK / 'manifest.json')
    manifest = {**prior_manifest, **manifest, 'format': prior_manifest['format'], 'language': 'en',
                'localization': {'source_bank_sha256': original_bank_sha, 'semantic_equivalence_review': 'pending',
                                 'source_text_copies_removed': True, 'migration': str(STAGE.relative_to(ROOT))}}
    save_text(output / 'records.jsonl', ''.join(json.dumps(grouped_record(i), ensure_ascii=False) + '\n' for i in items))
    save_text(output / 'examples.md', english_examples(items) + '\n')
    index = {x['instance_id']: x for x in items}
    media = replace_values(load(BANK / 'media.json'), mapping)
    for identity, assets in media.items():
        item = index[identity.removesuffix('-video')]
        source = item['authoring']['construction_source']
        trajectory = documents[source['trajectory_path']]
        turns = {str(t['turn_id']).removeprefix('t'): t for t in trajectory['turns']}
        visible = {t['turn_id']: t for key in ('history', 'history_a', 'history_b') for t in item['input'].get(key, [])}
        for asset in assets:
            assert asset['source_binding']['trajectory_sha256'] == source['trajectory_sha256']
            assert sha(Path(asset['path'])) == asset['sha256']
            for frame in asset.get('frames', []):
                assert sha(Path(frame['path'])) == frame['sha256']
            for evidence_id in asset['evidence_ids']:
                prefix, _, turn = evidence_id.rpartition(':')
                if not turn_matches(visible[evidence_id], turns[turn.removeprefix('t')], prefix + ':' if prefix else ''):
                    raise ValueError(f'Translated video evidence differs: {identity}, {evidence_id}')
    paired = []
    for line in (BANK / 'paired.items.jsonl').read_text().splitlines():
        prior = json.loads(line)
        identity = prior['metadata']['modality_pair_id']
        current = deepcopy(index[identity])
        current.update(instance_id=prior['instance_id'], modality=prior['modality'])
        current['metadata']['modality_pair_id'] = identity
        for key in ('media_manifest', 'media_human_review', 'matched_assets'):
            if key in prior['authoring']:
                current['authoring'][key] = deepcopy(prior['authoring'][key])
        validate_item(current)
        paired.append(current)
    for filename, rows in (('paired.items.jsonl', paired), ('paired.public.jsonl', [public_instance(i) for i in paired])):
        save_text(output / filename, ''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in rows))
    atomic_json(output / 'media.json', media)
    report = load(BANK / 'pairing_report.json')
    report.update(items_sha256=sha(output / 'items.jsonl'), media_sha256=sha(output / 'media.json'), language='en')
    atomic_json(output / 'pairing_report.json', report)
    manifest['media_pairing_report_sha256'] = sha(output / 'pairing_report.json')
    atomic_json(output / 'manifest.json', manifest)
    # Publish the same English projection for the live rollout view, without source quotations.
    for scene in scenes:
        directory = next(ACTIVE.glob('*_' + scene + '_gpt'))
        source = next(directory / name for name in ('trajectory.json', 'partial_trajectory.json', 'checkpoint.json')
                      if (directory / name).exists())
        trajectory = documents[str(source.relative_to(ROOT))]
        if not trajectory.get('turns'):
            continue
        scenario_path = index[next(k for k in index if index[k]['story_id'] == scene)]['authoring']['construction_source']['scenario_path']
        scenario = load(ROOT / scenario_path)
        review = export_projection(scenario, trajectory)
        review['localization'] = {'language': 'en', 'kind': 'english_canonical',
                                 'source_artifact': str(source.relative_to(ROOT)),
                                 'source_projection_sha256': digest(review),
                                 'source_original_sha256': source_hashes[str(source.relative_to(ROOT))],
                                 'source_text_copies_removed': True, 'human_review_status': 'pending',
                                 'semantic_equivalence_review': 'pending'}
        mechanical = check_export(clean(load(source)), deepcopy(review))
        if mechanical['unresolved_translation_quotes']:
            raise ValueError('Unaligned current rollout evidence: ' + scene)
        review['localization']['mechanical_checks'] = mechanical
        english = RELEASE / directory.relative_to(ROOT) / 'english'
        atomic_json(english / 'review.json', review)
        atomic_json(english / 'string_cache.json', caches[scene])
        atomic_json(english / 'trajectory.json', {**review['rollout'], 'localization': review['localization']})
        atomic_json(english / 'scenario.json', scenario)
        atomic_json(english / 'status.json', {'scenario_id': scene, 'status': 'completed', 'language': 'en',
                    'turns': len(trajectory['turns']), 'human_review_status': 'pending'})
        dialogue = '\n\n'.join(f"Turn {t['turn_id']}\nEvaluated agent: {t['policy_action']['text']}\nEnvironment: {t['environment_response']}" for t in trajectory['turns'])
        save_text(RELEASE / directory.relative_to(ROOT) / 'dialogue.txt', dialogue + '\n')
    summary = {'status': 'prepared', 'language': 'en', 'original_bank_sha256': original_bank_sha,
               'english_bank_sha256': sha(output / 'items.jsonl'), 'items': len(items), 'scenarios': len(scenes),
               'tasks': dict(Counter(i['task'] for i in items)),
               'hard_by_task': dict(Counter(i['task'] for i in items if i['analysis']['design_difficulty'] == 'hard')),
               'numeric_ids_answers_and_difficulty_preserved': True,
               'memory_reconstruction': str((STAGE / 'memory_reconstruction.json').relative_to(ROOT)),
               'generation_provenance_hashes_retained': True, 'semantic_equivalence_review': 'pending',
               'evidence_alignment': {scene: load(STAGE / 'scenes' / scene / 'evidence_alignment.json')['counts'] for scene in scenes},
               'source_files': file_bindings, 'media_pairs': len(paired) // 2, 'media_video_files': len({a['sha256'] for rows in media.values() for a in rows})}
    atomic_json(STAGE / 'release_report.json', summary)
    return summary


def install():
    report = load(STAGE / 'release_report.json')
    if report['status'] == 'installed':
        return report
    if (report['status'] not in {'prepared', 'installing'}
            or sha(BANK / 'items.jsonl') not in {report['original_bank_sha256'], report['english_bank_sha256']}):
        raise ValueError('Prepared release no longer matches current bank')
    if report.get('media_validation', {}).get('status') != 'passed':
        raise ValueError('English media and participant bindings must pass before installation')
    for relative, binding in report['source_files'].items():
        if (sha(ROOT / relative) not in {binding['original_sha256'], binding['english_sha256']}
                or sha(RELEASE / relative) != binding['english_sha256']):
            raise ValueError('Source or staged artifact changed before installation: ' + relative)
    report['status'] = 'installing'
    atomic_json(STAGE / 'release_report.json', report)
    # Inputs and all checks are complete before the first installed file changes.
    paths = sorted(p for p in RELEASE.rglob('*') if p.is_file())
    participant = load(RELEASE / report['media_validation']['participant_package'])
    selected_media = {Path(video['url']).name for video in participant['videos']}
    for source in paths:
        relative = source.relative_to(RELEASE)
        if (relative.parts[:4] == ('web', 'participant_demo', 'public', 'media')
                and relative.name not in selected_media):
            continue  # Unselected temporary copies never overwrite shared assets.
        if relative == Path('web/participant_demo/data/multimodal.json'):
            continue  # Existing participant sessions retain their frozen release.
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.english-migration.tmp')
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    removed = []
    for directory in sorted(ACTIVE.glob('*_GPT50_*_gpt')):
        # These are redundant human-readable Chinese renderings. The full English
        # trajectory and its numeric evidence have been checked and installed.
        for name in ('review.txt', 'evidence_review.txt'):
            path = directory / name
            if path.is_file() and CJK.search(path.read_text()):
                removed.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path)})
                path.unlink()
        path = directory / 'dialogue.txt'
        source = next(directory / name for name in ('trajectory.json', 'partial_trajectory.json', 'checkpoint.json')
                      if (directory / name).exists())
        if path.exists() and not load(source).get('turns') and CJK.search(path.read_text()):
            removed.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path)})
            path.unlink()
    atomic_json(ACTIVE / 'language_cleanup.json', {
        'language': 'en', 'current_sources_only': True, 'source_text_copies_removed': True,
        'migration_report': str((STAGE / 'release_report.json').relative_to(ROOT)),
        'historical_reviews': 'not_automatically_rebound_to_translated_sources'})
    report.update(status='installed', deleted_chinese_renderings=removed)
    atomic_json(STAGE / 'release_report.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    result = install() if args.install else prepare()
    print(json.dumps({k: v for k, v in result.items() if k not in ('source_files', 'deleted_chinese_renderings')}, indent=2))
