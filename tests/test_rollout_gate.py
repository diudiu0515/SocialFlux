import copy
import unittest

from evaluation.rollout_gate import (
    QUALITY_DIMENSIONS,
    audit_pool_contract,
    audit_rollout,
    infer_observed_outcome,
    public_judge_packet,
    select_diverse_trajectories,
)


def trajectory(index=0, family="qwen", source="local", scenario="IA_PIPE_001"):
    turns = []
    state = {"emotion": {"anger": 2}, "relationship": {"trust": 7}}
    for turn in range(6):
        before = copy.deepcopy(state)
        state = {
            "emotion": {"anger": min(10, 2 + turn // 2)},
            "relationship": {"trust": max(0, 7 - turn // 2)},
        }
        turns.append({
            "turn_id": f"t{turn + 1}",
            "policy_action": {"text": f"我想具体讨论第{turn + 1}个问题，方案编号{index}。"},
            "environment_response": f"我听到了第{turn + 1}点，但还需要更多依据，批次{index}。",
            "state_before": before,
            "state_after": copy.deepcopy(state),
            "dynamics_before": {"escalation_risk": turn},
            "dynamics_after": {"escalation_risk": turn + 1},
            "observable_expression": {"prosody": "克制"},
        })
    return {
        "trajectory_id": f"traj-{scenario}-{family}-{index}",
        "scenario_id": scenario,
        "turns": turns,
        "policy_provenance": {
            "model": f"{family}-model",
            "model_family": family,
            "source_type": source,
            "model_parameters_billion": 32 if family == "qwen" else 9,
        },
        "environment_provenance": {"environment": {"model": "environment-model"}},
    }


def judgment(item):
    return {
        "trajectory_id": item["trajectory_id"],
        "scores": {key: 4 for key in QUALITY_DIMENSIONS},
        "hard_reject_reasons": [],
        "rationale": "coherent and progressive",
    }


class RolloutGateTest(unittest.TestCase):
    def test_missing_independent_evidence_never_passes(self):
        result = audit_rollout(trajectory())
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "pending_evidence")
        self.assertIn("history_dependence", result["missing_evidence"])

    def test_complete_quality_evidence_passes(self):
        item = trajectory()
        result = audit_rollout(
            item,
            judgment(item),
            {"trajectory_id": item["trajectory_id"], "passed": True, "score": 0.8},
        )
        self.assertTrue(result["passed"])
        self.assertGreaterEqual(result["overall_score"], 0.7)

    def test_intervention_strength_does_not_replace_judge_history_score(self):
        item = trajectory()
        result = audit_rollout(
            item,
            judgment(item),
            {"trajectory_id": item["trajectory_id"], "passed": True, "score": 0.2},
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["scores"]["history_dependence"], 0.8)

    def test_stricter_history_character_naturalness_thresholds_are_enforced(self):
        item = trajectory()
        scores = {key: 4 for key in QUALITY_DIMENSIONS}
        scores["character_consistency"] = 3
        result = audit_rollout(
            item,
            {**judgment(item), "scores": scores},
            {"passed": True, "score": 0.8},
        )
        self.assertFalse(result["passed"])
        self.assertIn("character_consistency", result["diagnostics"]["threshold_failures"])

    def test_hidden_state_leakage_hard_rejects(self):
        item = trajectory()
        item["turns"][2]["environment_response"] = "state_before says trust is seven"
        result = audit_rollout(item, judgment(item), {"passed": True, "score": 0.8})
        self.assertIn("hidden_state_leakage", result["hard_reject_reasons"])
        self.assertFalse(result["passed"])

    def test_pool_contract_enforces_gate_md_ratios_and_separation(self):
        items = []
        for scenario in ("IA_PIPE_001", "IA_PIPE_002"):
            for family in ("qwen", "glm", "deepseek"):
                items.extend(trajectory(i, family, scenario=scenario) for i in range(4))
        selected = {
            scenario: [item for item in items if item["scenario_id"] == scenario][:4]
            for scenario in ("IA_PIPE_001", "IA_PIPE_002")
        }
        result = audit_pool_contract(items, selected)
        self.assertTrue(result["passed"])
        self.assertEqual(result["api_fraction"], 0.0)

    def test_selected_pool_uses_four_to_six_instead_of_raw_twelve(self):
        items = [trajectory(i, ("qwen", "glm", "deepseek")[i % 3]) for i in range(6)]
        result = audit_pool_contract(
            items,
            {"IA_PIPE_001": items},
            require_raw_minimum=False,
        )
        self.assertTrue(result["passed"])

    def test_diversity_selector_keeps_four_to_six(self):
        items = [trajectory(i, ("qwen", "glm", "deepseek")[i % 3]) for i in range(8)]
        items[0]["turns"][-1]["policy_action"]["text"] = "如果仍无法核验，我会离开这次协商。"
        audits = []
        for item in items:
            record = audit_rollout(
                item,
                judgment(item),
                {"passed": True, "score": 0.8},
            )
            record["overall_score"] = 0.9 - 0.01 * len(audits)
            audits.append(record)
        result = select_diverse_trajectories(items, audits)
        self.assertTrue(result["passed"])
        self.assertGreaterEqual(len(result["selected_ids"]), 4)
        self.assertLessEqual(len(result["selected_ids"]), 6)
        self.assertGreaterEqual(len(result["model_families"]), 3)
        self.assertGreaterEqual(len(set(result["observed_outcomes"])), 2)

    def test_judge_packet_excludes_private_state(self):
        packet = public_judge_packet(trajectory(), {
            "mechanism": "negotiation",
            "background": "A public conflict.",
            "environment_agent": {
                "persona": {"name": "A", "role": "manager", "patience": 0.4},
                "explicit_goal": "finish safely",
                "hidden_intention": "conceal a mistake",
            },
            "evaluated_agent_role": {"name": "B", "explicit_goal": "verify facts"},
        })
        self.assertNotIn("state_before", str(packet))
        self.assertNotIn("policy_provenance", packet)
        self.assertNotIn("hidden_intention", str(packet))
        self.assertEqual(packet["scenario_context"]["environment_agent"]["persona"]["role"], "manager")


if __name__ == "__main__":
    unittest.main()
