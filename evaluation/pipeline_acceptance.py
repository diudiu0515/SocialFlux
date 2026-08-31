"""Acceptance checks for the five EmoTree pipeline validity criteria."""

from copy import deepcopy
import json
from pathlib import Path

from environment.delta_mapper import DELTA_TO_INT, flatten_state
from environment.env import StatefulEnvironment
from policies.controlled import ControlledPolicy
from rollout.runner import RolloutRunner


def load_scenarios(directory):
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(Path(directory).glob("scenario_*.json"))
    ]


def _run(scenario, action_id, turns=1, persona=None, text=None):
    candidate = deepcopy(scenario)
    if persona is not None:
        candidate["environment_agent"]["persona"] = deepcopy(persona)
    action = {"action_id": action_id, "text": text or action_id}
    runner = RolloutRunner(lambda: StatefulEnvironment(candidate))
    return runner.run(
        ControlledPolicy(action_id, [action]),
        max_turns=turns,
    )


def _run_text(scenario, text, turns=1, persona=None):
    candidate = deepcopy(scenario)
    if persona is not None:
        candidate["environment_agent"]["persona"] = deepcopy(persona)
    runner = RolloutRunner(lambda: StatefulEnvironment(candidate))
    return runner.run(
        ControlledPolicy("natural_text", [{"text": text}]),
        max_turns=turns,
    )


def _sign(value):
    return 1 if value > 0 else -1 if value < 0 else 0


def _expected_sign(label):
    return _sign(DELTA_TO_INT[label])


def _flatten_delta(delta):
    return flatten_state(delta)


def state_update_validity(scenarios):
    checks = []
    for scenario in scenarios:
        for action_id, effect in scenario["action_effects"].items():
            trajectory = _run(scenario, action_id)
            turn = trajectory["turns"][0]
            expected = _flatten_delta(effect["state_delta"])
            actual = _flatten_delta(turn["numeric_state_delta"])
            for variable, label in expected.items():
                checks.append({
                    "scenario_id": scenario["scenario_id"],
                    "action_id": action_id,
                    "variable": variable,
                    "expected_direction": _expected_sign(label),
                    "actual_direction": _sign(actual[variable]),
                    "passed": _sign(actual[variable]) == _expected_sign(label),
                })
    return {
        "criterion": "1. State Update Validity",
        "status": "passed" if all(item["passed"] for item in checks) else "failed",
        "check_count": len(checks),
        "passed_checks": sum(item["passed"] for item in checks),
        "checks": checks,
        "interpretation": "One-turn numeric transitions match every configured semantic state_delta direction.",
    }


def persona_sensitivity(scenarios):
    scenario = scenarios[0]
    action_id = "repair" if "repair" in scenario["action_effects"] else next(iter(scenario["action_effects"]))
    base = deepcopy(scenario["environment_agent"]["persona"])
    variant = deepcopy(base)
    variant["patience"] = max(0.0, min(1.0, float(variant.get("patience", 0.5)) - 0.35))
    variant["empathy"] = max(0.0, min(1.0, float(variant.get("empathy", 0.5)) + 0.35))
    first = _run(scenario, action_id, persona=base)
    second = _run(scenario, action_id, persona=variant)
    first_turn, second_turn = first["turns"][0], second["turns"][0]
    transition_equal = (
        first_turn["state_after"] == second_turn["state_after"]
        and first_turn["dynamics_after"] == second_turn["dynamics_after"]
    )
    modifier_present = "persona_modifier" in first_turn["appraisal"] and "persona_modifier" in second_turn["appraisal"]
    return {
        "criterion": "2. Persona Sensitivity",
        "status": "passed" if (not transition_equal and modifier_present) else "failed",
        "scenario_id": scenario["scenario_id"],
        "action_id": action_id,
        "persona_a": base,
        "persona_b": variant,
        "state_after_a": first_turn["state_after"],
        "state_after_b": second_turn["state_after"],
        "behavioral_difference_observed": not transition_equal,
        "modifier_present": modifier_present,
        "interpretation": "同一 history/action 下，仅改变 persona 会产生可解释的状态或互动动力学差异。",
    }


def paraphrase_robustness(scenarios):
    paraphrases = {
        "repair": (
            "我想先把问题说清楚，找一个双方都能接受的解决办法。",
            "我们先冷静沟通，一起讨论一个可执行的方案。",
        ),
        "escalate": (
            "如果没有明确处理，我会正式提出申诉并追究责任。",
            "若问题继续被忽视，我将启动正式程序并要求问责。",
        ),
        "neutral": (
            "我先听取更多信息，再决定下一步怎么做。",
            "我暂时不表态，等更多事实后再决定。",
        ),
    }
    checks = []
    for scenario in scenarios:
        for action_id in scenario["action_effects"]:
            text_a, text_b = paraphrases.get(action_id, (action_id, action_id))
            first = _run_text(scenario, text_a)["turns"][0]
            second = _run_text(scenario, text_b)["turns"][0]
            normalized_a = first["policy_action"]["action_id"]
            normalized_b = second["policy_action"]["action_id"]
            checks.append({
                "scenario_id": scenario["scenario_id"],
                "action_id": action_id,
                "normalized_action_a": normalized_a,
                "normalized_action_b": normalized_b,
                "canonical_action_equal": normalized_a == normalized_b == action_id,
                "state_delta_equal": first["state_after"] == second["state_after"],
                "dynamics_delta_equal": first["dynamics_after"] == second["dynamics_after"],
                "passed": (
                    normalized_a == normalized_b == action_id
                    and first["state_after"] == second["state_after"]
                    and first["dynamics_after"] == second["dynamics_after"]
                ),
            })
    return {
        "criterion": "3. Paraphrase Robustness",
        "status": "passed" if all(item["passed"] for item in checks) else "failed",
        "check_count": len(checks),
        "passed_checks": sum(item["passed"] for item in checks),
        "checks": checks,
        "interpretation": "自然语言同义 action 先经过 versioned normalizer，再进入同一 canonical state transition。",
    }


def controlled_policy_sensitivity(scenarios, turns=1):
    reports = []
    for scenario in scenarios:
        trajectories = {
            action_id: _run(scenario, action_id, turns=turns)
            for action_id in ("repair", "neutral", "escalate")
            if action_id in scenario["action_effects"]
        }
        first_turns = {key: value["turns"][0] for key, value in trajectories.items()}
        variable_checks = []
        for action_id, effect in scenario["action_effects"].items():
            if action_id not in first_turns:
                continue
            expected = _flatten_delta(effect["state_delta"])
            actual = _flatten_delta(first_turns[action_id]["numeric_state_delta"])
            for variable, label in expected.items():
                variable_checks.append(_sign(actual[variable]) == _expected_sign(label))
        final_states = [
            flatten_state(trajectory["turns"][-1]["state_after"])
            for trajectory in trajectories.values()
            if trajectory["turns"]
        ]
        spread = {}
        for variable in sorted({key for state in final_states for key in state}):
            values = [state[variable] for state in final_states if variable in state]
            spread[variable] = max(values) - min(values) if values else 0
        divergent = any(value > 0 for value in spread.values())
        reports.append({
            "scenario_id": scenario["scenario_id"],
            "turns_checked": turns,
            "direction_checks_passed": all(variable_checks),
            "direction_check_count": len(variable_checks),
            "final_state_spread": spread,
            "meaningful_divergence_observed": divergent,
            "passed": all(variable_checks) and divergent,
        })
    return {
        "criterion": "4. Controlled Policy Sensitivity",
        "status": "passed" if all(item["passed"] for item in reports) else "failed",
        "scenario_count": len(reports),
        "passed_scenarios": sum(item["passed"] for item in reports),
        "scenarios": reports,
        "interpretation": "Repair, neutral and escalation produce configured directional divergence across all scenarios.",
    }


def _trajectory_semantic_checks(scenario, action_id, trajectory):
    effect = scenario["action_effects"][action_id]
    expected = _flatten_delta(effect["state_delta"])
    direction_checks = []
    turn_ids = []
    for turn in trajectory["turns"]:
        actual = _flatten_delta(turn["numeric_state_delta"])
        before = flatten_state(turn["state_before"])
        checks = []
        for key, label in expected.items():
            expected_sign = _expected_sign(label)
            observed_sign = _sign(actual[key])
            clipped_at_bound = (
                (expected_sign < 0 and before[key] == 0)
                or (expected_sign > 0 and before[key] == 10)
            )
            checks.append(observed_sign == expected_sign or clipped_at_bound)
        direction_checks.extend(checks)
        turn_ids.append(turn["turn_id"])
    policy_checks = {
        "configured_directions_hold": all(direction_checks),
        "turn_ids_in_order": turn_ids == sorted(turn_ids, key=lambda value: int(value[1:])),
        "appraisal_contains_persona_context": all(
            "persona_modifier" in turn["appraisal"]
            and turn["appraisal"].get("relevant_history") is not None
            for turn in trajectory["turns"]
        ),
        "expression_media_are_serializable": all(
            isinstance(turn["observable_expression"], dict) and isinstance(turn["media"], list)
            for turn in trajectory["turns"]
        ),
    }
    return policy_checks


def full_trajectory_plausibility(scenarios, turns=8):
    reports = []
    for scenario in scenarios:
        scenario_reports = []
        for action_id in ("repair", "neutral", "escalate"):
            if action_id not in scenario["action_effects"]:
                continue
            trajectory = _run(scenario, action_id, turns=turns)
            state_values = [
                value
                for turn in trajectory["turns"]
                for value in flatten_state(turn["state_after"]).values()
            ]
            dynamics_values = [
                value
                for turn in trajectory["turns"]
                for value in flatten_state(turn["dynamics_after"]).values()
            ]
            history_turn_ids = {
                f"t{item['turn_id']}"
                for turn in trajectory["turns"]
                for item in turn["observation"]["history"]
            }
            memory_ids = {
                item
                for turn in trajectory["turns"]
                for item in turn["memory_view"]["relevant_turn_ids"]
            }
            structural_checks = {
                "length_5_to_10": 5 <= len(trajectory["turns"]) <= 10,
                "state_bounds": all(0 <= value <= 10 for value in state_values),
                "dynamics_bounds": all(0 <= value <= 10 for value in dynamics_values),
                "nonempty_responses": all(turn["environment_response"].strip() for turn in trajectory["turns"]),
                "memory_references_prior_history": memory_ids <= history_turn_ids,
                "state_transition_fields_present": all(
                    all(key in turn for key in ("state_before", "state_after", "state_delta", "appraisal"))
                    for turn in trajectory["turns"]
                ),
            }
            semantic_checks = _trajectory_semantic_checks(scenario, action_id, trajectory)
            all_checks = {**structural_checks, **semantic_checks}
            scenario_reports.append({
                "policy_id": action_id,
                "turn_count": len(trajectory["turns"]),
                "structural_checks": structural_checks,
                "semantic_pre_review_checks": semantic_checks,
                "structurally_valid": all(structural_checks.values()),
                "expert_pre_review_passed": all(all_checks.values()),
            })
        reports.append({
            "scenario_id": scenario["scenario_id"],
            "policies": scenario_reports,
            "structurally_valid": all(item["structurally_valid"] for item in scenario_reports),
            "expert_pre_review_passed": all(item["expert_pre_review_passed"] for item in scenario_reports),
        })
    pre_review_passed = all(item["expert_pre_review_passed"] for item in reports)
    return {
        "criterion": "5. Full Trajectory Plausibility",
        "status": "provisionally_passed" if pre_review_passed else "failed",
        "scenario_count": len(reports),
        "structurally_valid_scenarios": sum(item["structurally_valid"] for item in reports),
        "expert_pre_review_valid_scenarios": sum(item["expert_pre_review_passed"] for item in reports),
        "scenarios": reports,
        "formal_human_judgment": "pending",
        "human_judgment_required": [
            "人物反应是否像真实角色而非模板拼接",
            "状态变化和回应是否与整段历史一致",
            "repair/escalate/neutral 的整体轨迹是否符合社会机制",
        ],
        "interpretation": "自动结构检查和可复核专家预审通过；真实人工语义签字仍需由评审者完成。",
    }


def build_acceptance_report(scenarios):
    criteria = [
        state_update_validity(scenarios),
        persona_sensitivity(scenarios),
        paraphrase_robustness(scenarios),
        controlled_policy_sensitivity(scenarios, turns=1),
        full_trajectory_plausibility(scenarios, turns=8),
    ]
    engineering_statuses = {"passed", "provisionally_passed"}
    return {
        "format": "emotree_pipeline_acceptance_v1",
        "scenario_count": len(scenarios),
        "criteria": criteria,
        "gate": {
            "automated_passed": all(item["status"] in engineering_statuses for item in criteria),
            "research_acceptance": all(item["status"] == "passed" for item in criteria),
            "blocking_items": [
                item["criterion"] for item in criteria
                if item["status"] not in engineering_statuses
            ],
            "formal_human_pending": [
                item["criterion"] for item in criteria
                if item.get("formal_human_judgment") == "pending"
            ],
        },
    }
