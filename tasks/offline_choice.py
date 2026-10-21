"""One-answer offline protocol; author labels never enter evaluated messages."""
from copy import deepcopy
import json
import re

from environment.state_ontology import STATE_VARIABLE_ONTOLOGY
from prompts.loader import render_prompt

VERSION = 'socialflux_offline_choice_v1'
VERSION_V2 = 'socialflux_offline_choice_v2'
VERSIONS = {VERSION, VERSION_V2}
FAMILIES = {'emotion': 'Emotion', 'behavioral_disposition': 'Behavioral Disposition',
            'relationship': 'Relationship', 'consequence_risk': 'Interaction Risk'}
SUBTYPES = {'T1': {'current_intensity', 'interval_change', 'joint_change'},
            'T2': {'history_comparison', 'expression_meaning', 'joint_comparison'},
            'T3': {'immediate_effect', 'delayed_effect', 'action_comparison', 'immediate_delayed'}}
ERROR_TYPES = {'actor_reversal', 'expression_as_state', 'state_dimension_confusion',
               'history_ignored', 'promise_as_fulfillment', 'immediate_delayed_confusion',
               'goal_constraint_ignored', 'unsupported_inference'}
INPUT_KEYS = {'context', 'role', 'target_character', 'history', 'history_a', 'history_b',
              'shared_ending', 'candidate_actions'}


def visible_evidence(item):
    result = {'context'}
    for key in ('history', 'history_a', 'history_b'):
        result.update(t['turn_id'] for t in item['input'].get(key, []))
    if item['input'].get('shared_ending'):
        result.add(item['input']['shared_ending']['turn_id'])
    result.update(a['action_id'] for a in item['input'].get('candidate_actions', []))
    return result


def public_instance(item):
    """Allowlist, rather than removing a growing list of author-side fields."""
    from evaluation.leakage import assert_no_leaks
    result = {'instance_id': item['instance_id'], 'modality': item['modality'],
              'input': {k: deepcopy(v) for k, v in item['input'].items() if k in INPUT_KEYS},
              'question': item['question'], 'options': deepcopy(item['options'])}
    assert_no_leaks(result)
    def reject_private(value):
        if isinstance(value, dict):
            if set(value) & {'persona', 'initial_state', 'oracle_state', 'future_turns', 'authoring', 'ground_truth', 'target_spec', 'analysis', 'primary_capability', 'difficulty_reason', 'branch_evidence'}:
                raise ValueError('private field in evaluated input')
            for child in value.values():
                reject_private(child)
        elif isinstance(value, list):
            for child in value:
                reject_private(child)
    reject_private(result)
    return result


def answer_prompt(instance, diagnostic=False):
    return render_prompt('offline_choice_answer_v1', public_instance(instance),
                         evidence_instruction=('额外输出 evidence_ids 字符串数组，引用材料中的定位 ID；答案与证据分别计分。'
                                               if diagnostic else '只输出 answer，不要求解释或证据。'))


def parse_answer(raw, options, diagnostic=False):
    """Strict unique choice; no regex fishing in prose or semantic repair retries."""
    result = {'answer': None, 'format_error': None, 'evidence_ids': None,
              'evidence_format_error': None}
    if not isinstance(raw, str):
        return {**result, 'format_error': 'not_text'}
    raw = raw.strip()
    if re.fullmatch('[A-Fa-f]', raw):
        value = {'answer': raw.upper()}
    else:
        try:
            def unique(pairs):
                obj = {}
                for k, v in pairs:
                    if k in obj:
                        raise ValueError('duplicate key')
                    obj[k] = v
                return obj
            value = json.loads(raw, object_pairs_hook=unique)
        except (ValueError, TypeError):
            return {**result, 'format_error': 'not_single_letter_or_json'}
    if not isinstance(value, dict):
        return {**result, 'format_error': 'missing_answer'}
    if diagnostic:
        ids = value.get('evidence_ids')
        if (not isinstance(ids, list) or any(not isinstance(x, str) for x in ids)
                or len(ids) != len(set(ids))):
            result['evidence_format_error'] = 'missing_or_invalid_evidence_ids'
        else:
            result['evidence_ids'] = ids
    if 'answer' not in value:
        return {**result, 'format_error': 'missing_answer'}
    if set(value) - ({'answer', 'evidence_ids'} if diagnostic else {'answer'}):
        result['format_error'] = 'unexpected_fields'
    answer = value['answer']
    if isinstance(answer, str):
        answer = answer.strip().upper()
    if not isinstance(answer, str) or answer not in options:
        return {**result, 'format_error': 'invalid_option'}
    result['answer'] = answer
    return result


def validate_answer(value, instance):
    """Validate a decoded answer through the same parser used for API output."""
    parsed = parse_answer(json.dumps(value), instance["options"])
    if parsed["format_error"]:
        raise ValueError(parsed["format_error"])
    return {"answer": parsed["answer"]}


def validate_item(item, formal=False):
    if item.get('benchmark_version') not in VERSIONS:
        raise ValueError('unknown offline protocol version')
    task = item['task']
    v2 = item.get('benchmark_version') == VERSION_V2
    from tasks.offline_design import SUBTYPES_V2, validate_design
    if task not in SUBTYPES or item['subtype'] not in (SUBTYPES_V2 if v2 else SUBTYPES)[task]:
        raise ValueError('task/subtype mismatch')
    options = item['options']
    if not 3 <= len(options) <= 6 or list(options) != list('ABCDEF'[:len(options)]):
        raise ValueError('options must be 3–6 consecutive letters')
    expected_count = (6 if item['subtype'] == 'current_intensity' else 4 if item['subtype'] in {'expression_meaning','joint_change','joint_comparison','immediate_delayed'} else None)
    if v2:
        expected_count = None if item['subtype'] in {'interval_change', 'history_comparison'} else 4
    if (expected_count is not None and len(options) != expected_count) or (expected_count is None and len(options) not in {3,4}):
        raise ValueError('option count does not match subtype')
    if len(set(options.values())) != len(options) or any(not str(x).strip() for x in options.values()):
        raise ValueError('empty or duplicate options')
    spec, author = item['target_spec'], item['authoring']
    variables = spec['target_state_ids']
    if not variables or len(set(variables)) != len(variables) or not set(variables) <= STATE_VARIABLE_ONTOLOGY.keys():
        raise ValueError('invalid canonical state paths')
    if not spec.get('state_owner') or not spec.get('state_target') or not spec.get('time_scope'):
        raise ValueError('missing owner, target or time scope')
    if any(p.startswith('consequence_risk.') for p in variables) and not spec.get('risk_event'):
        raise ValueError('risk needs a named event and time scope')
    if spec['state_owner'] != item['input']['target_character']['character_id'] or spec['state_target'] != item['input']['role']['character_id']:
        raise ValueError('state owner/target does not match public roles')
    if author['answer'] not in options:
        raise ValueError('answer outside options')
    accepted = author.get('acceptable_answers', [author['answer']])
    if not accepted or not set(accepted) <= options.keys() or author['answer'] not in accepted:
        raise ValueError('invalid acceptable answers')
    if set(author['option_errors']) != set(options) - set(accepted):
        raise ValueError('each distractor needs one primary error')
    if not set(author['option_errors'].values()) <= ERROR_TYPES:
        raise ValueError('unknown error type')
    if (not author['evidence_ids'] or len(author['evidence_ids']) != len(set(author['evidence_ids']))
            or not set(author['evidence_ids']) <= visible_evidence(item)):
        raise ValueError('answer cites invisible evidence')
    if set(item['input']) - INPUT_KEYS:
        raise ValueError('unexpected public input field')
    if task == 'T2':
        if not item.get('pair_id') or not item['input'].get('shared_ending'):
            raise ValueError('T2 requires pair and one shared ending')
        a, b = item['input']['history_a'], item['input']['history_b']
        if not a or len(a) != len(b) or a == b:
            raise ValueError('invalid controlled histories')
        if not v2 and any({k:v for k,v in left.items() if k!='turn_id'} != {k:v for k,v in right.items() if k!='turn_id'} for left,right in zip(a[:-1],b[:-1])):
            raise ValueError('controlled T2 shared prefix changed')
        evidence = author['evidence_ids']
        if not any(x.startswith('A:') for x in evidence) or not any(x.startswith('B:') for x in evidence):
            raise ValueError('T2 needs both histories')
        if item['subtype'] == 'expression_meaning' and item['input']['shared_ending']['turn_id'] not in evidence:
            raise ValueError('expression explanation must cite shared ending')
    if task == 'T3':
        actions = item['input']['candidate_actions']
        if not 2 <= len(actions) <= 4 or len({a['action_id'] for a in actions}) != len(actions):
            raise ValueError('T3 requires 2–4 distinct actions')
        if not v2 and not 5 <= spec['delayed_horizon'] <= 10:
            raise ValueError('invalid delayed horizon')
        action_ids={a['action_id'] for a in actions}
        if v2:
            pass  # v2 validates explicit action/baseline comparisons below.
        elif item['subtype'] == 'action_comparison':
            if spec.get('comparison_horizon') not in {None,'immediate','delayed'}:
                raise ValueError('comparison needs an explicit immediate or delayed horizon')
            compared=spec.get('comparison_actions',[])
            if len(compared)!=2 or len(set(compared))!=2 or not set(compared)<=action_ids:
                raise ValueError('comparison needs two named candidate actions')
        elif spec.get('action_id') not in action_ids:
            raise ValueError('effect needs a named candidate action')
        if spec.get('immediate_anchor') != 'next_environment_response':
            raise ValueError('invalid immediate anchor')
    maps = author.get('option_variable_map', {})
    if set(maps) != set(options) or any(not isinstance(v, dict) or not v for v in maps.values()):
        raise ValueError('every option requires variable judgments')
    coordinates = set(maps[author['answer']])
    if any(set(v) != coordinates for v in maps.values()):
        raise ValueError('option variable coordinates differ')
    if {p.split('@')[0] for p in coordinates} != set(variables):
        raise ValueError('option variable map differs from target states')
    if item['subtype'] == 'current_intensity':
        from tasks.T1.t1_probability_utils import INTENSITY_LABELS
        if len(variables) != 1 or len(options) != len(INTENSITY_LABELS) or {next(iter(m.values())) for m in maps.values()} != set(INTENSITY_LABELS):
            raise ValueError('intensity must preserve the existing five levels plus insufficient evidence')
    if item.get('ground_truth') is not None and author['review_status'] != 'human_approved':
        raise ValueError('unreviewed machine proposal cannot become ground truth')
    if formal:
        if item.get('ground_truth') is None or author['review_status'] != 'human_approved':
            raise ValueError('formal scoring requires human ground truth')
        if set(item['ground_truth']['acceptable_answers']) != set(accepted):
            raise ValueError('human label and reviewed option annotations disagree')
        if not author.get('source_admission', {}).get('formal_admitted'):
            raise ValueError('formal source gates incomplete')
        if item['modality'] == 'text+video' and author.get('media_human_review') != 'approved':
            raise ValueError('formal video review pending')
        if task in {'T2', 'T3'} and author.get('replay_status') != 'validated':
            raise ValueError('formal controlled replay not validated')
    if v2:
        validate_design(item)
    public_instance(item)
    return item


def generate_answer(provider, instance, seed, *, diagnostic=False, **unused):
    if instance['modality'] == 'text+video':
        raise ValueError('video answering requires offline-eval with an explicit media manifest and transport')
    raw = provider.complete([{'role': 'user', 'content': answer_prompt(instance, diagnostic)}],
                            temperature=0, seed=seed)
    return parse_answer(raw, instance['options'], diagnostic), 1
