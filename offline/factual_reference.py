"""Reuse an observed continuation only when its external conditions are fixed."""
from copy import deepcopy
import hashlib
import json


POLICY_CONTRACT = ('model','prompt_id','sampling','validation_profile',
                   'minimum_natural_turns','observation_condition','media_input_format')


def factual_reference(trajectory, horizon, source):
    turns = trajectory.get('turns', [])
    if len(turns) < 2+horizon:
        return None
    future = turns[2:2+horizon]
    snapshot = future[0]['environment_snapshot_before']
    plan_hash = snapshot.get('event_plan', {}).get('plan_hash')
    if not plan_hash and (snapshot.get('longitudinal_enabled')
                          or snapshot.get('event_plan',{}).get('selection') not in (None,'none')
                          or snapshot.get('event_plan',{}).get('selected_outcomes')):
        return None
    previous_state, previous_dynamics = snapshot['state'], snapshot['dynamics']
    for turn in future:
        before = turn['environment_snapshot_before']
        if (turn.get('segment_transition_after')
                or before.get('event_plan', {}) != snapshot.get('event_plan', {})
                or before.get('longitudinal_enabled') != snapshot.get('longitudinal_enabled')
                or before.get('public_timeline') != snapshot.get('public_timeline')
                or before.get('segment_index') != snapshot.get('segment_index')
                or turn['state_before'] != previous_state
                or turn['dynamics_before'] != previous_dynamics):
            return None
        previous_state = turn.get('state_after_public_events', turn['state_after'])
        previous_dynamics = turn.get('dynamics_after_public_events', turn['dynamics_after'])
    first, last = future[0], future[-1]
    return {
        'experiment':'existing_factual_continuation',
        'snapshot_sha256':hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
        'checkpoint_turn_id':first['turn_id'],
        'candidate_action':{'text':first['policy_action']['text']},
        'state_before':deepcopy(snapshot['state']),
        'dynamics_before':deepcopy(snapshot['dynamics']),
        'state_after_immediate':deepcopy(first.get('state_after_public_events',first['state_after'])),
        'state_after_immediate_action_response':deepcopy(first['state_after']),
        'dynamics_after_immediate':deepcopy(first.get('dynamics_after_public_events',first['dynamics_after'])),
        'dynamics_after_immediate_action_response':deepcopy(first['dynamics_after']),
        'state_after_delayed':deepcopy(previous_state),
        'dynamics_after_delayed':deepcopy(previous_dynamics),
        'future_turns':deepcopy(future), 'window_complete':True,
        'delayed_horizon':horizon, 'actual_turns_observed':horizon,
        'continuation_protocol':'free_form_same_model_policy',
        'continuation_policy_provenance':deepcopy(trajectory['policy_provenance']),
        'elapsed_time_start':snapshot.get('elapsed_time',0),
        'elapsed_time_end':last.get('elapsed_time_after',snapshot.get('elapsed_time',0)),
        'elapsed_time_delta':last.get('elapsed_time_after',0)-snapshot.get('elapsed_time',0),
        'crossed_event_nodes':[], 'external_event_plan_hash':plan_hash,
        'counterfactual_timeline_control':'observed_window_verified_no_external_event_or_segment_change',
        'source_reuse':{k:source[k] for k in ['trajectory_path','trajectory_sha256']},
    }


def assert_same_policy(reference, policy):
    actual = reference['continuation_policy_provenance']
    expected = policy.provenance
    differences = [key for key in POLICY_CONTRACT if actual.get(key) != expected.get(key)]
    if differences:
        raise ValueError('factual continuation policy differs: '+', '.join(differences))
