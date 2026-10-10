"""Local counterfactual branches restored from real free-form checkpoints."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json


def branch_counterfactuals(
    environment_factory,
    checkpoint_turn,
    candidate_actions,
    continuation_policy_factory,
    delayed_horizon=5,
    audit_callback=None,
    branch_workers=1,
    resume_logs=None,
    completed_branches=None,
    branch_callback=None,
):
    if not 5 <= delayed_horizon <= 10:
        raise ValueError("delayed_horizon must be between 5 and 10")
    if not 2 <= len(candidate_actions) <= 4:
        raise ValueError("counterfactuals require 2–4 actions")
    snapshot = checkpoint_turn.get("environment_snapshot_before")
    if not snapshot:
        raise ValueError("checkpoint lacks a private environment snapshot")
    if branch_workers < 1:
        raise ValueError("branch_workers must be positive")
    resume_logs = resume_logs or {}
    completed_branches = completed_branches or {}
    snapshot_hash = hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    for index, branch in completed_branches.items():
        if (index not in range(len(candidate_actions))
                or branch['candidate_action']['text'] != candidate_actions[index]['text']
                or branch['snapshot_sha256'] != snapshot_hash
                or branch['external_event_plan_hash'] != snapshot.get('event_plan',{}).get('plan_hash')
                or branch['delayed_horizon'] != delayed_horizon
                or not branch['window_complete']
                or branch['actual_turns_observed'] != delayed_horizon
                or len(branch['future_turns']) != delayed_horizon):
            raise ValueError('completed branch does not match snapshot/action/window')
        future=branch['future_turns']
        if (future[0]['policy_action']['text']!=candidate_actions[index]['text']
                or future[0]['state_before']!=snapshot['state']
                or future[0]['state_after']!=branch['state_after_immediate_action_response']
                or future[-1].get('state_after_public_events',future[-1]['state_after'])!=branch['state_after_delayed']):
            raise ValueError('completed branch evidence and summary differ')
        for previous,current in zip(future,future[1:]):
            if current['state_before']!=previous.get('state_after_public_events',previous['state_after']):
                raise ValueError('completed branch state chain is discontinuous')
    checkpoint_elapsed = snapshot.get("elapsed_time", 0)
    checkpoint_timeline_count = len(snapshot.get("public_timeline", []))
    frozen_event_plan_hash = snapshot.get("event_plan", {}).get("plan_hash")
    for branch_index,candidate in enumerate(candidate_actions):
        prior = resume_logs.get(branch_index, [])
        if prior:
            expected_snapshot = deepcopy(snapshot)
            expected_snapshot['counterfactual_timeline_lock'] = True
            if (len(prior) > delayed_horizon
                    or prior[0]['policy_action'] != candidate
                    or prior[0]['environment_snapshot_before'] != expected_snapshot):
                raise ValueError('resume progress does not match original snapshot/action')
            for previous, current in zip(prior, prior[1:]):
                if (current['state_before'] != previous.get('state_after_public_events', previous['state_after'])
                        or current['dynamics_before'] != previous.get('dynamics_after_public_events',previous['dynamics_after'])):
                    raise ValueError('resume progress state chain is discontinuous')
            after = prior[-1].get('environment_snapshot_after')
            if after and (after['state'] != prior[-1].get('state_after_public_events', prior[-1]['state_after'])
                          or after['dynamics'] != prior[-1].get('dynamics_after_public_events', prior[-1]['dynamics_after'])
                          or after.get('event_plan') != snapshot.get('event_plan')
                          or not after.get('counterfactual_timeline_lock')):
                raise ValueError('resume after-snapshot differs from recorded transition')

    def run_branch(indexed_candidate):
        branch_index, candidate = indexed_candidate
        if branch_index in completed_branches:
            return deepcopy(completed_branches[branch_index])
        environment = environment_factory()
        policy = continuation_policy_factory()
        last_error = None
        prior = deepcopy(resume_logs.get(branch_index, []))
        def record_step(attempt, step, log):
            # Persist an actual full runtime snapshot, never reconstruct one
            # from state values. Older checkpoints retain the replay fallback.
            if callable(getattr(environment, 'snapshot', None)):
                log['environment_snapshot_after'] = environment.snapshot()
            if audit_callback:
                audit_callback(branch_index, attempt, step, deepcopy(log))
        # Each response already performs up to 4 distinct-text attempts.
        # Two snapshot replays are enough before trying the next checkpoint.
        for branch_attempt in range(2):
            # Replay the last logged step, whose before-snapshot is complete;
            # no inferred state is ever used to resume an environment.
            after = prior[-1].get('environment_snapshot_after') if branch_attempt == 0 and prior else None
            prefix = (prior if after else prior[:-1]) if branch_attempt == 0 and prior else []
            replay_snapshot = after or (prior[-1]['environment_snapshot_before'] if branch_attempt == 0 and prior else snapshot)
            environment.restore(
                replay_snapshot,
                episode_id=f"local-branch-{branch_index}-attempt-{branch_attempt}",
            )
            environment.session['turns'] = deepcopy(prefix)
            environment.session["counterfactual_timeline_lock"] = True
            state_before = deepcopy(snapshot["state"])
            dynamics_before = deepcopy(snapshot["dynamics"])
            try:
                if prefix:
                    immediate_log = prefix[0]
                    state_after_immediate = deepcopy(immediate_log.get('state_after_public_events',immediate_log['state_after']))
                    dynamics_after_immediate = deepcopy(immediate_log.get('dynamics_after_public_events',immediate_log['dynamics_after']))
                    if after:
                        continuation_steps = len(prefix) - 1
                    else:
                        _, replayed_log = environment.step(deepcopy(prior[-1]['policy_action']))
                        record_step(branch_attempt, len(prefix)+1, replayed_log)
                        continuation_steps = len(prefix)
                else:
                    _, immediate_log = environment.step(deepcopy(candidate))
                    record_step(branch_attempt, 1, immediate_log)
                    state_after_immediate = deepcopy(environment.session["state"])
                    dynamics_after_immediate = deepcopy(environment.session["dynamics"])
                    continuation_steps = 0
                while (
                    continuation_steps < delayed_horizon - 1
                    and environment.session["status"] == "active"
                ):
                    _, continuation_log = environment.step(policy.generate(environment.observe()))
                    continuation_steps += 1
                    record_step(branch_attempt, 1 + continuation_steps, continuation_log)
                break
            except ValueError as exc:
                last_error = exc
        else:
            raise RuntimeError(
                f"counterfactual branch {branch_index} exhausted retries"
            ) from last_error
        result = {
            "resumed_prefix_turns": len(prefix),
            "experiment": "local_action_intervention",
            "snapshot_sha256": hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "future_turns": deepcopy(environment.session["turns"]),
            "window_complete": 1 + continuation_steps == delayed_horizon,
            "checkpoint_turn_id": checkpoint_turn["turn_id"],
            "candidate_action": deepcopy(candidate),
            "state_before": state_before,
            "state_after_immediate": state_after_immediate,
            "state_after_immediate_action_response": deepcopy(immediate_log["state_after"]),
            "state_after_delayed": deepcopy(environment.session["state"]),
            "dynamics_before": dynamics_before,
            "dynamics_after_immediate": dynamics_after_immediate,
            "dynamics_after_immediate_action_response": deepcopy(immediate_log["dynamics_after"]),
            "dynamics_after_delayed": deepcopy(environment.session["dynamics"]),
            "delayed_horizon": delayed_horizon,
            "continuation_protocol": "free_form_same_model_policy",
            "continuation_policy_provenance": getattr(policy, "provenance", {}),
            "actual_turns_observed": 1 + continuation_steps,
            "elapsed_time_start": checkpoint_elapsed,
            "elapsed_time_end": environment.session.get("elapsed_time", checkpoint_elapsed),
            "elapsed_time_delta": (
                environment.session.get("elapsed_time", checkpoint_elapsed)
                - checkpoint_elapsed
            ),
            "crossed_event_nodes": deepcopy(
                environment.session.get("public_timeline", [])[checkpoint_timeline_count:]
            ),
            "external_event_plan_hash": environment.session.get(
                "event_plan", {}
            ).get("plan_hash"),
            "counterfactual_timeline_control": (
                "frozen_snapshot_plan_and_segment_boundary"
            ),
        }
        if branch_callback:
            branch_callback(branch_index,deepcopy(result))
        return result
    if branch_workers == 1:
        branches = [run_branch(pair) for pair in enumerate(candidate_actions)]
    else:
        with ThreadPoolExecutor(max_workers=min(branch_workers,len(candidate_actions))) as pool:
            branches = list(pool.map(run_branch,enumerate(candidate_actions)))
    if any(
        branch["external_event_plan_hash"] != frozen_event_plan_hash
        for branch in branches
    ):
        raise RuntimeError(
            "counterfactual branches did not preserve the frozen external event plan"
        )
    return branches
