"""Leakage-safe offline candidates derived from naturally evolved model trajectories."""

from copy import deepcopy

from environment.delta_mapper import flatten_state


def _public_turn(turn):
    action_text = turn["policy_action"]["text"]
    observation = deepcopy(turn["observation"])
    observation.pop("history", None)
    return {
        "turn_id": turn["turn_id"],
        "observation": observation,
        "policy_action": {"text": action_text},
        "environment_response": deepcopy(turn["environment_response"]),
    }


def _public_history(trajectory, end_index):
    return [_public_turn(turn) for turn in trajectory["turns"][: end_index + 1]]


def _shared_observation(observation):
    shared = deepcopy(observation)
    shared.pop("history", None)
    return shared


def build_t1_checkpoints(trajectory, target_state_ids=None):
    checkpoints = []
    for index, turn in enumerate(trajectory.get("turns", [])):
        checkpoints.append({
            "instance_id": f"{trajectory['trajectory_id']}_t1_{index + 1}",
            "benchmark_version": "socialflux_v1",
            "story_id": trajectory["scenario_id"],
            "story_version": "scenario_v2",
            "task_type": "T1_state_tracking",
            "language": "zh",
            "split": "unassigned",
            "modality": "text",
            "input": {
                "target_character_id": turn["observation"].get("target_character", {}).get("character_id"),
                "history": _public_history(trajectory, index),
                "current_checkpoint": _shared_observation(turn["observation_after"]),
            },
            "target_spec": {
                "prediction_format": "subjective_state_tracking_v1",
                "target_state_ids": list(target_state_ids or []),
                "ground_truth_source": "human_annotation",
            },
            "ground_truth": None,
            "label_status": "pending_human_annotation",
            "metadata": {
                "source_trajectory_id": trajectory["trajectory_id"],
                "trajectory_origin": "free_form_model_interaction",
                "private_state_exposed": False,
            },
        })
    return checkpoints


def _history_signature(trajectory, end_index):
    return [
        (turn["policy_action"]["text"], turn["environment_response"])
        for turn in trajectory["turns"][: end_index + 1]
    ]


def _state_distance(left_turn, right_turn):
    left = flatten_state(left_turn["state_before"])
    right = flatten_state(right_turn["state_before"])
    shared = set(left) & set(right)
    return sum(abs(left[key] - right[key]) for key in shared)


def _source_model(trajectory):
    return trajectory.get("policy_provenance", {}).get("model")


def retrieve_divergent_history_pairs(trajectories, same_source_model=False):
    """Rank same-scenario, same-depth checkpoints by private state divergence."""
    candidates = []
    for left_index, left in enumerate(trajectories):
        for right in trajectories[left_index + 1:]:
            if left["scenario_id"] != right["scenario_id"]:
                continue
            if same_source_model and _source_model(left) != _source_model(right):
                continue
            max_depth = min(len(left.get("turns", [])), len(right.get("turns", [])))
            for depth in range(1, max_depth):
                if _history_signature(left, depth - 1) == _history_signature(right, depth - 1):
                    continue
                distance = _state_distance(left["turns"][depth], right["turns"][depth])
                if distance <= 0:
                    continue
                candidates.append({
                    "left": left,
                    "right": right,
                    "left_index": depth - 1,
                    "right_index": depth - 1,
                    "state_distance": distance,
                })
    return sorted(candidates, key=lambda item: item["state_distance"], reverse=True)


def build_t2_pair(candidate, shared_observation, target_state_ids=None):
    left = candidate["left"]
    right = candidate["right"]
    left_index = candidate["left_index"]
    right_index = candidate["right_index"]
    history_a = _public_history(left, left_index)
    history_b = _public_history(right, right_index)
    return {
        "instance_id": f"{left['trajectory_id']}_{right['trajectory_id']}_t2_{left_index + 1}",
        "benchmark_version": "socialflux_v1",
        "story_id": left["scenario_id"],
        "story_version": "scenario_v2",
        "task_type": "T2_history_sensitive_merge",
        "language": "zh",
        "split": "unassigned",
        "modality": "text",
        "input": {
            "target_character": deepcopy(
                left["turns"][0]["observation"].get("target_character", {})
            ),
            "history_a": history_a,
            "history_b": history_b,
            "shared_current_observation": deepcopy(shared_observation),
        },
        "target_spec": {
            "prediction_format": "pairwise_state_difference_v1",
            "target_character_id": left["turns"][0]["observation"].get(
                "target_character", {}
            ).get("character_id"),
            "target_state_ids": list(target_state_ids or []),
            "direction_labels": [
                "higher_in_a",
                "similar",
                "higher_in_b",
                "cannot_determine",
            ],
            "ground_truth_source": "human_annotation",
        },
        "ground_truth": None,
        "label_status": "pending_human_annotation",
        "metadata": {
            "source_trajectory_ids": [left["trajectory_id"], right["trajectory_id"]],
            "trajectory_origin": "free_form_model_interaction",
            "shared_observation_injected": True,
            "compatibility_status": "pending_human_validation",
            "private_state_exposed": False,
        },
    }


def build_t2_pairs(
    trajectories,
    shared_observation_factory,
    max_pairs,
    target_state_ids=None,
    same_source_model=False,
):
    pairs = []
    candidates = retrieve_divergent_history_pairs(
        trajectories,
        same_source_model=same_source_model,
    )
    if same_source_model:
        grouped = {}
        for candidate in candidates:
            model = _source_model(candidate["left"])
            grouped.setdefault(model, []).append(candidate)
        candidates = []
        depth = 0
        while any(depth < len(group) for group in grouped.values()):
            for group in grouped.values():
                if depth < len(group):
                    candidates.append(group[depth])
            depth += 1
    for candidate in candidates:
        history_a = _public_history(candidate["left"], candidate["left_index"])
        history_b = _public_history(candidate["right"], candidate["right_index"])
        first_observation = candidate["left"]["turns"][0]["observation"]
        shared = shared_observation_factory(
            history_a,
            history_b,
            first_observation.get("target_character", {}),
            first_observation.get("role", {}),
        )
        pairs.append(build_t2_pair(candidate, shared, target_state_ids))
        if len(pairs) >= max_pairs:
            break
    return pairs


def build_t3_candidates(checkpoint, candidate_actions, delayed_horizon=5, target_state_ids=None):
    if not 5 <= delayed_horizon <= 10:
        raise ValueError("T3 delayed_horizon must be between 5 and 10")
    if any(set(action) != {"text"} or not action["text"].strip() for action in candidate_actions):
        raise ValueError("T3 candidates must be free-form text without action taxonomy")
    return {
        "instance_id": f"{checkpoint['trajectory_id']}_t3_{checkpoint['turn_id']}",
        "benchmark_version": "socialflux_v1",
        "story_id": checkpoint["scenario_id"],
        "story_version": "scenario_v2",
        "task_type": "T3_counterfactual_choice_effect",
        "language": "zh",
        "split": "unassigned",
        "modality": "text",
        "input": {
            "history": deepcopy(checkpoint["observation"].get("history", [])),
            "current_observation": _shared_observation(checkpoint["observation"]),
            "candidate_actions": deepcopy(candidate_actions),
        },
        "target_spec": {
            "prediction_format": "counterfactual_option_effects_v1",
            "target_character_id": checkpoint["observation"].get(
                "target_character", {}
            ).get("character_id"),
            "time_horizons": ["immediate", "delayed"],
            "delayed_horizon": delayed_horizon,
            "continuation_protocol": "free_form_same_model_policy",
            "target_state_ids": list(target_state_ids or []),
            "ground_truth_source": "human_annotation",
        },
        "ground_truth": None,
        "label_status": "pending_human_annotation",
        "metadata": {
            "source_trajectory_id": checkpoint["trajectory_id"],
            "checkpoint_turn_id": checkpoint["turn_id"],
            "checkpoint_origin": "free_form_model_interaction",
            "local_intervention": True,
            "private_state_exposed": False,
        },
    }
