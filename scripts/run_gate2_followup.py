"""Bounded E4 repeat/wording controls and missing E3 recent-history control.

Uses the previous frozen 46 sources, never overwrites their evidence. Every
condition is run once; unsuccessful construction and replay remain outcomes.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from environment.unified_appraisal import UnifiedEnvironmentFactory
from evaluation.t4_multimodal import RequestBudget
from evaluation.transition_metrics import compare_transition_outputs
from offline.choice_builder import load, save, sha
from offline.oracle import now
from offline.provider_compat import OfflineLoggedProvider, OfflineRuntimeFactory, OfflineSamplingProvider
from pipeline.runtime import build_environment_factory
from prompts.loader import render_prompt
from providers.factory import build_provider
from providers.structured import complete_json
from scripts.auto_gate2_unified_gpt50 import interpret, project_history
from scripts.run_environment_interventions import (_paraphrase, load_records, load_actual_scenarios,
                                                  select_intervention_checkpoint, select_one_per_scenario)
from web.live_rollouts import ACTIVE

SOURCE = ROOT / 'data/gate2_machine_20261020_complete'
RUN = ROOT / 'data/gate2_followup_20261022'
TRANSPORT_TIMEOUT = 180


class CountedProvider:
    def __init__(self, provider, budget):
        self.provider, self.budget = provider, budget

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def complete(self, messages, **kwargs):
        self.budget.take()
        return self.provider.complete(messages, **kwargs)


def count_leaves(provider, budget):
    if 'candidates' in vars(provider):
        provider.candidates = [count_leaves(p, budget) for p in provider.candidates]
    elif 'provider' in vars(provider):
        provider.provider = count_leaves(provider.provider, budget)
    else:
        return CountedProvider(provider, budget)
    return provider


def bounded(config):
    result = deepcopy(config)
    result.update(timeout=TRANSPORT_TIMEOUT, max_transport_attempts=1, retry_backoff_seconds=0)
    if 'candidates' in result:
        result['candidates'] = [bounded(p) for p in result['candidates']]
    return result


def recent_snapshot(snapshot, count=3):
    result = deepcopy(snapshot)
    # The canonical history has one row per speaker, not one row per turn.
    history = result.get('history', [])
    turn_ids = list(dict.fromkeys(row['turn_id'] for row in history))[-count:]
    result['history'] = [row for row in history if row['turn_id'] in turn_ids]
    return project_history(result)


def aggregate_metrics(records, name):
    groups = [r['comparisons'][name]['overall'] for r in records if name in r.get('comparisons', {})]
    n = sum(g['active_union_count'] for g in groups)
    def weighted(metric, denominator):
        count = sum(g[denominator] for g in groups)
        return round(sum((g[metric] or 0) * g[denominator] for g in groups) / count, 4) if count else None
    return dict(pairs=len(groups), active_dimensions=n,
        direction_agreement=weighted('active_union_direction_agreement', 'active_union_count'),
        change_agreement=weighted('active_union_change_no_change_agreement', 'active_union_count'),
        reversal_rate=weighted('active_union_true_sign_reversal_rate', 'active_union_count'),
        all_dimension_agreement=weighted('exact_direction_agreement', 'variable_count'))


def summarize(run, manifest, status, budget):
    rows = [load(p) for p in sorted((run / 'results').glob('*.json'))]
    result = dict(run_id=run.name, updated_at=now(), status=status, pid=os.getpid(),
        expected=len(manifest['scenario_ids']), recorded=len(rows), api_requests=budget.count,
        request_limit=budget.limit, threshold=.8, human_review='pending', formal_admission=False,
        semantic_equivalence=dict(Counter(r.get('equivalence_status', 'unavailable') for r in rows)),
        condition_counts={c:dict(Counter(r.get('conditions', {}).get(c, 'not_run') for r in rows))
                          for c in ('original', 'repeat', 'paraphrase', 'recent3')},
        comparisons={name:aggregate_metrics(rows, name) for name in ('repeat', 'paraphrase', 'recent3')},
        failures=[{'scenario_id':r['scenario_id'], 'steps':{k:v['type'] for k,v in r.get('errors', {}).items()}}
                  for r in rows if r.get('errors')],
        note='Same frozen sources and 70% checkpoint. Original/repeat/paraphrase/recent3 are fresh replays; no cross-run score pooling. E4 excludes machine-rejected paraphrases; human equivalence remains pending.')
    save(run / 'summary.json', result)
    return result


def execute(run, trajectory, scenario, config, old_pairs, budget, reuse_run=None):
    sid = trajectory['scenario_id']
    path = run / 'results' / (sid + '.json')
    if path.exists():
        return load(path)
    checkpoint = select_intervention_checkpoint(trajectory)
    row = dict(scenario_id=sid, trajectory_id=trajectory['trajectory_id'], checkpoint_turn_id=checkpoint['turn_id'],
               conditions={}, comparisons={}, errors={}, equivalence_status='unavailable')
    construction = OfflineLoggedProvider(OfflineSamplingProvider(CountedProvider(
        build_provider(bounded(config['construction']['provider'])), budget)), run / 'calls' / sid / 'construction')
    sampling = deepcopy(config['construction']['sampling'])
    original = checkpoint['policy_action']
    try:
        previous = old_pairs.get(sid)
        if previous and previous['source_trajectory_id'] == trajectory['trajectory_id'] and previous['original_action'] == original['text']:
            paraphrase = previous['paraphrase']
            row['paraphrase_origin'] = 'previous_fixed_candidate'
        else:
            paraphrase = _paraphrase(construction, sampling, trajectory, checkpoint,
                                    prompt_id='environment_paraphrase_probe_v2', max_attempts=2)
            row['paraphrase_origin'] = 'same_language_v2'
        row.update(original_action=original['text'], paraphrase=paraphrase)
        def validate(value):
            if set(value) != {'equivalent', 'reason'} or not isinstance(value['equivalent'], bool) or not isinstance(value['reason'], str):
                raise ValueError('invalid equivalence judgment')
            return value
        row['equivalence'] = complete_json(construction, [{'role':'user','content':render_prompt(
            'environment_paraphrase_equivalence_v1', dict(original_action=original['text'], paraphrase=paraphrase,
                context=checkpoint['observation'].get('history', [])[-4:]))}], sampling, validate,
                context='independent paraphrase equivalence', max_attempts=2)
        row['equivalence_status'] = 'machine_equivalent' if row['equivalence']['equivalent'] else 'machine_rejected'
    except Exception as exc:
        row['errors']['construction'] = dict(type=type(exc).__name__, message=str(exc))
    snapshot = checkpoint['environment_snapshot_before']
    outputs = {}
    for condition in ('original', 'repeat', 'paraphrase', 'recent3'):
        if condition == 'paraphrase' and row['equivalence_status'] != 'machine_equivalent':
            row['conditions'][condition] = 'equivalence_unavailable'
            continue
        if condition == 'recent3' and len({h['turn_id'] for h in snapshot.get('history', [])}) <= 3:
            row['conditions'][condition] = 'no_history_removed'
            continue
        try:
            cached = reuse_run / 'outputs' / sid / (condition + '.json') if reuse_run else None
            if condition in ('original', 'repeat') and cached and cached.exists():
                output = load(cached)
                outputs[condition] = output
                save(run / 'outputs' / sid / (condition + '.json'), output)
                row.setdefault('reused_outputs', {})[condition] = dict(path=str(cached.relative_to(ROOT)), sha256=sha(cached))
                row['conditions'][condition] = 'completed'
                if condition != 'original' and 'original' in outputs:
                    row['comparisons'][condition] = compare_transition_outputs(outputs['original'], output)
                continue
            environment_config = deepcopy(config['environment'])
            for key in ('state_appraisal_provider', 'interaction_appraisal_provider', 'response_provider'):
                environment_config[key] = bounded(environment_config[key])
            factory = OfflineRuntimeFactory(UnifiedEnvironmentFactory(build_environment_factory(scenario, environment_config)),
                                             run / 'calls' / sid / condition)
            env = factory()
            for appraiser in (env.state_updater.state_appraiser, env.state_updater.interaction_appraiser):
                appraiser.provider = count_leaves(appraiser.provider, budget)
            env.restore(recent_snapshot(snapshot) if condition == 'recent3' else project_history(snapshot))
            output = interpret(env, {'text':row['paraphrase']} if condition == 'paraphrase' else original)
            outputs[condition] = output
            save(run / 'outputs' / sid / (condition + '.json'), output)
            row['conditions'][condition] = 'completed'
            if condition != 'original' and 'original' in outputs:
                row['comparisons'][condition] = compare_transition_outputs(outputs['original'], output)
        except Exception as exc:
            row['conditions'][condition] = 'failed'
            row['errors'][condition] = dict(type=type(exc).__name__, message=str(exc))
    save(path, row)
    return row


def main():
    global TRANSPORT_TIMEOUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=RUN)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--output-budget-amendment', action='store_true', help='Frozen transport/output-only amendment; shares the original 600-request budget.')
    parser.add_argument('--reuse-run', type=Path, help='Reuse only completed original/repeat outputs from the stopped output-budget batch.')
    parser.add_argument('--request-budget', type=int, default=600)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    run = args.output.resolve()
    if args.output_budget_amendment:
        if run == RUN or args.request_budget != 600:
            raise ValueError('Amendment must preserve the original run and shared 600-request cap')
        TRANSPORT_TIMEOUT = 300
    reuse_run = args.reuse_run.resolve() if args.reuse_run else None
    if reuse_run and (reuse_run != ROOT/'data/gate2_followup_budget_20261022' or not args.output_budget_amendment):
        raise ValueError('Only the fixed, output-budget-amended source can supply identical original/repeat controls')
    config = load(SOURCE / 'rollout.runtime.json')
    trajectories = select_one_per_scenario(load_records(SOURCE / 'rollouts'))
    scenarios = {s['scenario_id']:s for s in load_actual_scenarios(SOURCE / 'scenarios')}
    plans = {p['case']['scenario_id']:p for p in load(ACTIVE / 'preregistration.json')['plans']}
    paths = [Path(__file__), ROOT/'scripts/run_environment_interventions.py',
             ROOT/'evaluation/transition_metrics.py', ROOT/'environment/unified_appraisal.py',
             ROOT/'prompts/environment_paraphrase_probe_v2.md', ROOT/'prompts/environment_paraphrase_equivalence_v1.md',
             SOURCE/'rollout.runtime.json', SOURCE/'gate2/paraphrase_robustness.json', ACTIVE/'preregistration.json']
    paths += sorted((SOURCE/'rollouts').glob('*/trajectory.json'))
    paths += sorted((SOURCE/'scenarios').glob('*/*.json'))
    if reuse_run:
        paths += [reuse_run/'manifest.json', reuse_run/'summary.json', reuse_run/'runner.snapshot.py']
        paths += sorted((reuse_run/'outputs').glob('*/*.json'))
    manifest = dict(scenario_ids=[t['scenario_id'] for t in trajectories], request_limit=args.request_budget,
        source_hashes={str(p.relative_to(ROOT)):sha(p) for p in paths},
        conditions=['original','repeat','paraphrase','recent3'], equivalence_attempts=2,
        construction_attempts=2, checkpoint='ceil(0.7 * source_turns)', threshold=.8,
        authorization='User requested remaining Gate2 environment checks and another semantic invariance test on 2026-10-22.',
        outcome_rule='One result per scene; retain every failure; no success resampling or threshold changes.')
    if args.output_budget_amendment:
        manifest['amendment'] = dict(reason='Initial requests repeatedly hit length with absent/truncated text; not a semantic result.',
            original_run=str(RUN.relative_to(ROOT)), shared_request_budget=str((RUN/'request_budget.json').relative_to(ROOT)),
            state_max_tokens=16000, interaction_max_tokens=12000, timeout_seconds=300,
            unchanged=['46 sources', 'checkpoint', 'prompts', 'model', 'temperature', 'seed', 'four conditions', '0.8 threshold'])
    manifest['recent3_unit'] = 'last three complete dialogue turns, retaining both speakers'
    if reuse_run:
        manifest['history_unit_repair'] = dict(source=str(reuse_run.relative_to(ROOT)),
            reason='Snapshot history rows are speaker messages; keep complete dialogue turns, not three message rows.',
            reuse='Only complete original/repeat outputs, same checkpoint/config/action; failures and interrupted calls retained in source batch.')
    if (run/'manifest.json').exists() and load(run/'manifest.json') != manifest:
        raise ValueError('Frozen follow-up changed; do not overwrite this run')
    save(run/'manifest.json', manifest)
    budget = RequestBudget((RUN if args.output_budget_amendment else run)/'request_budget.json', args.request_budget)
    if args.prepare_only:
        print(json.dumps(summarize(run, manifest, 'prepared', budget)));return
    old_pairs = {r['scenario_id']:r for r in load(SOURCE/'gate2/paraphrase_robustness.json')['records']}
    summarize(run, manifest, 'running', budget)
    save(run/'process.json', dict(pid=os.getpid(), script=str(Path(__file__).relative_to(ROOT))))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = []
        for trajectory in trajectories:
            sid = trajectory['scenario_id']
            local = deepcopy(config)
            # Per-scene registered sampling; retain the runtime's secret locations.
            for key in ('state_appraisal_sampling','interaction_appraisal_sampling','response_sampling'):
                local['environment'][key] = deepcopy(plans[sid]['environment'][key])
            if args.output_budget_amendment:
                local['environment']['state_appraisal_sampling']['max_tokens'] = 16000
                local['environment']['interaction_appraisal_sampling']['max_tokens'] = 12000
            jobs.append(pool.submit(execute, run, trajectory, scenarios[sid], local, old_pairs, budget, reuse_run))
        for job in as_completed(jobs):
            row = job.result()
            print(row['scenario_id'], row['conditions'], flush=True)
            summarize(run, manifest, 'running', budget)
    print(json.dumps(summarize(run, manifest, 'finished', budget)))


if __name__ == '__main__':
    main()
