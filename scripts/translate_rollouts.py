#!/usr/bin/env python3
"""Publish source-bound English exports as a rollout batch progresses."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.localization import atomic_json, digest, export_projection, translate_export
from pipeline.translation_checks import check_export
from providers.factory import build_provider
from scripts.run_role_visible_shadow_pilot import RoleLogProvider


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def translate_case(source, case, index, config):
    directory = source / f"{index:02d}_{case['scenario_id']}_gpt"
    artifact = next((directory / n for n in ('trajectory.json', 'partial_trajectory.json', 'checkpoint.json')
                     if (directory / n).exists()), None)
    if artifact is None:
        return {'scenario_id': case['scenario_id'], 'status': 'waiting_for_source'}
    trajectory = read(artifact)
    if not trajectory or not trajectory.get('turns'):
        return {'scenario_id': case['scenario_id'], 'status': 'waiting_for_turns'}
    scenario = read(ROOT / case['candidate'])
    projection_hash = digest(export_projection(scenario, trajectory))
    output = directory / 'english'
    previous = read(output / 'review.json', {})
    if previous.get('localization', {}).get('source_projection_sha256') == projection_hash:
        return {'scenario_id': case['scenario_id'], 'status': 'completed',
                'turns': len(trajectory['turns']), 'cached': True}
    routes = read(ROOT / config['provider_routes'])
    provider_config = deepcopy(routes['provider_defaults'])
    provider_config.update(timeout=config['timeout'], max_tokens=config['sampling']['max_tokens'])
    for route in provider_config.get('candidates', []):
        route.update(timeout=config['timeout'], max_tokens=config['sampling']['max_tokens'])
    # Rotate the existing credential pool across distinct scenarios.
    candidates = provider_config.get('candidates', [])
    if candidates:
        offset = index % len(candidates)
        provider_config['candidates'] = candidates[offset:] + candidates[:offset]
    runs = output / 'calls' / projection_hash[:16]
    run = runs / f"attempt_{len(list(runs.glob('attempt_*'))) + 1:03d}"
    provider = RoleLogProvider(build_provider(provider_config), run, None)
    atomic_json(output / 'status.json', {'status': 'translating', 'source': str(artifact.relative_to(ROOT)),
                                       'source_projection_sha256': projection_hash})
    translated = translate_export(scenario, trajectory, provider, output / 'string_cache.json',
                                  sampling=config['sampling'],
                                  preserve_source_evidence=config.get('preserve_source_evidence', True))
    check_export(trajectory, translated, provider, config['sampling'])
    translated['localization']['source_artifact'] = str(artifact.relative_to(ROOT))
    translated['localization']['provider'] = provider.provenance
    atomic_json(output / 'review.json', translated)
    atomic_json(output / 'scenario.json', translated['scenario'])
    atomic_json(output / 'trajectory.json', {**translated['rollout'], 'localization': translated['localization']})
    result = {'scenario_id': case['scenario_id'], 'status': 'completed', 'turns': len(trajectory['turns']),
              'source_projection_sha256': projection_hash, 'human_review_status': 'pending'}
    atomic_json(output / 'status.json', result)
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--scenario-manifest', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/gpt50_experiment/localization.json')
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    source = args.source_root.resolve()
    config = read(args.config)
    cases = read(args.scenario_manifest)['cases']
    status_file = source / 'translation_job.json'
    state = {'status': 'running', 'output_language': 'en', 'rows': read(status_file, {}).get('rows', {}),
             'pid': __import__('os').getpid(), 'human_review_status': 'pending'}
    atomic_json(status_file, state)
    while True:
        with ThreadPoolExecutor(max_workers=config['translation_workers']) as pool:
            futures = {pool.submit(translate_case, source, case, i, config): (i, case)
                       for i, case in enumerate(cases)}
            for future in as_completed(futures):
                i, case = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {'scenario_id': case['scenario_id'], 'status': 'translation_error',
                              'error_type': type(exc).__name__, 'error': str(exc)}
                    atomic_json(source / f"{i:02d}_{case['scenario_id']}_gpt/english/status.json", result)
                    print(json.dumps(result), flush=True)
                state['rows'][str(i)] = result
                state['completed_scenarios'] = sum(r['status'] == 'completed' for r in state['rows'].values())
                atomic_json(status_file, state)
        if not args.watch or read(source / 'results.json', {}).get('status') == 'completed':
            state['status'] = 'finished_with_errors' if any(r['status'] == 'translation_error' for r in state['rows'].values()) else 'completed_available'
            atomic_json(status_file, state)
            break
        time.sleep(20)


if __name__ == '__main__':
    main()
