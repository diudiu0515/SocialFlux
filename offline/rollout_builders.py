"""Leakage-safe offline candidate builders from complete rollout records."""

from copy import deepcopy


def _public_turn(turn):
    action = turn["policy_action"]
    action_text = action.get("text", "") if isinstance(action, dict) else str(action)
    observation = deepcopy(turn["observation"])
    observation.pop("history", None)
    return {
        "turn_id": turn["turn_id"],
        "observation": observation,
        "policy_action": {"text": action_text},
        "environment_response": deepcopy(turn["environment_response"]),
    }


def _shared_observation(observation):
    shared = deepcopy(observation)
    shared.pop("history", None)
    return shared


def build_t1_checkpoints(trajectory, target_state_ids=None):
    """Extract ordinary checkpoints without private state or appraisal."""
    checkpoints = []
    for index, turn in enumerate(trajectory.get("turns", [])):
        checkpoints.append({
            "instance_id": f"{trajectory['trajectory_id']}_t1_{index + 1}",
            "benchmark_version": "rollout_benchmark_v1",
            "story_id": trajectory["scenario_id"],
            "story_version": "scenario_v1",
            "task_type": "T1_state_tracking",
            "language": "en",
            "split": "unassigned",
            "modality": "text",
            "input": {
                "target_character_id": turn["observation"].get("role", {}).get("character_id"),
                "history": [_public_turn(previous) for previous in trajectory["turns"][: index + 1]],
                "current_checkpoint": _shared_observation(turn["observation"]),
            },
            "target_spec": {
                "prediction_format": "subjective_state_tracking_v1",
                "target_state_ids": list(target_state_ids or []),
                "ground_truth_source": "human_annotation",
            },
            "ground_truth": None,
            "label_status": "pending_human_annotation",
            "metadata": {"source_trajectory_id": trajectory["trajectory_id"], "author_effects_exposed": False},
        })
    return checkpoints


def _history_signature(turns):
    return [(x["policy_action"].get("text", "") if isinstance(x["policy_action"], dict) else x["policy_action"],
             x["environment_response"]) for x in turns]


def build_t2_pairs(trajectories, current_observation_key="current_response"):
    """Pair identical public observations with genuinely different histories."""
    buckets = {}
    for trajectory in trajectories:
        for turn in trajectory.get("turns", []):
            key = turn["observation"].get(current_observation_key)
            if key is not None:
                buckets.setdefault((trajectory["scenario_id"], key), []).append((trajectory, turn))
    pairs = []
    for candidates in buckets.values():
        for index, (left, left_turn) in enumerate(candidates):
            for right, right_turn in candidates[index + 1:]:
                left_turns = [x for x in left["turns"] if x["turn_id"] <= left_turn["turn_id"]]
                right_turns = [x for x in right["turns"] if x["turn_id"] <= right_turn["turn_id"]]
                if _history_signature(left_turns) == _history_signature(right_turns):
                    continue
                pairs.append({
                    "instance_id": f"{left['trajectory_id']}_{right['trajectory_id']}_t2_{left_turn['turn_id']}",
                    "benchmark_version": "rollout_benchmark_v1",
                    "story_id": left["scenario_id"],
                    "story_version": "scenario_v1",
                    "task_type": "T2_history_sensitive_merge",
                    "language": "en",
                    "split": "unassigned",
                    "modality": "text",
                    "input": {
                        "history_a": [_public_turn(x) for x in left_turns],
                        "history_b": [_public_turn(x) for x in right_turns],
                        "shared_current_observation": _shared_observation(left_turn["observation"]),
                    },
                    "target_spec": {
                        "prediction_format": "pairwise_state_difference_v1",
                        "direction_labels": ["higher_in_a", "similar", "higher_in_b", "cannot_determine"],
                        "ground_truth_source": "human_annotation",
                    },
                    "ground_truth": None,
                    "label_status": "pending_human_annotation",
                    "metadata": {
                        "source_trajectory_ids": [left["trajectory_id"], right["trajectory_id"]],
                        "controlled_current_observation": True,
                        "author_effects_exposed": False,
                    },
                })
    return pairs


def build_t3_candidates(checkpoint, candidate_actions, delayed_horizon=5, target_state_ids=None):
    """Create a T3 candidate envelope; candidate branches share a fixed horizon."""
    if not 5 <= delayed_horizon <= 10:
        raise ValueError("T3 delayed_horizon must be between 5 and 10")
    return {
        "instance_id": f"{checkpoint['trajectory_id']}_t3_{checkpoint['turn_id']}",
        "benchmark_version": "rollout_benchmark_v1",
        "story_id": checkpoint.get("scenario_id", "unknown"),
        "story_version": "scenario_v1",
        "task_type": "T3_counterfactual_choice_effect",
        "language": "en",
        "split": "unassigned",
        "modality": "text",
        "input": {
            "history": deepcopy(checkpoint["observation"].get("history", [])),
            "current_observation": deepcopy(checkpoint["observation"]),
            "candidate_actions": deepcopy(candidate_actions),
        },
        "target_spec": {
            "prediction_format": "counterfactual_option_effects_v1",
            "time_horizons": ["immediate", "delayed"],
            "delayed_horizon": delayed_horizon,
            "continuation_protocol": "fixed",
            "target_state_ids": list(target_state_ids or []),
            "ground_truth_source": "human_annotation",
        },
        "ground_truth": None,
        "label_status": "pending_human_annotation",
        "metadata": {"continuation_protocol": "fixed", "author_effects_exposed": False},
    }
