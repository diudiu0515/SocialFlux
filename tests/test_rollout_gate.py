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
    action_texts = [
        "先核对原始贡献记录。", "请说明决定形成的时间线。", "我愿意听取资源限制。",
        "能否区分事实与推测？", "这项安排会影响我的毕业。", "我提出共享材料清单。",
        "如果署名不变，请解释标准。", "我们可以邀请中立同事旁听。", "我承认沟通时间太晚。",
        "先处理最紧迫的截止日期。", "这部分工作由我独立完成。", "请确认哪些证据仍然缺失。",
        "我可以接受阶段性复核。", "但口头承诺不足以执行。", "我们把分歧写成两个选项。",
        "我需要保留正式申诉空间。", "也愿意补做必要验证。", "请对刚才的让步明确回应。",
        "若仍无共识，我建议暂停决定。", "现在请确认最终可执行安排。",
    ]
    response_texts = [
        "记录可以查看，但背景比表格复杂。", "时间线里还有一次临时调整。", "资源确实有限，我不想回避。",
        "有些判断来自经验而非文件。", "我理解毕业安排不能一直悬着。", "材料清单可以先由双方确认。",
        "标准包含投入和整体责任。", "旁听人选需要双方都信任。", "时间压力让沟通变得仓促。",
        "截止日期可以先单独处理。", "独立完成的范围还需核验。", "缺的是版本记录和交接说明。",
        "阶段复核比一次定死更可行。", "书面记录会增加我的顾虑。", "两个选项可以帮助委员会判断。",
        "正式申诉会改变后续合作方式。", "补充验证能降低目前的不确定性。", "我愿意回应，但需要更窄的问题。",
        "暂停会影响项目，不过并非不能谈。", "最终安排必须同时覆盖责任与期限。",
    ]
    state = {"emotion": {"anger": 2}, "relationship": {"trust": 7}}
    for turn in range(20):
        before = copy.deepcopy(state)
        state = {
            "emotion": {"anger": min(10, 2 + turn // 2)},
            "relationship": {"trust": max(0, 7 - turn // 2)},
        }
        turns.append({
            "turn_id": f"t{turn + 1}",
            "policy_action": {"text": action_texts[turn] + f" 编号{index}。"},
            "environment_response": response_texts[turn] + f" 批次{index}。",
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
        "ending": {"reason": "max_turns", "turn_id": 20},
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
        without_history = audit_rollout(
            item,
            {**judgment(item), "scores": scores},
        )
        self.assertEqual(without_history["status"], "rejected")

    def test_hidden_state_leakage_hard_rejects(self):
        item = trajectory()
        item["turns"][2]["environment_response"] = "state_before says trust is seven"
        result = audit_rollout(item, judgment(item), {"passed": True, "score": 0.8})
        self.assertIn("hidden_state_leakage", result["hard_reject_reasons"])
        self.assertFalse(result["passed"])

    def test_natural_ending_before_twenty_is_not_automatically_rejected(self):
        item = trajectory()
        item["turns"] = item["turns"][:17]
        item["ending"] = {"reason": "natural_completion", "turn_id": 17}
        result = audit_rollout(
            item, judgment(item), {"passed": True, "score": 0.8}
        )
        self.assertNotIn(
            "meaningless_premature_ending", result["hard_reject_reasons"]
        )

        item["ending"] = {"reason": "max_turns", "turn_id": 17}
        invalid = audit_rollout(
            item, judgment(item), {"passed": True, "score": 0.8}
        )
        self.assertIn(
            "meaningless_premature_ending", invalid["hard_reject_reasons"]
        )

    def test_short_natural_trajectory_is_not_canonical_admission(self):
        item = trajectory()
        item["turns"] = item["turns"][:7]
        item["ending"] = {"reason": "natural_completion", "turn_id": 7}
        result = audit_rollout(
            item, judgment(item), {"passed": True, "score": 0.8}
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "rejected")
        self.assertIn("short_natural_trajectory", result["eligibility_failures"])


    def test_pool_contract_enforces_one_raw_trajectory_per_scenario(self):
        items = []
        for scenario in ("IA_PIPE_001", "IA_PIPE_002"):
            items.append(trajectory(len(items), "qwen", scenario=scenario))
        selected = {
            scenario: [item for item in items if item["scenario_id"] == scenario][:1]
            for scenario in ("IA_PIPE_001", "IA_PIPE_002")
        }
        result = audit_pool_contract(items, selected)
        self.assertTrue(result["passed"])
        self.assertEqual(result["api_fraction"], 0.0)
        self.assertTrue(result["checks"]["every_trajectory_has_1_to_20_turns"])
        self.assertTrue(
            result["checks"]["every_trajectory_has_consistent_natural_or_max_ending"]
        )
        self.assertTrue(result["checks"]["model_and_source_are_provenance_not_quotas"])

    def test_selected_pool_keeps_exactly_one_instead_of_raw_three(self):
        items = [trajectory(i, ("qwen", "glm", "deepseek")[i % 3]) for i in range(6)]
        result = audit_pool_contract(
            items,
            {"IA_PIPE_001": items[:1]},
            require_raw_minimum=False,
        )
        self.assertTrue(result["passed"])

    def test_selector_keeps_one_quality_first_winner(self):
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
        self.assertEqual(len(result["selected_ids"]), 1)
        self.assertEqual(result["selected_ids"][0], items[0]["trajectory_id"])
        self.assertFalse(result["model_quota"])

    def test_diversity_selector_does_not_force_model_balance(self):
        items = [trajectory(i, "qwen" if i < 6 else "glm") for i in range(8)]
        items[0]["turns"][-1]["policy_action"]["text"] = "我决定离开并结束这次沟通。"
        audits = []
        for index, item in enumerate(items):
            record = audit_rollout(
                item, judgment(item), {"passed": True, "score": 0.8}
            )
            record["overall_score"] = 0.95 - 0.01 * index
            audits.append(record)
        result = select_diverse_trajectories(items, audits)
        self.assertTrue(result["passed"])
        self.assertEqual(result["model_families"], ["qwen"])

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
