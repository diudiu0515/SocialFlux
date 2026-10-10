#!/usr/bin/env python3
"""One frozen actor-binding comparison, including boundary controls and repeats."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from environment.actor_bound_appraisal import ActorBoundStateAppraiser, BASE_PROMPT, PROFILE
from environment.delta_mapper import apply_semantic_deltas, flatten_state
from providers.factory import public_provider_config
from rollout.configuration import load_rollout_config
from scripts import validate_state_context_samples as v
from scripts.resume_state_context_validation import DeadlineProvider, route_config

CONFIG = ROOT / 'configs/gpt50_experiment/state_actor_bound_v1_candidate.json'
OUT = v.BASE / 'actor_bound_v1_fixed'
SOURCE = v.BASE / 'observed_evidence_v6_fixed'
SHADOW = v.BASE / 'observed_evidence_v6_shadow_six'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def cases():
    fixed = [deepcopy(x['case']) for x in v.load(SOURCE / 'prepared_requests.json')]
    reversal = {
        'case_id': 'school_t2_owner_target_reversal', 'label_status': 'provisional_predeclared_requires_human_confirmation',
        'scenario': str((v.BASE / 'observed_evidence_v6_pilot_preparation/scenarios/gpt_002.json').relative_to(ROOT)),
        'source': str((SHADOW / '00_GPT50_002_gpt/trajectory.json').relative_to(ROOT)),
        'turn_id': 't2', 'target': 'relationship.perceived_responsiveness', 'action_override': None,
        'expected_judgment': 'ordinary_new_evidence', 'expected_direction': 'increase',
        'label_rationale': 'The parent directly answers the counselor\'s scheduling question; judge the counselor\'s view of the parent, not whether the counselor answered the parent. Trust is not forced to increase.',
    }
    paraphrase = {**deepcopy(fixed[9]), 'case_id': 'trust_paraphrased_same_evidence',
        'label_status': 'provisional_predeclared_requires_human_confirmation',
        'action_override': '目前手上的材料不足以排除线人在采购期间的利益关联，所以不能拿她的话当独立佐证。仍按阶段刊出，今晚把记录支持的事实和还没核清的来源说法分开写。',
        'label_rationale': 'Restates the same admission and separation posture already in t2, without a further event or disclosure; changed wording alone is not new trust evidence.'}
    quotation = {**deepcopy(reversal), 'case_id': 'trust_quoted_other_person_commitment',
        'target': 'relationship.trust', 'expected_judgment': 'no_relevant_evidence', 'expected_direction': None,
        'action_override': '你刚才说的是“我会在名册关闭前把这些临时安排写明”。这句话里的“我”指你。',
        'label_rationale': 'The parent quotes an already observed counselor commitment and clarifies its speaker; this supplies no new evidence of the parent\'s reliability. Other constructs are not assumed unchanged.'}
    new_act = {**deepcopy(fixed[3]), 'case_id': 'trust_same_topic_new_self_correction',
        'label_status': 'provisional_predeclared_requires_human_confirmation',
        'action_override': '刚刚核对了我引用的那页采购记录，我发现我把日期看错了；此前据此作出的时间线判断需要撤回，即使因此不能赶在投票前刊出。',
        'expected_judgment': 'ordinary_new_evidence', 'expected_direction': 'increase',
        'label_rationale': 'A new admission of the reporter\'s own concrete error and withdrawal of their inference is not repetition merely because procurement evidence was already discussed. Ordinary versus decisive is reported, not a pass condition.'}
    return fixed + [reversal, paraphrase, quotation, new_act]


def prepare():
    config = v.load(CONFIG)
    if config['format'] != 'actor_bound_state_candidate_v1' or config['binding_profile'] != PROFILE:
        raise ValueError('Wrong actor-bound candidate config')
    env = load_rollout_config(ROOT / config['base_rollout_config'])['environment']
    v.PROMPT = BASE_PROMPT
    baseline = [v.prepare_case(case, env) for case in cases()]
    saved = v.load(SOURCE / 'prepared_requests.json')
    for item, old in zip(baseline[:12], saved):
        assert item['request'] == old['request'], 'Original v6 control request changed'
    # The known reversal is compared with the actual request that produced it.
    reversal_wire = v.load(SHADOW / '00_GPT50_002_gpt/calls/state_appraisal/requests.json')[1]
    assert baseline[12]['request']['messages'] == reversal_wire['messages'], 'Reversal checkpoint reconstruction changed'
    assert baseline[12]['request']['generation'] == reversal_wire['generation']
    v.ModelStateAppraiser = ActorBoundStateAppraiser
    prepared = [v.prepare_case(case, env) for case in cases()]
    for before, after in zip(baseline, prepared):
        restored = deepcopy(after['payload'])
        restored['state_semantics'].pop('actor_binding')
        for path, entry in restored['state_semantics']['variables'].items():
            entry.pop('perspective')
            entry['definition'] = before['payload']['state_semantics']['variables'][path]['definition']
        assert restored == before['payload'], 'Actor binding changed non-perspective payload fields'
        assert before['request']['generation'] == after['request']['generation']
    assert prepared[2]['request'] == prepared[10]['request'], 'Strength retest must use identical input'
    return config, env, prepared


def run_one(index, item, env, route):
    row = v.run_one(index, item, env, route)
    if row['status'] == 'completed':
        after, numeric = apply_semantic_deltas(item['kwargs']['previous_state'], row['transition']['state_delta'])
        target = item['case']['target']
        row['target_before'] = flatten_state(item['kwargs']['previous_state'])[target]
        row['target_after'] = flatten_state(after)[target]
        row['target_numeric_delta'] = flatten_state(numeric)[target]
        required = item['case']['expected_direction']
        row['final_update_correct'] = ((row['target_numeric_delta'] > 0) if required == 'increase'
                                       else (row['target_numeric_delta'] < 0) if required == 'decrease'
                                       else row['target_numeric_delta'] == 0)
        row['perspective_status'] = 'requires_actual_subject_object_review'
        row['rationale_review'] = row['state_appraisal']['perspective_review']
        directory = OUT / f"{index:02d}_{item['case']['case_id']}"
        v.save(directory / 'result.json', row)
    return row


def summarize(report, prepared):
    groups = {'original_human_confirmed_fixed': range(10), 'predeclared_retests': range(10, 12),
              'new_provisional_boundaries': range(12, 16)}
    report['summary'] = {}
    for name, indices in groups.items():
        rows = [report['rows'].get(str(i), {}) for i in indices]
        done = [row for row in rows if row.get('status') == 'completed']
        report['summary'][name] = {'scheduled': len(rows), 'complete': len(done), **{
            key: sum(bool(row.get(key)) for row in done)
            for key in ['recognition_correct', 'strength_correct', 'false_positive', 'false_negative', 'final_update_correct', 'call_complete']}}
    pair = [report['rows'].get(str(i), {}) for i in (2, 10)]
    report['amplitude_retest'] = {'identical_request': prepared[2]['request'] == prepared[10]['request'],
        'status': 'pending', 'strength_difference_is_not_update_failure': True}
    if all(row.get('status') == 'completed' for row in pair):
        report['amplitude_retest'].update(status='completed',
            no_numeric_boundary=all(0 < row['target_before'] < 10 and 0 < row['target_after'] < 10 for row in pair),
            strengths=[row['target_judgment']['semantic_strength'] for row in pair],
            deltas=[row['target_numeric_delta'] for row in pair],
            both_directionally_correct=all(row['final_update_correct'] for row in pair))
    report['recognition_update_gate_passed'] = len(report['rows']) == 16 and all(
        row.get('status') == 'completed' and row.get('recognition_correct') and row.get('final_update_correct') and row.get('call_complete')
        for row in report['rows'].values())
    report['orientation_gate'] = 'requires_semantic_review_not_name_presence'
    report['full_scale_authorized'] = False


def write_review(report, prepared):
    lines = ['人物绑定候选：本轮实际结果（完整保留，未人工通过）',
             '状态：' + report['status'], '主体/对象仍须核对实际理由；姓名出现不是正确性证明。', '']
    for i, item in enumerate(prepared):
        case = item['case']; row = report['rows'].get(str(i))
        binding = item['payload']['state_semantics']['actor_binding']
        lines += [f"{i}. {case['case_id']} [{case['label_status']}]",
                  '评价方向：' + binding['state_owner']['name'] + ' → ' + binding['relationship_target']['name'],
                  '当前行为：' + item['kwargs']['action']['text'],
                  '预设：' + case['expected_judgment'] + ' / ' + str(case['expected_direction'])]
        if row and row['status'] == 'completed':
            j = row['target_judgment']
            lines += ['实际：' + j['judgment'] + '；delta=' + str(row['target_numeric_delta']),
                      '引用：' + j['evidence_span'], '理由：' + j['rationale']]
            if i == 12:
                lines += ['反转回归：下面保留全部关系变量理由，trust 不强制更新。']
                for j in row['state_appraisal']['state_judgments']:
                    if j['variable'].startswith('relationship.'):
                        lines.append(j['variable'] + '：' + j['rationale'])
        else:
            lines.append('运行结果：' + (row.get('error', row['status']) if row else '待运行'))
        lines += ['']
    lines += ['强度复测：' + json.dumps(report.get('amplitude_retest'), ensure_ascii=False),
              '新边界标签为调用前预设，未人工确认；不冒充正式准确率。']
    (OUT / 'review.txt').write_text('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if (OUT / 'results.json').exists():
        raise FileExistsError('All first-pass results retained; no automatic reruns')
    config, env, prepared = prepare()
    schedule = [12, 14, 13, 15, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    routes = {i: route_config(env, 0 if n % 2 == 0 else 4) for n, i in enumerate(schedule)}
    files = ['environment/actor_bound_appraisal.py', 'prompts/state_actor_binding_v1.txt',
             'scripts/validate_actor_bound_state.py', str(CONFIG.relative_to(ROOT)), config['base_rollout_config'],
             'environment/independent_appraisal.py', 'environment/calibration.py', 'environment/state_ontology.py',
             'environment/appraisal_context.py', 'environment/public_situation.py', 'environment/observation.py',
             'scripts/validate_state_context_samples.py', 'scripts/resume_state_context_validation.py',
             'prompts/environment_state_appraisal_v6_observed_evidence.md', 'prompts/manifest.json']
    freeze = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in files}
    requests = [{'case': p['case'], 'request': p['request'], 'payload': p['payload']} for p in prepared]
    prereg = {'schedule': schedule, 'original_fixed': list(range(10)), 'retests': [10, 11], 'new_boundaries': list(range(12, 16)),
              'input_sha256': digest(requests), 'code_sha256': freeze, 'workers': config['validation_workers'],
              'routes': {str(i): public_provider_config(route) for i, route in routes.items()},
              'semantic_retries': 0, 'amplitude_not_a_gate': True, 'model_effort_sampling_unchanged': True,
              'new_label_status': 'provisional_predeclared_requires_human_confirmation',
              'orientation_check': 'Review actual subject and object of rationales; never auto-pass from name presence',
              'full_scale_authorized': False}
    if (OUT / 'preregistration.json').exists():
        assert v.load(OUT / 'preregistration.json') == prereg, 'Prepared candidate changed'
        assert v.load(OUT / 'prepared_requests.json') == requests, 'Prepared requests changed'
    else:
        v.save(OUT / 'preregistration.json', prereg)
        v.save(OUT / 'prepared_requests.json', requests)
        labels = ['新增边界预设（调用前固定；待人工确认）', '']
        for item in prepared[12:]:
            case = item['case']
            labels += [case['case_id'], '当前动作：' + item['kwargs']['action']['text'],
                       '目标：' + case['target'], '预设：' + case['expected_judgment'] + ' / ' + str(case['expected_direction']),
                       '依据：' + case['label_rationale'], '完整前史：']
            labels += [x['role'] + '：' + x['text'] for x in item['payload']['appraisal_context']['historical_messages']]
            labels += ['']
        (OUT / 'label_review.txt').write_text('\n'.join(labels) + '\n')
    print('Prepared 16 observations: fixed 10 + existing retests 2 + boundary controls 4; zero calls so far.', flush=True)
    if not args.run:
        return
    v.OUTPUT = OUT
    v.build_provider = DeadlineProvider
    report = {'status': 'running', 'rows': {}, 'full_scale_authorized': False}
    summarize(report, prepared); v.save(OUT / 'results.json', report); write_review(report, prepared)
    with ThreadPoolExecutor(max_workers=config['validation_workers']) as pool:
        pending = {pool.submit(run_one, i, prepared[i], env, routes[i]): i for i in schedule}
        for future in as_completed(pending):
            report['rows'][str(pending[future])] = future.result()
            summarize(report, prepared); v.save(OUT / 'results.json', report); write_review(report, prepared)
    report['status'] = 'completed'
    report['code_freeze_unchanged'] = all(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == value for path, value in freeze.items())
    summarize(report, prepared); v.save(OUT / 'results.json', report); write_review(report, prepared)
    print(json.dumps({'summary': report['summary'], 'amplitude': report['amplitude_retest']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
