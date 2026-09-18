"""Local counterfactual branches restored from real free-form checkpoints."""

from copy import deepcopy


def branch_counterfactuals(
    environment_factory,
    checkpoint_turn,
    candidate_actions,
    continuation_policy_factory,
    delayed_horizon=5,
):
    if not 5 <= delayed_horizon <= 10:
        raise ValueError("delayed_horizon must be between 5 and 10")
    snapshot = checkpoint_turn.get("environment_snapshot_before")
    if not snapshot:
        raise ValueError("checkpoint lacks a private environment snapshot")
    branches = []
    checkpoint_elapsed = snapshot.get("elapsed_time", 0)
    checkpoint_timeline_count = len(snapshot.get("public_timeline", []))
    frozen_event_plan_hash = snapshot.get("event_plan", {}).get("plan_hash")
    for branch_index, candidate in enumerate(candidate_actions):
        environment = environment_factory()
        policy = continuation_policy_factory()
        last_error = None
        # Each response already performs up to 4 distinct-text attempts.
        # Two snapshot replays are enough before trying the next checkpoint.
        for branch_attempt in range(2):
            environment.restore(
                snapshot,
                episode_id=f"local-branch-{branch_index}-attempt-{branch_attempt}",
            )
            environment.session["counterfactual_timeline_lock"] = True
            state_before = deepcopy(environment.session["state"])
            dynamics_before = deepcopy(environment.session["dynamics"])
            try:
                _, immediate_log = environment.step(deepcopy(candidate))
                state_after_immediate = deepcopy(environment.session["state"])
                dynamics_after_immediate = deepcopy(environment.session["dynamics"])
                continuation_steps = 0
                while (
                    continuation_steps < delayed_horizon - 1
                    and environment.session["status"] == "active"
                ):
                    environment.step(policy.generate(environment.observe()))
                    continuation_steps += 1
                break
            except ValueError as exc:
                last_error = exc
        else:
            raise RuntimeError(
                f"counterfactual branch {branch_index} exhausted retries"
            ) from last_error
        branches.append({
            "experiment": "local_action_intervention",
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
        })
    if any(
        branch["external_event_plan_hash"] != frozen_event_plan_hash
        for branch in branches
    ):
        raise RuntimeError(
            "counterfactual branches did not preserve the frozen external event plan"
        )
    return branches
