#!/usr/bin/env python3
"""One user-approved trust/schema validation; no semantic resampling."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from environment.unified_appraisal import UnifiedStateAppraiser, SchemaBoundInteractionAppraiser, trust_policy, PROFILE
from environment.actor_bound_appraisal import BASE_PROMPT
from rollout.configuration import load_rollout_config
from providers.factory import public_provider_config
from scripts import validate_actor_bound_state as previous
from scripts import validate_state_context_samples as v
from scripts.resume_state_context_validation import DeadlineProvider
from pipeline.runtime import appraisal_route_config as route_config

CONFIG = ROOT / 'configs/gpt50_experiment/state_unified_v1_candidate.json'
OUT = v.BASE / 'unified_current_trust_v1_fixed'
SOURCE = v.BASE / 'actor_bound_v1_fixed'
SHADOW = v.BASE / 'observed_evidence_v6_shadow_six'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare():
    config = v.load(CONFIG)
    env = load_rollout_config(ROOT / config['base_rollout_config'])['environment']
    prior = v.load(SOURCE / 'prepared_requests.json')
    v.PROMPT = BASE_PROMPT
    v.ModelStateAppraiser = UnifiedStateAppraiser
    prepared = []
    for i, before in enumerate(prior):
        case = deepcopy(before['case'])
        if i >= 12:
            case['label_status'] = 'protocol_confirmed_boundary_control'
            case['label_confirmation'] = {'basis': 'User approved unified trust rule and requested confirmation of these four unchanged controls',
                'reviewer': 'assistant_under_user_approved_protocol', 'independent_human_annotation': False,
                'previous_preregistered_input_sha256': sha(SOURCE / 'prepared_requests.json'),
                'magnitude_label_status': 'reference_only_not_formally_adjudicated'}
        item = v.prepare_case(case, env)
        restored = deepcopy(item['payload'])
        if 'relationship.trust' in restored['state_semantics']['variables']:
            restored['state_semantics']['variables']['relationship.trust'] = deepcopy(before['payload']['state_semantics']['variables']['relationship.trust'])
        assert restored == before['payload'], 'Unexpected non-trust input change'
        assert item['request']['generation'] == before['request']['generation'], 'Sampling changed'
        prepared.append(item)
    assert prepared[2]['request'] == prepared[10]['request']
    smoke = []
    for slot, name, scenario_file in [(4, '04_CF150_014_claude', 'claude_014.json'), (5, '05_CF150_044_claude', 'claude_044.json')]:
        raw = v.load(SHADOW / name / 'calls/interaction_appraisal/requests.json')[0]
        old = json.loads(raw['messages'][1]['content'].split('## Input\n', 1)[1])
        kwargs = {key: deepcopy(old.get(key)) for key in ['action', 'previous_state', 'previous_dynamics', 'memory', 'longitudinal_context', 'interaction_ledger', 'appraisal_context']}
        scenario = v.load(v.BASE / 'observed_evidence_v6_pilot_preparation/scenarios' / scenario_file)
        capture = v.Capture()
        try:
            SchemaBoundInteractionAppraiser(scenario, capture, env['interaction_appraisal_sampling']).appraise(**kwargs)
        except v.Captured:
            pass
        now = json.loads(capture.request['messages'][1]['content'].split('## Input\n', 1)[1])
        for key in kwargs:
            assert now.get(key) == old.get(key), 'Interaction smoke snapshot changed: ' + key
        smoke.append({'case_id': scenario['scenario_id'] + '_interaction_schema_regression', 'scenario': scenario,
                      'kwargs': kwargs, 'request': capture.request,
                      'source': str((SHADOW / name / 'calls/interaction_appraisal/requests.json').relative_to(ROOT))})
    return config, env, prepared, smoke


def run_smoke(index, item, env, route):
    directory = OUT / f"interaction_{index}_{item['case_id']}"
    provider = v.LoggedProvider(DeadlineProvider(route), directory, item['request'])
    started = time.monotonic()
    result = {'case_id': item['case_id'], 'source': item['source']}
    try:
        output = SchemaBoundInteractionAppraiser(item['scenario'], provider, env['interaction_appraisal_sampling']).appraise(**item['kwargs'])
        audits = output['provider_audit_records']
        result.update(status='completed', output=output, call_complete=bool(audits) and all(r.get('complete') is True for r in audits),
                      schema_repair_attempts=len(output['request_retry_diagnostics']))
    except Exception as exc:
        result.update(status='call_failure', error_type=type(exc).__name__, error=str(exc),
                      diagnostics=getattr(exc, 'diagnostics', []), last_raw=getattr(exc, 'last_raw', None))
    result['elapsed_seconds'] = time.monotonic() - started
    v.save(directory / 'result.json', result)
    print('INTERACTION', item['case_id'], result['status'], flush=True)
    return result


def summarize(report, prepared):
    previous.summarize(report, prepared)
    report['summary']['protocol_confirmed_boundary_controls'] = report['summary'].pop('new_provisional_boundaries')
    rows = list(report['interaction_rows'].values())
    report['interaction_schema_gate_passed'] = len(rows) == 2 and all(r['status'] == 'completed' and r.get('call_complete') for r in rows)
    report['mechanical_gate_passed'] = report['recognition_update_gate_passed'] and report['interaction_schema_gate_passed']
    report['next_stage'] = 'requires_semantic_review_before_three_trajectories' if report['mechanical_gate_passed'] else 'not_released'
    report['formal_human_annotation_status'] = 'not_started'


def review(report, prepared):
    previous.write_review(report, prepared)
    path = OUT / 'review.txt'
    text = path.read_text().replace('原先预设', '原先预设')
    text = text.replace('新边界标签为调用前预设，未人工确认；不冒充正式准确率。',
                        '四个边界按用户认可口径、沿用调用前预设并经助手复核；不是独立正式人工 annotation。')
    text += '\nInteraction schema 回归：\n'
    for row in report['interaction_rows'].values():
        text += row['case_id'] + '：' + row['status'] + '；' + row.get('error', '完整结构化结果已保存') + '\n'
    path.write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if (OUT / 'results.json').exists():
        raise FileExistsError('One validation only; preserve all earlier outcomes')
    config, env, prepared, smoke = prepare()
    schedule = [0, 1, 3, 12, 13, 14, 15, 2, 4, 5, 6, 7, 8, 9, 10, 11]
    files = ['environment/unified_appraisal.py', 'environment/interaction_wire_schema.py', 'environment/ledger_events.py',
             'environment/actor_bound_appraisal.py', 'environment/independent_appraisal.py', 'environment/appraisal.py',
             'environment/state_ontology.py', 'environment/calibration.py', 'environment/appraisal_context.py',
             'environment/public_situation.py', 'environment/policy_context.py', 'environment/observation.py',
             'environment/state_updater.py', 'environment/env.py', 'providers/structured.py', 'rollout/runner.py',
             'prompts/state_actor_binding_v1.txt', 'prompts/interaction_schema_bound_v1.txt',
             'configs/state_trust_current_evidence_v1.json', config['base_rollout_config'], str(CONFIG.relative_to(ROOT)),
             'scripts/validate_unified_state.py', 'scripts/validate_actor_bound_state.py',
             'scripts/validate_state_context_samples.py', 'scripts/resume_state_context_validation.py',
             'prompts/environment_state_appraisal_v6_observed_evidence.md', 'prompts/manifest.json']
    freeze = {path: sha(ROOT / path) for path in files}
    requests = [{'case': p['case'], 'request': p['request'], 'payload': p['payload']} for p in prepared]
    routes = {i: route_config(env, 0 if n % 2 == 0 else 4) for n, i in enumerate(schedule)}
    smoke_routes = {i: route_config(env, 0 if i == 0 else 4) for i in range(2)}
    prereg = {'profile': PROFILE, 'schedule': schedule, 'fixed_count': 10, 'retest_indices': [10, 11], 'boundary_indices': [12, 13, 14, 15],
              'interaction_schema_smoke_cases': [s['case_id'] for s in smoke], 'workers': config['validation_workers'],
              'requests_sha256': previous.digest(requests), 'code_sha256': freeze,
              'routes': {str(k): public_provider_config(route) for k, route in routes.items()},
              'interaction_routes': {str(k): public_provider_config(route) for k, route in smoke_routes.items()},
              'semantic_resampling': False, 'exact_strength_is_gate': False,
              'next_three_preregistered': config['pilot_three'], 'full_scale_authorized': False,
              'stages': config['stages'], 'human_annotation_not_replaced_by_assistant_review': True}
    if (OUT / 'preregistration.json').exists():
        assert v.load(OUT / 'preregistration.json') == prereg, 'Frozen preparation changed'
    else:
        v.save(OUT / 'preregistration.json', prereg)
        v.save(OUT / 'prepared_requests.json', requests)
        v.save(OUT / 'interaction_prepared_requests.json', smoke)
        v.save(OUT / 'confirmed_boundary_labels.json', [p['case'] for p in prepared[12:]])
        (OUT / 'annotation_guide.txt').write_text(trust_policy()['annotation_zh'] + '\n\n'
            + '四个对照：签收回应→响应性增加；同证据换措辞→trust 不变；引用辅导员承诺→对家长 trust 不变；新的自我纠错→trust 增加。幅度正式标签仍待核验。\n'
            + '标注时分别记录：评价人、被评价人、当前行为原文、具体顾虑如何改变、是否重复、方向。不存在新增证据时不变是正确结果。\n'
            + '人工/协议标签与实际模型输出分开保存；未依本次输出修改目标答案。\n')
    print('Frozen: 16 state observations + 2 interaction schema regressions. No API calls during preparation.', flush=True)
    if not args.run:
        return
    v.OUTPUT = OUT; previous.OUT = OUT; v.build_provider = DeadlineProvider
    report = {'status': 'running', 'rows': {}, 'interaction_rows': {}, 'full_scale_authorized': False}
    summarize(report, prepared); v.save(OUT / 'results.json', report); review(report, prepared)
    with ThreadPoolExecutor(max_workers=config['validation_workers']) as pool:
        futures = {}
        # Repair the known schema failure path first, then keep every fixed observation.
        for i, item in enumerate(smoke):
            futures[pool.submit(run_smoke, i, item, env, smoke_routes[i])] = ('interaction_rows', i)
        for i in schedule:
            futures[pool.submit(previous.run_one, i, prepared[i], env, routes[i])] = ('rows', i)
        for future in as_completed(futures):
            group, i = futures[future]
            report[group][str(i)] = future.result()
            summarize(report, prepared); v.save(OUT / 'results.json', report); review(report, prepared)
    report['status'] = 'completed'
    report['code_freeze_unchanged'] = all(sha(ROOT / path) == value for path, value in freeze.items())
    summarize(report, prepared); v.save(OUT / 'results.json', report); review(report, prepared)
    print(json.dumps({'summary': report['summary'], 'mechanical_gate_passed': report['mechanical_gate_passed'],
                      'amplitude': report['amplitude_retest']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
