"""Author-side v2 contract; shared capabilities are not state variables or outputs."""
from copy import deepcopy

CAPABILITIES = {
    'situational_evidence_integration': '情境证据整合',
    'multidimensional_state_distinction': '多维状态区分',
    'temporal_dynamics_reasoning': '跨时动态推理',
}
SUBTYPES_V2 = {
    'T1': {'current_state', 'interval_change', 'evidence_support', 'state_combination'},
    'T2': {'history_comparison', 'expression_meaning', 'joint_comparison', 'history_evidence'},
    'T3': {'action_selection', 'consequence_explanation'},
}

# Declarative requests, usable by an authoring provider or a human author.
TEMPLATES = {
    'T1/current_state': '截至{checkpoint}，{owner}目前对{object}的{state}，哪项判断最符合材料？',
    'T1/interval_change': '相较{start}，在{checkpoint}时{owner}对{object}的{state}如何变化？',
    'T1/evidence_support': '哪项已发生的证据最能支持或限制{owner}在{checkpoint}的{judgment}？',
    'T1/state_combination': '截至{checkpoint}，哪组{states}判断最符合{owner}的当前状态？',
    'T2/history_comparison': '在共同表达时，哪段历史更支持{owner}对{object}的{state}判断？',
    'T2/expression_meaning': '结合两段历史，{owner}相同的{expression}分别具有怎样的含义？',
    'T2/joint_comparison': '在共同表达时，哪组{states}比较最符合两段历史？',
    'T2/history_evidence': '综合两段历史的{earlier_event}与{repair_event}，哪项关于{state}的判断最有依据？',
    'T3/action_selection': '从{checkpoint}出发，为了{goal}，哪个行动更可能在{horizon}产生该结果？',
    'T3/consequence_explanation': '相对于{comparison}，关于{actions}在{horizon}对{states}的影响，哪组判断最有依据？',
}


def generation_request(task, subtype, public_input, *, primary_capability, difficulty='ordinary', author_context=None):
    """Only for authors. Never pass this payload to the evaluated model."""
    if subtype not in SUBTYPES_V2[task] or primary_capability not in CAPABILITIES:
        raise ValueError('unknown task form or capability')
    if difficulty not in {'ordinary', 'hard'}:
        raise ValueError('invalid design difficulty')
    return {'benchmark_version': 'socialflux_offline_choice_v2', 'task': task, 'subtype': subtype,
            'template': TEMPLATES[task + '/' + subtype], 'public_input': deepcopy(public_input),
            'primary_capability': primary_capability, 'design_difficulty': difficulty,
            'author_context': deepcopy(author_context or {}),
            'schema_path': 'schemas/offline_choice_item_v2.schema.json',
            'answer_format': {'answer': 'B'}}


def validate_design(item):
    from tasks.offline_choice import visible_evidence
    a, spec, inp, author = item['analysis'], item['target_spec'], item['input'], item['authoring']
    if a['primary_capability'] not in CAPABILITIES:
        raise ValueError('invalid primary capability')
    aux = a['auxiliary_capabilities']
    if not isinstance(aux, list) or len(set(aux)) != len(aux) or not set(aux) <= CAPABILITIES.keys() or a['primary_capability'] in aux:
        raise ValueError('invalid auxiliary capabilities')
    if a['design_difficulty'] not in {'ordinary', 'hard'}:
        raise ValueError('invalid design difficulty')
    if a['design_difficulty'] == 'hard' and not a.get('difficulty_reason', '').strip():
        raise ValueError('Hard requires a specific difficulty reason')
    measured = a['empirical_difficulty']
    if measured is not None and (not isinstance(measured, dict) or not {'run_id', 'sample_size', 'accuracy'} <= measured.keys()
                                 or measured['sample_size'] < 1 or not 0 <= measured['accuracy'] <= 1):
        raise ValueError('empirical difficulty needs actual run provenance')
    bindings = a['state_bindings']
    if len(bindings) != len(spec['target_state_ids']) or {b['state_id'] for b in bindings} != set(spec['target_state_ids']):
        raise ValueError('state bindings must cover each target variable')
    for b in bindings:
        if b['owner'] != spec['state_owner'] or b['object'] != spec['state_target']:
            raise ValueError('state binding direction mismatch')
        if b['state_id'].startswith('consequence_risk.') and (not b.get('risk_event') or not b.get('risk_window')):
            raise ValueError('risk binding needs event and event window')
    if not isinstance(author.get('counterevidence_ids'), list) or not set(author['counterevidence_ids']) <= visible_evidence(item):
        raise ValueError('counterevidence must reference observable materials')
    if not author.get('rationale') or not author.get('generation_source'):
        raise ValueError('missing rationale or generation provenance')
    if author.get('review_protocol') != ('human_annotation' if item['task'] == 'T3' else 'human_verification'):
        raise ValueError('wrong human review protocol')
    if len(author.get('acceptable_answers', [author['answer']])) != 1:
        raise ValueError('v2 examples require a discriminable single best answer; reauthor ambiguous choices')
    # Historical public-only drafts retain their original schema for audit.
    # The omniscient release tightens the distinction between a single-state
    # history comparison and a genuine combination of two state dimensions.
    if author.get('oracle_reference') and item['subtype'] in {'state_combination', 'joint_comparison'} and len(spec['target_state_ids']) != 2:
        raise ValueError('omniscient combination questions require exactly two recorded state variables')
    if author.get('oracle_reference') and item['task'] == 'T3' and spec.get('horizon') == 'immediate':
        if any(':step' in evidence for evidence in author['oracle_reference'].get('evidence_ids', [])):
            raise ValueError('immediate oracle reference cannot cite later branch steps')
    if item['task'] == 'T1':
        if 'candidate_actions' in inp or 'history_a' in inp:
            raise ValueError('T1 only observes completed history')
        ids = {t['turn_id'] for t in inp['history']}
        if spec['checkpoint'] not in ids or inp['history'][-1]['turn_id'] != spec['checkpoint']:
            raise ValueError('T1 visible history must end at checkpoint')
        if item['subtype'] == 'interval_change':
            interval = spec.get('comparison_interval', {})
            endpoints = [interval.get(k, '').split(':')[0] for k in ('start', 'end')]
            order = [t['turn_id'] for t in inp['history']]
            if not set(endpoints) <= ids or order.index(endpoints[0]) >= order.index(endpoints[1]) or endpoints[1] != spec['checkpoint']:
                raise ValueError('T1 change needs ordered visible start and end')
    if item['task'] == 'T2':
        if 'history' in inp or 'candidate_actions' in inp:
            raise ValueError('T2 needs only the two histories and one common expression')
        control = author['history_control']
        if not control.get('factor') or control.get('shared_external_conditions') is not True:
            raise ValueError('T2 needs a controlled historical factor')
        if control.get('shared_expression') != 'single_shared_ending':
            raise ValueError('T2 expression must be stored only once')
        # Every difference is recoverable, with unchanged context/roles kept in one object.
        actual = []
        for left, right in zip(inp['history_a'], inp['history_b']):
            for key in sorted((left.keys() | right.keys()) - {'turn_id'}):
                if left.get(key) != right.get(key):
                    actual.append({'a_id': left['turn_id'], 'b_id': right['turn_id'], 'field': key,
                                   'before': left.get(key), 'after': right.get(key)})
        if actual != control.get('edits') or not actual:
            raise ValueError('T2 edit log does not match original and edited histories')
        if not control.get('state_check', {}).get('status'):
            raise ValueError('T2 state check must be recorded, including pending status')
    if item['task'] == 'T3':
        actions = inp['candidate_actions']
        ids = [x['action_id'] for x in actions]
        if ids != [f'action_{i+1}' for i in range(len(actions))] or any(x.get('label') != f'行动 {i+1}' for i, x in enumerate(actions)):
            raise ValueError('candidate actions use numbered labels, answers use letters')
        if len({x['text'] for x in actions}) != len(actions):
            raise ValueError('duplicate candidate actions')
        if inp['history'][-1]['turn_id'] != spec['checkpoint']:
            raise ValueError('T3 input must stop at the common decision checkpoint')
        comparison = spec['comparison']
        if comparison['kind'] not in {'pre_action', 'between_actions'} or not set(comparison['action_ids']) <= set(ids) or not comparison['action_ids']:
            raise ValueError('invalid comparison reference')
        if len(set(comparison['action_ids'])) != len(comparison['action_ids']) or (comparison['kind'] == 'between_actions' and len(comparison['action_ids']) < 2):
            raise ValueError('comparison needs distinct actions')
        if spec['horizon'] not in {'immediate', 'delayed', 'immediate_delayed'}:
            raise ValueError('invalid consequence horizon')
        delayed = spec['horizon'] != 'immediate'
        if delayed and not 5 <= spec.get('delayed_horizon', 0) <= 10:
            raise ValueError('delayed questions need a 5–10 response window')
        if item['subtype'] == 'action_selection' and not spec.get('goal'):
            raise ValueError('action selection needs an explicit goal')
        branches = author['branch_evidence']
        if branches['status'] not in {'validated', 'needs_branch_evidence'} or not branches.get('common_initial_context') or not branches.get('shared_external_conditions'):
            raise ValueError('branch evidence needs common origin and external controls')
        if branches['status'] == 'validated':
            needed = spec['delayed_horizon'] if delayed else 1
            if branches['observed_responses'] < needed or author['replay_status'] != 'validated':
                raise ValueError('observed branch window too short for this question')
        elif author['replay_status'] == 'validated':
            raise ValueError('pending branch evidence cannot be validated')
    return item


def author_item(provider, request):
    """Generate one v2 proposal; caller supplies frozen sources and review context.

    This is opt-in. Legacy batch recipes remain fixed for reproducibility.
    """
    import json
    from pathlib import Path
    from prompts.loader import render_prompt
    from providers.structured import complete_json
    from tasks.offline_choice import validate_item
    payload = deepcopy(request)
    payload['schema'] = json.loads((Path(__file__).resolve().parents[1] / 'schemas/offline_choice_item_v2.schema.json').read_text())
    frozen = request.get('author_context', {})
    required_source_fields = ['construction_source', 'replay_status']
    if request['task'] == 'T2':
        required_source_fields.append('history_control')
    if request['task'] == 'T3':
        required_source_fields.append('branch_evidence')
    if any(key not in frozen for key in required_source_fields):
        raise ValueError('caller must supply frozen construction and replay provenance')
    def validate_proposal(item):
        if item.get('ground_truth') is not None or item.get('authoring', {}).get('review_status') != 'pending_human_review':
            raise ValueError('generation may not mint human truth')
        if item['task'] != request['task'] or item['subtype'] != request['subtype'] or item['input'] != request['public_input']:
            raise ValueError('author changed the frozen task or observable input')
        if item['analysis']['primary_capability'] != request['primary_capability'] or item['analysis']['design_difficulty'] != request['design_difficulty']:
            raise ValueError('author changed the requested capability or difficulty')
        if any(item['authoring'].get(key) != frozen[key] for key in required_source_fields):
            raise ValueError('author changed frozen construction or replay provenance')
        if item['authoring'].get('source_admission', {}).get('formal_admitted'):
            raise ValueError('author cannot approve source admission')
        return validate_item(item)
    return complete_json(provider, [{'role':'user','content':render_prompt('offline_choice_author_v2',payload)}],
                         {'temperature':0.2}, validate_proposal, context='offline choice v2 author', max_attempts=2)


def grouped_record(item):
    """Portable three-group export; only evaluated_input is sent to a model."""
    from tasks.offline_choice import public_instance
    return {
        'evaluated_input': public_instance(item),
        'annotation': {'ground_truth': deepcopy(item['ground_truth']), **deepcopy(item['authoring'])},
        'analysis': {**deepcopy(item['analysis']), 'task': item['task'], 'question_form': item['subtype'],
                     'benchmark_version': item['benchmark_version'], 'target_spec': deepcopy(item['target_spec']),
                     'modality': item['modality'], 'story_id': item['story_id'], 'history_pair_id': item['pair_id'],
                     'modality_pair_id': item['metadata'].get('modality_pair_id'),
                     'branch_ids': deepcopy(item['authoring'].get('branch_evidence', {}).get('branch_ids', [])),
                     'source': deepcopy(item['metadata'])},
    }
