"""T3 counterfactual branching from one checkpoint with fixed continuation."""

from copy import deepcopy


def _replay_to(environment, checkpoint_turns):
    environment.reset()
    for turn in checkpoint_turns:
        environment.step(deepcopy(turn["policy_action"]))


def branch_counterfactuals(environment_factory, checkpoint_turns, candidate_actions,
                           continuation_actions, delayed_horizon=5):
    if not 5 <= delayed_horizon <= 10:
        raise ValueError("delayed_horizon must be between 5 and 10")
    branches = []
    for candidate in candidate_actions:
        environment = environment_factory()
        _replay_to(environment, checkpoint_turns)
        state_before = deepcopy(environment.session["state"])
        dynamics_before = deepcopy(environment.session["dynamics"])
        _, immediate_log = environment.step(deepcopy(candidate))
        continuation = list(continuation_actions)
        while len(continuation) < delayed_horizon - 1:
            continuation.append(continuation[-1] if continuation else {"action_id": "default", "text": ""})
        for action in continuation[: delayed_horizon - 1]:
            if environment.session["status"] != "active":
                break
            environment.step(deepcopy(action))
        final_state = deepcopy(environment.session["state"])
        final_dynamics = deepcopy(environment.session["dynamics"])
        branches.append({
            "candidate_action": deepcopy(candidate),
            "state_before": state_before,
            "state_after_immediate": deepcopy(immediate_log["state_after"]),
            "state_after_delayed": final_state,
            "dynamics_before": dynamics_before,
            "dynamics_after_delayed": final_dynamics,
            "delayed_horizon": delayed_horizon,
            "continuation_protocol": "fixed",
        })
    return branches
