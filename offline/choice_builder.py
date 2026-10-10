"""Source-grounded choice authoring and reproducible public/review exports."""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path
from collections import Counter

from environment.delta_mapper import flatten_state
from evaluation.leakage import assert_no_leaks
from prompts.loader import render_prompt
from providers.structured import complete_json
from tasks.offline_choice import VERSION, FAMILIES, validate_item, public_instance


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def public_turn(turn, prefix=''):
    return {'turn_id': prefix + 't' + str(turn['turn_id']).removeprefix('t'),
            'evaluated_agent': turn['policy_action']['text'],
            'environment_character': turn['environment_response'],
            'observable_expression': deepcopy(turn.get('observable_expression') or {}),
            'public_events': deepcopy((turn.get('segment_transition_after') or {}).get('public_events', []))}


def source_input(trajectory, end):
    observation = trajectory['turns'][0]['observation']
    return {'context': {'background': observation['background'],
                        'public_situation': deepcopy(observation.get('public_situation', {}))},
            'role': {k: observation['role'][k] for k in ('character_id', 'name', 'role', 'explicit_goal') if k in observation['role']},
            'target_character': deepcopy(observation['target_character']),
            'history': [public_turn(t) for t in trajectory['turns'][:end]]}


def author_call(provider, payload, validator=lambda x: x):
    return complete_json(provider, [{'role': 'user', 'content': render_prompt('offline_choice_author_v1', payload)}],
                         {'temperature': 0.2}, validator, context='offline choice author', max_attempts=2)


def assemble(raw, *, task, source, public_input, ordinal, index, replay_status='not_required', delayed_horizon=None):
    target = raw['target_spec']
    target['state_owner'] = public_input['target_character']['character_id']
    target['state_target'] = public_input['role']['character_id']
    target.setdefault('checkpoint', 't2')
    if task == 'T1' and raw['subtype'] in {'interval_change','joint_change'}:
        target['comparison_interval']={'start':'t1:after_environment_response','end':'t2:after_environment_response'}
    if task == 'T2':
        target['checkpoint']='shared_ending'
    if task == 'T3':
        horizon=delayed_horizon or target.get('delayed_horizon',5)
        if not 5 <= horizon <= 10 or target.get('delayed_horizon',horizon)!=horizon:
            raise ValueError('T3 window differs from author artifact; reauthor the question for the new window')
        target.update(checkpoint='t2',delayed_horizon=horizon, immediate_anchor='next_environment_response')
        if raw['subtype'] == 'action_comparison':
            if target.get('comparison_horizon') not in {'immediate','delayed'}:
                raise ValueError('author must specify the action-comparison horizon')
            target['comparison_actions']=[a['action_id'] for a in public_input['candidate_actions'][:2]]
        else:
            mentioned=set(re.findall(r'action_[1-4]',raw['question']))
            if len(mentioned)!=1:
                raise ValueError('T3 single-action question must identify one candidate action')
            target['action_id']=next(iter(mentioned))
        target['prediction_window']={'baseline':'t2:after_environment_response','immediate':'next_environment_response',
                                     'delayed':{'environment_responses':horizon,'includes_immediate':True}}
    item = {'instance_id': f'SFO-{ordinal*12 + {"T1":0,"T2":4,"T3":8}[task] + index + 1:03d}',
            'benchmark_version': VERSION, 'task': task, 'subtype': raw['subtype'],
            'story_id': source['scenario_id'], 'pair_id': source['trajectory_id'] + ':t2:history_pair' if task == 'T2' else None,
            'modality': 'text', 'input': deepcopy(public_input), 'question': raw['question'],
            'options': raw['options'], 'target_spec': target, 'ground_truth': None,
            'label_status': 'pending_human_annotation',
            'metadata': {'source_trajectory_id': source['trajectory_id']},
            'authoring': {k: deepcopy(raw[k]) for k in ('answer', 'evidence_ids', 'rationale', 'option_errors', 'option_variable_map', 'review_notes')}}
    if 'author_reference' in raw:
        item['authoring']['supplemental_reference'] = deepcopy(raw['author_reference'])
    if 'acceptable_answers' in raw:
        item['authoring']['acceptable_answers'] = list(raw['acceptable_answers'])
    item['authoring'].update(review_status='pending_human_review', construction_source=deepcopy(source),
                             replay_status=replay_status, source_admission={'formal_admitted': False, 'reason': 'development_source_gates_pending'},
                             history_dependence=raw.get('history_dependence', 'required'),
                             nonverbal_history_relation=raw.get('nonverbal_history_relation', 'context_dependent'))
    # Rotate correct positions deterministically; rotate all diagnostics with the options.
    old = list(item['options'])
    desired = (ordinal + index + {'T1':0,'T2':1,'T3':2}[task]) % len(old)
    if raw['subtype'] == 'current_intensity':
        desired = [0,1,2,4,5][ordinal % 5]  # Five six-choice items include both E and F.
    offset = (desired - old.index(item['authoring']['answer'])) % len(old)
    mapping = {letter: old[(i+offset) % len(old)] for i, letter in enumerate(old)}
    for container, field in [(item, 'options'), (item['authoring'], 'option_errors'), (item['authoring'], 'option_variable_map')]:
        container[field] = dict(sorted((mapping[k], v) for k, v in container[field].items()))
    item['authoring']['answer'] = mapping[item['authoring']['answer']]
    if 'acceptable_answers' in item['authoring']:
        item['authoring']['acceptable_answers'] = [mapping[a] for a in item['authoring']['acceptable_answers']]
    validate_item(item)
    assert_no_leaks(public_instance(item))
    return item


def freeze_authoring_source(items, path):
    path=Path(path)
    reference={'path':str(path),'sha256':sha(path),
               'kind':'assistant_curated_not_human' if '.curated.' in path.name else 'provider_generated_not_human'}
    for item in items:
        item['authoring']['answer_construction']=deepcopy(reference)
        if '.curated.' in path.name:
            item['authoring']['editorial_review']={'reviewer_type':'assistant_not_human','source':str(path)}
    return items


def write_bundle(items, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for item in items:
        validate_item(item)
    for name, values in [('items.jsonl', items), ('public.jsonl', [public_instance(x) for x in items])]:
        (output/name).write_text(''.join(json.dumps(v, ensure_ascii=False)+'\n' for v in values), encoding='utf-8')
    ready=[i for i in items if i['task']=='T1' or i['authoring']['replay_status']=='validated']
    (output/'replay_ready.items.jsonl').write_text(''.join(json.dumps(i,ensure_ascii=False)+'\n' for i in ready),encoding='utf-8')
    coverage = Counter((i['task'], FAMILIES[f]) for i in items for f in {p.split('.')[0] for p in i['target_spec']['target_state_ids']})
    manifest = {'format': VERSION, 'item_count': len(items), 'tasks': dict(Counter(x['task'] for x in items)),
                'subtypes': dict(Counter(x['task']+'/'+x['subtype'] for x in items)),
                'task_state_coverage': {'/'.join(k):v for k,v in sorted(coverage.items())},
                'answer_positions': dict(Counter(x['authoring']['answer'] for x in items)),
                'scenario_count': len({x['story_id'] for x in items}), 'formal_admission': False,
                'human_review': 'pending', 'replay_ready_count':len(ready),
                'replay_ready_tasks':dict(Counter(i['task'] for i in ready)),
                'replay_pending_ids':[i['instance_id'] for i in items if i not in ready], 'items_sha256': sha(output/'items.jsonl'), 'public_sha256': sha(output/'public.jsonl')}
    save(output/'manifest.json', manifest)
    lines = ['# SocialFlux offline T1–T3 开发题（完整题面与作者参考答案）', '',
             '所有答案是待人工审核的开发参考，不是已冻结真值。下面每题先给出完整可见材料，再给出作者侧标注。',
             '主评测只答 `{"answer":"B"}`。证据诊断另加 `evidence_ids`，分别计分。', '']
    for x in items:
        a=x['authoring']; lines += [f"## {x['instance_id']} · {x['task']} / {x['subtype']}", '',
            f"来源：{x['story_id']}；轨迹：{x['metadata']['source_trajectory_id']}；状态持有者：{x['input']['target_character']['name']} → {x['input']['role']['name']}。", '']
        inp=x['input']; lines += ['背景：'+inp['context']['background'], '角色目标：'+inp['role'].get('explicit_goal',''), '']
        situation=inp['context'].get('public_situation', {})
        for key,value in situation.items():
            lines += [f"{key}：" + ('；'.join(value) if isinstance(value,list) else str(value)), '']
        for key in ('history','history_a','history_b'):
            if key in inp:
                lines += [key+'：', '']
                for t in inp[key]:
                    lines += [f"- [{t['turn_id']}] {inp['role']['name']}：{t['evaluated_agent']}",
                              f"  {inp['target_character']['name']}：{t['environment_character']}"]
                    if t.get('observable_expression'):
                        lines += ['  可见表达：'+json.dumps(t['observable_expression'],ensure_ascii=False)]
                    if t.get('public_events'):
                        lines += ['  公开事件：'+json.dumps(t['public_events'],ensure_ascii=False)]
                lines += ['']
        if inp.get('shared_ending'):
            lines += ['共同 ending（两侧完全相同）：'+json.dumps(inp['shared_ending'],ensure_ascii=False), '']
        for action in inp.get('candidate_actions',[]):
            lines += [f"- 候选行动 {action['action_id']}：{action['text']}"]
        lines += ['', '**题目：'+x['question']+'**', '']
        lines += [f"- **{k}.** {v}" for k,v in x['options'].items()]
        lines += ['', f"**作者参考答案：{a['answer']}（待审）**", '', a['rationale'], '',
                  '证据：'+', '.join(a['evidence_ids']), '变量／时间：'+json.dumps(x['target_spec'],ensure_ascii=False),
                  '错项类型：'+json.dumps(a['option_errors'],ensure_ascii=False),
                  '分维映射：'+json.dumps(a['option_variable_map'],ensure_ascii=False),
                  '可接受答案：'+', '.join(a.get('acceptable_answers',[a['answer']])),
                  '审核备注：'+str(a['review_notes']), '分支验证：'+a['replay_status'], '']
    (output/'examples.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return manifest
