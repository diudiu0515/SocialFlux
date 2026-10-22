"""Reuse the already generated English videos for the translated offline bank."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.localize_current_data import BANK, STAGE, load, sha, translate_tree, clean
from scripts.publish_english_data import RELEASE, replace_values, item_sha, english_only
from pipeline.localization import atomic_json, digest


def link_or_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha(source) != sha(target):
            raise ValueError('Existing staged media differs')
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def prepare_media():
    report = load(STAGE / 'release_report.json')
    if report['status'] != 'prepared':
        raise ValueError('Core English release must be prepared first')
    old_sha, new_sha = report['original_bank_sha256'], report['english_bank_sha256']
    old_directory = ROOT / 'data/offline_talking_head_en_v1' / old_sha[:16]
    new_relative = Path('data/offline_talking_head_en_v1') / new_sha[:16]
    destination = RELEASE / new_relative
    original = [json.loads(s) for s in (BANK / 'items.jsonl').read_text().splitlines() if s]
    items = [json.loads(s) for s in (RELEASE / BANK.relative_to(ROOT) / 'items.jsonl').read_text().splitlines() if s]
    index = {x['instance_id']: x for x in items}
    mapping = {item_sha(x): item_sha(index[x['instance_id']]) for x in original}
    mapping[old_sha] = new_sha
    mapping.update({v['original_sha256']: v['english_sha256'] for v in report['source_files'].values()})
    for p in RELEASE.glob('data/gpt50/**/english/trajectory.json'):
        original_path = ROOT / p.relative_to(RELEASE)
        if original_path.exists():
            mapping[sha(original_path)] = sha(p)
    caches = {scene: load(STAGE / 'scenes' / scene / 'cache.json') for scene in {i['story_id'] for i in items}}

    def paths(value):
        if isinstance(value, str):
            return value.replace(str(old_directory.relative_to(ROOT)), str(new_relative))
        if isinstance(value, dict):
            return {k: paths(v) for k, v in value.items()}
        if isinstance(value, list):
            return [paths(v) for v in value]
        return value

    def translate(value, scene):
        return paths(replace_values(translate_tree(clean(value), caches[scene]), mapping))

    manifest = load(old_directory / 'manifest.json')
    manifest['nodes'] = [translate(node, node['scenario_id']) for node in manifest['nodes']]
    manifest['requests'] = [translate(row, row['scenario_id']) for row in manifest['requests']]
    manifest = paths(replace_values(manifest, mapping))
    config = load(ROOT / 'configs/offline_talking_preview_en_v1.json')
    config['translations'] = [translate(row, row['scenario_id']) for row in config['translations']]
    # The source line is now the same English wording used by the existing audio.
    for row in config['translations']:
        assert row['source_text'] == row['text']
    atomic_json(RELEASE / 'configs/offline_talking_preview_en_v1.json', config)
    manifest['translation_config_sha256'] = sha(RELEASE / 'configs/offline_talking_preview_en_v1.json')
    manifest['language_migration'] = {'original_bank_sha256': old_sha, 'audio_unchanged': True,
                                    'semantic_equivalence_review': 'pending'}
    atomic_json(destination / 'manifest.json', manifest)
    atomic_json(destination / 'translations.json', config)
    nodes = {x['node_id']: x for x in manifest['nodes']}
    completed = []
    for row in load(old_directory / 'completed_nodes.json'):
        scene = nodes[row['node_id']]['scenario_id']
        translated = translate(row, scene)
        for binding in translated['bindings']:
            assert binding['item_sha256'] == item_sha(index[binding['instance_id']])
        assert translated['asset']['spoken_text'] == translated['asset']['source_public_response']
        completed.append(translated)
    atomic_json(destination / 'completed_nodes.json', completed)
    atomic_json(destination / 'preview_selection.json', paths(replace_values(load(old_directory / 'preview_selection.json'), mapping)))
    # Reuse only exact selected assets/requests; do not submit video generation.
    for source in old_directory.rglob('*'):
        if not source.is_file():
            continue
        relative = source.relative_to(old_directory)
        if relative.parts[0] in {'assets', 'frames', 'segments', 'trimmed_segments', 'requests', 'provider_states'}:
            target = destination / relative
            if source.suffix == '.json':
                value = load(source)
                value = paths(replace_values(value, mapping))
                if not english_only(value):
                    continue  # Historical provider traces do not become dataset text.
                atomic_json(target, value)
            else:
                link_or_copy(source, target)
    for name in ('speech_screen.json', 'review_findings.json'):
        source = old_directory / name
        if source.exists():
            value = paths(replace_values(load(source), mapping))
            if english_only(value):
                atomic_json(destination / name, value)
    status = load(BANK / 'talking_head_status.json')
    atomic_json(RELEASE / BANK.relative_to(ROOT) / 'talking_head_status.json', paths(replace_values(status, mapping)))

    # Export the local participant bundle against the staged bank, including all
    # original visibility and SHA checks in the established exporter.
    from scripts import export_participant_multimodal as exporter
    site_relative = Path('web/participant_demo')
    # Use a dedicated empty export directory; shared media are never cleaned.
    site = STAGE / 'participant_english_export'
    legacy = site / 'data/questions.json'
    link_or_copy(ROOT / site_relative / 'data/questions.json', legacy)
    saved_root = exporter.ROOT
    exporter.ROOT = RELEASE
    try:
        exporter.export(site, RELEASE / 'reports/experiments/2026-10-22_english_participant_export.json',
                        expected_bank_sha256=new_sha, release='offline-multimodal-review-20261022-en-v1')
    finally:
        exporter.ROOT = saved_root
        legacy.unlink()  # Frozen historical sessions are not part of this release.
    # Existing participant sessions are tied to the frozen multimodal package.
    # Supply a separate English release; deployment/session migration is separate.
    generated = site / 'data/multimodal.json'
    english_package = site / 'data/multimodal-en.json'
    generated.replace(english_package)
    public = load(english_package)
    if not english_only(public):
        raise ValueError('Chinese text remains in participant package')
    final_package = RELEASE / site_relative / 'data/multimodal-en.json'
    atomic_json(final_package, public)
    for video in public['videos']:
        name = Path(video['url']).name
        link_or_copy(site / 'public/media' / name, RELEASE / site_relative / 'public/media' / name)
    report['media_validation'] = {'status': 'passed', 'existing_video_bytes_unchanged': True,
                                'talking_head_samples': len(completed), 'participant_items': len(public['items']),
                                'participant_videos': len(public['videos']), 'public_package_english_only': True,
                                'participant_package': str(final_package.relative_to(RELEASE)),
                                'frozen_participant_releases_unchanged': True}
    atomic_json(STAGE / 'release_report.json', report)
    return report['media_validation']


if __name__ == '__main__':
    print(json.dumps(prepare_media(), indent=2))
