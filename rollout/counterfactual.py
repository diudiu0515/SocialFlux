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
    for branch_index, candidate in enumerate(candidate_actions):
        environment = environment_factory()
        environment.restore(snapshot, episode_id=f"local-branch-{branch_index}")
        state_before = deepcopy(environment.session["state"])
        dynamics_before = deepcopy(environment.session["dynamics"])
        _, immediate_log = environment.step(deepcopy(candidate))
        policy = continuation_policy_factory()
        continuation_steps = 0
        while (
            continuation_steps < delayed_horizon - 1
            and environment.session["status"] == "active"
        ):
            environment.step(policy.generate(environment.observe()))
            continuation_steps += 1
        branches.append({
            "experiment": "local_action_intervention",
            "checkpoint_turn_id": checkpoint_turn["turn_id"],
            "candidate_action": deepcopy(candidate),
            "state_before": state_before,
            "state_after_immediate": deepcopy(immediate_log["state_after"]),
            "state_after_delayed": deepcopy(environment.session["state"]),
            "dynamics_before": dynamics_before,
            "dynamics_after_immediate": deepcopy(immediate_log["dynamics_after"]),
            "dynamics_after_delayed": deepcopy(environment.session["dynamics"]),
            "delayed_horizon": delayed_horizon,
            "continuation_protocol": "free_form_same_model_policy",
            "continuation_policy_provenance": getattr(policy, "provenance", {}),
        })
    return branches
