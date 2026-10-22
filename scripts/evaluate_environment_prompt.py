#!/usr/bin/env python3
"""Bounded current-prompt diagnostic on frozen development checkpoints.

Uses the canonical unified environment. Source model agreement is diagnostic,
never human correctness; failures remain in the denominator.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.delta_mapper import flatten_state
from environment.unified_appraisal import UnifiedEnvironmentFactory
from evaluation.backbone_sensitivity import compare_transitions
from pipeline.runtime import build_environment_factory
from shared.artifacts import atomic_json

DEFAULT_SOURCE = ROOT / 'data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/unified_current_trust_v1_gpt50_active'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def environment_config(deployment):
    env = deepcopy(read(ROOT / deployment['environment_source_config'])['environment'])
    for role in ('provider', 'state_appraisal_provider', 'interaction_appraisal_provider', 'response_provider'):
        env[role] = deepcopy(deployment['provider'])
    return env


def select_cases(source, count):
    plans = read(source / 'preregistration.json')['plans']
    # Selection is fixed before any model call and independent of Qwen outcomes.
    plans = sorted(plans, key=lambda p: hashlib.sha256(
        ('qwen-environment-prompt-v1:' + p['case']['scenario_id']).encode()).hexdigest())
    selected, unavailable = [], []
    for plan in plans:
        sid = plan['case']['scenario_id']
        paths = sorted(source.glob('*_' + sid + '_*/trajectory.json'))
        if len(paths) != 1:
            unavailable.append({'scenario_id': sid, 'reason': 'no_unique_completed_source'})
            continue
        trajectory = read(paths[0])
        if len(trajectory.get('turns', [])) < 4:
            unavailable.append({'scenario_id': sid, 'reason': 'source_too_short'})
            continue
        scenario_path = ROOT / plan['case']['candidate']
        scenario = read(scenario_path)
        if scenario['initial_state'] != trajectory['initial_state']:
            raise ValueError('Source initial state mismatch: ' + sid)
        selected.append((scenario_path, paths[0], trajectory))
        if len(selected) == count:
            break
    if len(selected) != count:
        raise ValueError(f'Only {len(selected)} eligible sources; requested {count}')
    cases = []
    for i, (scenario_path, path, trajectory) in enumerate(selected):
        turns = trajectory['turns']
        for index in (1, len(turns) // 2):
            turn = turns[index]
            cases.append({
                'case_id': trajectory['scenario_id'] + '_' + turn['turn_id'],
                'kind': 'matched_checkpoint', 'scenario_id': trajectory['scenario_id'],
                'scenario': str(scenario_path), 'scenario_sha256': sha(scenario_path),
                'source': str(path), 'source_sha256': sha(path),
                'turn_id': turn['turn_id'], 'action': turn['policy_action'],
            })
        if i < 3:
            control = deepcopy(cases[-1])
            control.update(case_id=control['case_id'] + '_neutral', kind='neutral_control',
                           action={'text': 'I am listening. Please continue.'})
            cases.append(control)
    return cases, unavailable


def run_case(case, env_config, output):
    for key in ('scenario', 'source'):
        if sha(case[key]) != case[key + '_sha256']:
            raise ValueError('Frozen input changed: ' + case[key])
    scenario, source = read(case['scenario']), read(case['source'])
    reference = next(t for t in source['turns'] if t['turn_id'] == case['turn_id'])
    env = UnifiedEnvironmentFactory(build_environment_factory(scenario, env_config))()
    env.restore(deepcopy(reference['environment_snapshot_before']), episode_id=case['case_id'])
    providers = {
        'state': env.state_updater.state_appraiser.provider,
        'interaction': env.state_updater.interaction_appraiser.provider,
        'response': env.response_generator.provider,
    }
    row = {**case, 'status': 'failed', 'formal_admission': False, 'human_review_status': 'pending'}
    started = time.monotonic()
    try:
        _, turn = env.step(deepcopy(case['action']))
        atomic_json(output / case['case_id'] / 'turn.json', turn)
        delta = flatten_state(turn['numeric_state_delta'])
        row.update(status='completed', response=turn['environment_response'],
                   changed_state_variables={k: v for k, v in delta.items() if v},
                   numeric_dynamics_delta=turn['numeric_dynamics_delta'])
        if case['kind'] == 'matched_checkpoint':
            row['source_model_comparison'] = compare_transitions(reference, turn)
        row['state_bounds_valid'] = all(0 <= x <= 10 for x in flatten_state(turn['state_after']).values())
        row['state_variable_set_preserved'] = set(flatten_state(turn['state_before'])) == set(flatten_state(turn['state_after']))
    except Exception as exc:
        row.update(error_type=type(exc).__name__, error=str(exc),
                   diagnostics=getattr(exc, 'diagnostics', []))
    finally:
        row['seconds'] = round(time.monotonic() - started, 3)
        row['provider_metrics'] = {k: p.metrics for k, p in providers.items()}
        row['request_count'] = sum(v.get('request_count', 0) for v in row['provider_metrics'].values())
        row['first_pass'] = row['status'] == 'completed' and row['request_count'] == 3
        for name, provider in providers.items():
            atomic_json(output / case['case_id'] / (name + '_requests.json'), provider.audit_records)
        atomic_json(output / case['case_id'] / 'result.json', row)
    return row


def summarize(rows):
    success = [r for r in rows if r['status'] == 'completed']
    comparisons = [r['source_model_comparison'] for r in success if 'source_model_comparison' in r]
    active = sum(c['active_union_count'] for c in comparisons)
    def weighted(key):
        return sum((c[key] or 0) * c['active_union_count'] for c in comparisons) / active if active else None
    return {
        'attempted': len(rows), 'completed': len(success), 'failed': len(rows) - len(success),
        'first_pass_count': sum(r['first_pass'] for r in rows),
        'request_count': sum(r['request_count'] for r in rows),
        'completion_rate': len(success) / len(rows) if rows else None,
        'median_seconds': statistics.median(r['seconds'] for r in success) if success else None,
        'max_seconds': max((r['seconds'] for r in success), default=None),
        'matched_success_count': len(comparisons),
        'active_union_dimensions': active,
        'source_model_active_direction_agreement': weighted('active_union_direction_agreement'),
        'source_model_active_sign_reversal_rate': weighted('active_union_true_sign_reversal_rate'),
        'neutral_controls': [{k: r.get(k) for k in ('case_id', 'status', 'changed_state_variables')} for r in rows if r['kind'] == 'neutral_control'],
        'human_correctness_measured': False,
        'formal_admission': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment', type=Path, default=ROOT / 'configs/qwen_local_deployment.json')
    parser.add_argument('--source-root', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario-count', type=int, default=6)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--run-prepared', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    manifest_path = output / 'manifest.json'
    if args.run_prepared:
        manifest = read(manifest_path)
        for path, expected in manifest['runtime_sha256'].items():
            if sha(ROOT / path) != expected:
                raise ValueError('Runtime changed since preparation: ' + path)
        if (output / 'results.json').exists():
            raise FileExistsError('Use a new output directory for a new run')
    else:
        if manifest_path.exists():
            raise FileExistsError('Already prepared; use --run-prepared or a new directory')
        deployment = read(args.deployment)
        cases, unavailable = select_cases(args.source_root.resolve(), args.scenario_count)
        # Copy both source material and runtime now, so an hours-long model
        # download cannot silently move the diagnostic onto a different prompt.
        for case in cases:
            for key in ('scenario', 'source'):
                source_path = Path(case[key])
                target = output / 'inputs' / (case[key + '_sha256'] + '.json')
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copy2(source_path, target)
                case[key + '_origin'] = str(source_path)
                case[key] = str(target)
        files = [p for d in ('environment', 'providers', 'prompts', 'schemas', 'pipeline', 'evaluation', 'shared', 'rollout', 'policies', 'memory', 'utils', 'tasks', 'offline', 'scenario_design', 'annotation')
                 for p in (ROOT / d).rglob('*') if p.suffix in {'.py', '.md', '.txt', '.json'}]
        files += [Path(__file__), ROOT / 'configs/state_trust_current_evidence_v1.json', args.deployment.resolve(), ROOT / deployment['environment_source_config']]
        runtime = output / 'runtime'
        for path in files:
            target = runtime / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        manifest = {
            'version': 'environment_prompt_diagnostic_v1',
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'deployment': deployment, 'environment': environment_config(deployment),
            'frozen_runtime': str(runtime),
            'cases': cases, 'unavailable_sources': unavailable,
            'runtime_sha256': {str(p.relative_to(ROOT)): sha(p) for p in files},
            'max_transport_attempts': 1, 'structured_attempts_per_stage': 3, 'response_attempts': 4,
            'interpretation': 'Development diagnostic. Source model agreement is not human correctness. Neutral controls may legitimately change state in context.',
            'formal_admission': False,
        }
        atomic_json(manifest_path, manifest)
    print(json.dumps({'case_count': len(manifest['cases']), 'manifest': str(manifest_path)}), flush=True)
    if args.prepare_only:
        return
    rows = []
    for case in manifest['cases']:
        row = run_case(case, manifest['environment'], output)
        rows.append(row)
        atomic_json(output / 'results.json', {'summary': summarize(rows), 'records': rows})
        print(json.dumps({k: row.get(k) for k in ('case_id', 'status', 'seconds', 'request_count', 'error')}, ensure_ascii=False), flush=True)
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
