import json
import tempfile
import unittest
from pathlib import Path

from scripts.t2_common import ROOT, load, scenario_path
from tasks.T2.answering import validate_answer
from tasks.T2.branch_authoring import validate_authored_branch
from tasks.T2.configuration import load_t2_config
from tasks.T2.pair_builder import cross_speaker_echo_violations
from tasks.T2.quality_review import validate_pair_review
from tasks.T2.run_artifacts import (
    initialize_run,
    summarize_run,
    write_result,
)
from tasks.T2.source_selection import assess_source, find_audit_record, source_index
from tasks.T2.spec_authoring import candidate_windows, validate_spec


CONFIG = ROOT / "configs" / "t2_source_adaptation_v2.json"
AUDIT = ROOT / "build" / "scale300_v1" / "automatic_gate_audit.json"


class T2SourceAdaptationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.specs, cls.pair_source, cls.model_routes = load_t2_config(
            ROOT, CONFIG
        )
        cls.audit = load(AUDIT)

    def _source_inputs(self, index):
        spec = self.specs[index]
        scenario = load(scenario_path(spec["ordinal"]))
        source = load(ROOT / spec["source_rollout"])
        record = find_audit_record(
            self.audit,
            ordinal=spec["ordinal"],
            trajectory_id=source["trajectory_id"],
        )
        return spec, scenario, source, record

    def test_specs_bind_real_source_to_valid_checkpoint(self):
        self.assertGreaterEqual(len(self.specs), 3)
        for spec in self.specs:
            scenario = load(scenario_path(spec["ordinal"]))
            source = load(ROOT / spec["source_rollout"])
            self.assertEqual(source["scenario_id"], scenario["scenario_id"])
            indexes = source_index(source)
            self.assertLess(indexes[spec["fork_turn_id"]], indexes[spec["ending_turn_id"]])
            self.assertIn(
                "environment_snapshot_before",
                source["turns"][indexes[spec["fork_turn_id"]]],
            )

    def test_spec_windows_require_shared_prefix_and_do_not_cross_events(self):
        trajectory = {
            "turns": [
                {"turn_id": f"t{index}"}
                for index in range(1, 8)
            ]
        }
        windows = candidate_windows(
            trajectory,
            minimum_shared_prefix_turns=2,
            minimum_branch_turns=2,
            maximum_branch_turns=4,
        )
        self.assertTrue(windows)
        self.assertTrue(all(row["prefix_turn_count"] >= 2 for row in windows))
        self.assertTrue(all(row["adapted_turn_count"] >= 2 for row in windows))
        self.assertEqual(windows[0]["fork_turn_id"], "t3")

        trajectory["turns"][2]["segment_transition_after"] = {
            "public_events": [{"event_id": "checkpoint"}]
        }
        filtered = candidate_windows(trajectory)
        self.assertFalse(any(row["fork_turn_id"] == "t3" for row in filtered))

    def test_spec_validator_binds_exact_candidate_window(self):
        windows = [{
            "fork_turn_id": "t3",
            "ending_turn_id": "t5",
            "prefix_turn_count": 2,
            "adapted_turn_count": 2,
        }]
        value = {
            "fork_turn_id": "t3",
            "ending_turn_id": "t5",
            "adaptation_point": "改变对历史失约的解释。",
            "source_anchor_evidence": [{
                "turn_id": "t3",
                "speaker": "environment_character",
            }],
            "history_b_direction": "B 中对方先提供可核验解释。",
            "protected_facts": [
                "截止时间尚未到达",
                "材料尚未核验",
                "双方仍在合作",
                "当前没有替代人选",
                "此前曾经延期",
                "未发生可核验履约",
            ],
            "shared_ending_behavior": {
                "facial_expression": "克制地微笑",
                "gaze": "看向对方",
                "speech_style": "简短而礼貌",
                "prosody": "语速平稳",
                "behavioral_cues": ["轻轻点头"],
            },
            "rationale": "相同表达可由不同历史状态支持。",
        }
        trajectory = {"turns": [
            {
                "turn_id": "t3",
                "policy_action": {"text": "你需要给出安排。"},
                "environment_response": "我可以先说明原因，再给出安排。",
            },
            {
                "turn_id": "t4",
                "policy_action": {"text": "先说具体一点。"},
                "environment_response": "我会说明。",
            },
            {
                "turn_id": "t5",
                "policy_action": {"text": "继续。"},
                "environment_response": "好。",
            },
        ]}
        validated = validate_spec(value, windows, trajectory)
        self.assertEqual(
            validated["source_anchor_evidence"][0]["quote"],
            "我可以先说明原因，再给出安排。",
        )
        value["source_anchor_evidence"][0]["turn_id"] = "t5"
        with self.assertRaisesRegex(ValueError, "outside branch"):
            validate_spec(value, windows, trajectory)
        value["source_anchor_evidence"][0]["turn_id"] = "t3"
        value["ending_turn_id"] = "t6"
        with self.assertRaisesRegex(ValueError, "invalid window"):
            validate_spec(value, windows, trajectory)

    def test_low_information_source_is_skipped_before_generation(self):
        spec, scenario, source, record = self._source_inputs(0)
        result = assess_source(
            spec, scenario, source, record, self.config["source_selection"],
        )
        self.assertEqual(result["status"], "skipped_source_quality")
        self.assertIn("insufficient_history_before_ending", result["reasons"])

    def test_main_window_source_is_eligible(self):
        spec, scenario, source, record = self._source_inputs(1)
        result = assess_source(
            spec, scenario, source, record, self.config["source_selection"],
        )
        self.assertTrue(result["eligible"], result["reasons"])

    def test_complete_branch_validator_requires_exact_shape_but_not_word_rules(self):
        source_tail = [
            {"turn_id": "t5", "evaluated_agent": "A1", "environment_character": "E1"},
            {"turn_id": "t6", "evaluated_agent": "A2", "environment_character": "E2"},
        ]
        branch = {
            "turns": [
                {"turn_id": "t5", "evaluated_agent": "我不同意现在签。", "environment_character": "那先核对风险。"},
                {"turn_id": "t6", "evaluated_agent": "可以先看记录。", "environment_character": "我把范围限定在现有材料。"},
            ],
            "authoring_summary": "B 更审慎，但共享 ending 仍可成立。",
        }
        self.assertEqual(
            validate_authored_branch(branch, ["t5", "t6"], source_tail), branch,
        )
        branch["turns"][1]["turn_id"] = "t7"
        with self.assertRaisesRegex(ValueError, "turn ids"):
            validate_authored_branch(branch, ["t5", "t6"], source_tail)

    def test_echo_is_diagnostic_not_a_branch_rewrite(self):
        history = [{
            "turn_id": "t1",
            "evaluated_agent": "我们先核对原始记录。",
            "environment_character": "我们先核对原始记录。",
        }]
        self.assertEqual(
            cross_speaker_echo_violations(history),
            [{"turn_id": "t1", "speaker": "environment_agent"}],
        )

    def test_pair_review_requires_every_environment_turn_and_marks_issues(self):
        instance = {
            "input": {
                "history_a": [{"turn_id": "t1", "environment_character": "A 的回应。"}],
                "history_b": [{"turn_id": "t1", "environment_character": "B 的回应。"}],
                "shared_current_action": {"turn_id": "t2", "text": "继续。"},
                "shared_current_observation": {"current_response": "共享回应。"},
            }
        }
        checks = {
            "source_a_coherent": True,
            "history_b_coherent": True,
            "difference_locatable": True,
            "ending_natural_in_a": True,
            "ending_natural_in_b": True,
            "ownership_and_facts_sound": False,
            "no_sustained_empty_loop": True,
            "state_expression_link_supported": True,
            "history_is_necessary": True,
        }
        review = {
            "decision": "needs_revision",
            "checks": checks,
            "reviewed_environment_turns": [
                {"side": "A", "turn_id": "t1"},
                {"side": "B", "turn_id": "t1"},
                {"side": "shared", "turn_id": "t2"},
            ],
            "environment_issues": [
                {"side": "B", "turn_id": "t1", "categories": ["action_ownership"], "quote": "B 的回应", "description": "替对方执行动作。", "task_impact": "会污染状态归因。"},
            ],
            "rationale": "B 有局部动作归属问题。",
        }
        self.assertEqual(validate_pair_review(review, instance), review)
        review["reviewed_environment_turns"].pop()
        with self.assertRaisesRegex(ValueError, "coverage"):
            validate_pair_review(review, instance)

    def test_answer_validation_enforces_target_speaker_quote(self):
        instance = {
            "instance_id": "pair",
            "input": {
                "history_a": [{"turn_id": "t6", "environment_character": "A侧目标角色原话。"}],
                "history_b": [{"turn_id": "t6", "environment_character": "B侧目标角色原话。"}],
            },
            "target_spec": {"candidate_state_ids": ["relationship.trust"]},
        }
        answer = {
            "instance_id": "pair",
            "selected_state_ids": ["relationship.trust"],
            "predictions": [{
                "state_id": "relationship.trust",
                "direction_probabilities": {"higher_in_a": 0.7, "similar": 0.1, "higher_in_b": 0.1, "cannot_determine": 0.1},
                "evidence_a": [{"turn_id": "t6", "target_quote": "A侧目标角色原话", "interpretation": "支持 A。"}],
                "evidence_b": [{"turn_id": "t6", "target_quote": "B侧目标角色原话", "interpretation": "支持 B。"}],
                "key_history_events_a": ["t6"],
                "key_history_events_b": ["t6"],
                "rationale": "两侧公开反应不同。",
                "confidence": 0.7,
            }],
            "shared_expression_explanation": {"history_a": "维持合作。", "history_b": "礼貌克制。", "uncertainty": "有替代解释。"},
            "history_necessity": {"judgment": "necessary", "explanation": "ending 单独不足以区分。"},
        }
        self.assertEqual(validate_answer(answer, instance), answer)
        answer["predictions"][0]["evidence_b"][0]["target_quote"] = "错误说话人"
        with self.assertRaisesRegex(ValueError, "not target speech"):
            validate_answer(answer, instance)
        row = answer["predictions"][0]
        row["evidence_b"][0]["target_quote"] = "B侧目标角色原话"
        row["evidence_a"] = []
        row["key_history_events_a"] = []
        row["direction_probabilities"] = {
            "higher_in_a": 0.1,
            "similar": 0.2,
            "higher_in_b": 0.1,
            "cannot_determine": 0.6,
        }
        self.assertEqual(validate_answer(answer, instance), answer)
        row["direction_probabilities"]["cannot_determine"] = 0.1
        row["direction_probabilities"]["higher_in_b"] = 0.6
        with self.assertRaisesRegex(ValueError, "missing-side evidence"):
            validate_answer(answer, instance)
        row["evidence_b"] = []
        row["key_history_events_b"] = []
        with self.assertRaisesRegex(ValueError, "no public evidence"):
            validate_answer(answer, instance)

    def test_run_summary_uses_manifest_only_and_reports_not_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            initialize_run(
                run_dir,
                run_id="test_run",
                config_path=CONFIG,
                pair_source=self.pair_source,
                specs=self.specs,
                model_routes=self.model_routes,
            )
            result = {
                "format": "socialflux_t2_build_result_v2",
                "builder_version": "t2_source_adapted_v2",
                "run_id": "test_run",
                "status": "skipped_source_quality",
                "stage": "source_selection",
                "human_review": "pending",
            }
            write_result(run_dir, 0, self.specs[0], result)
            stale = run_dir / "results" / "unlisted_stale.json"
            stale.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            summary = summarize_run(run_dir)
            self.assertEqual(summary["result_count"], 1)
            self.assertEqual(summary["status_counts"]["skipped_source_quality"], 1)
            self.assertEqual(summary["status_counts"]["not_run"], len(self.specs) - 1)


if __name__ == "__main__":
    unittest.main()
