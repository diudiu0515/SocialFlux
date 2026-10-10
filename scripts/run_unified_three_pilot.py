#!/usr/bin/env python3
"""Three first-pass trajectories, gated by the fixed run and explicit review."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from environment.unified_appraisal import UnifiedEnvironmentFactory
from pipeline.runtime import build_environment_factory, build_policy
from rollout.runner import RolloutRunner
from evaluation.rollout_gate import audit_rollout
from scripts.run_role_visible_shadow_pilot import assemble as base_plans, RoleLogProvider, review_text
from scripts.validate_state_context_samples import BASE, load, save
from scripts import export_shadow_pilot_review as exporter
from providers.factory import public_provider_config

FIXED = BASE / 'unified_current_trust_v1_fixed'
OUT = BASE / 'unified_current_trust_v1_three'
CONFIG = ROOT / 'configs/gpt50_experiment/state_unified_v1_candidate.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plans():
    requested = load(CONFIG)['pilot_three']
    by_key = {Path(p['case']['candidate']).stem: p for p in base_plans()}
    selected = [deepcopy(by_key[key]) for key in requested]
    for plan in selected:
        plan['policy']['policy_id'] = plan['case']['policy'] + '_unified_v1_three_' + plan['case']['scenario_id']
        plan['policy']['runs'] = 1
        UnifiedEnvironmentFactory(build_environment_factory(plan['scenario'], plan['environment']))
    return selected


def run_one(index, plan):
    directory = OUT / f"{index:02d}_{plan['case']['scenario_id']}_{plan['case']['policy']}"
    factory = UnifiedEnvironmentFactory(build_environment_factory(plan['scenario'], plan['environment']))
    def logged_factory():
        environment = factory()
        state = environment.state_updater.state_appraiser
        # Log inside the request-transforming adapter, i.e. actual wire input.
        state.provider.provider = RoleLogProvider(state.provider.provider, directory / 'calls/state_appraisal', None)
        for role, component in [('interaction_appraisal', environment.state_updater.interaction_appraiser),
                                 ('response', environment.response_generator)]:
            component.provider = RoleLogProvider(component.provider, directory / 'calls' / role, None)
        environment.state_updater.provider = state.provider
        return environment
    policy = build_policy(plan['policy'])
    policy.provider = RoleLogProvider(policy.provider, directory / 'calls/policy', None)
    def checkpoint(trajectory):
        trajectory['review_only'] = True
        trajectory['formal_human_annotation_status'] = 'not_started'
        save(directory / 'checkpoint.json', trajectory)
        (directory / 'review.txt').write_text(review_text(plan, trajectory))
    row = {'scenario_id': plan['case']['scenario_id'], 'policy': plan['case']['policy'],
           'formal_admission': False, 'quality_review_status': 'pending'}
    try:
        trajectory = RolloutRunner(logged_factory, checkpoint_writer=checkpoint).run(policy, max_turns=20)
        trajectory['review_only'] = True
        save(directory / 'trajectory.json', trajectory)
        save(directory / 'gate.json', audit_rollout(trajectory))
        row.update(status='completed', turns=len(trajectory['turns']), ending=trajectory.get('ending'))
    except Exception as exc:
        row.update(status='call_or_validation_failure', error_type=type(exc).__name__, error=str(exc))
        partial = getattr(exc, 'partial_trajectory', None)
        if partial is not None:
            row['completed_turns'] = len(partial.get('turns', []))
            save(directory / 'partial_trajectory.json', partial)
    save(directory / 'result.json', row)
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row


def refresh_exports():
    exporter.BASE = OUT
    exporter.main()
    # Keep reusable export implementation unchanged; correct the slot-count label here.
    path = OUT / 'review_index.txt'
    path.write_text(path.read_text().replace('六条审核用轨迹', '三条统一口径审核用轨迹'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    selected = plans()
    public = [{'case': p['case'], 'environment': {k: public_provider_config(v) if k.endswith('provider') else v for k, v in p['environment'].items()},
               'policy': {**p['policy'], 'provider': public_provider_config(p['policy']['provider'])}, 'initial_observation': p['observation']} for p in selected]
    fixed_freeze = load(FIXED / 'preregistration.json')['code_sha256']
    for path, expected in fixed_freeze.items():
        assert sha(ROOT / path) == expected, 'Fixed code changed before pilot: ' + path
    paths = ['scripts/run_unified_three_pilot.py', 'scripts/export_shadow_pilot_review.py'] + [p['case']['candidate'] for p in selected]
    freeze = {**fixed_freeze, **{path: sha(ROOT / path) for path in paths}}
    prereg = {'status': 'prepared_not_started', 'plans': public, 'code_sha256': freeze, 'workers': 3,
              'first_pass_only': True, 'maximum_turns': 20, 'target_turns': [10, 20], 'pad_short_trajectories': False,
              'quality_review_status': 'pending', 'formal_human_annotation_status': 'not_started',
              'next_stage_if_quality_and_constructibility_review_pass': '20_scenarios', 'formal_admission': False}
    if (OUT / 'preregistration.json').exists():
        assert load(OUT / 'preregistration.json') == prereg, 'Pilot preparation changed'
    else:
        save(OUT / 'preregistration.json', prereg)
    if not args.run:
        print('Prepared three slots, no API calls.', flush=True)
        return
    fixed = load(FIXED / 'results.json')
    if fixed.get('status') != 'completed' or not fixed.get('mechanical_gate_passed') or not fixed.get('code_freeze_unchanged'):
        raise ValueError('Fixed validation gate has not passed')
    approval_path = FIXED / 'semantic_review.json'
    if not approval_path.exists():
        raise ValueError('Actual rationale subject/object and newness/direction review is required')
    approval = load(approval_path)
    if approval.get('fixed_results_sha256') != sha(FIXED / 'results.json') or not approval.get('eligible_for_three'):
        raise ValueError('Semantic review does not approve these exact fixed results')
    if (OUT / 'results.json').exists():
        raise FileExistsError('Do not replace or repeat first-pass trajectories')
    report = {'status': 'running', 'rows': {}, 'quality_review_status': 'pending', 'formal_admission': False,
              'fixed_semantic_review_sha256': sha(approval_path)}
    save(OUT / 'results.json', report)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(run_one, i, plan): i for i, plan in enumerate(selected)}
        for future in as_completed(futures):
            report['rows'][str(futures[future])] = future.result()
            save(OUT / 'results.json', report)
            refresh_exports()
    report['status'] = 'completed'
    report['code_freeze_unchanged'] = all(sha(ROOT / path) == expected for path, expected in freeze.items())
    save(OUT / 'results.json', report)
    refresh_exports()
    print('Three attempts ended. Review turn ownership, repetition, accumulation, naturalness and constructibility before 20.', flush=True)


if __name__ == '__main__':
    main()
