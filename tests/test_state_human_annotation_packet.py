import hashlib
import json
from pathlib import Path
import unittest

from scripts.prepare_state_human_annotation_round import (
    DEFAULT_MANIFEST,
    DEFAULT_OUTPUT,
    build_packet,
)
from web.server import api_payload


class StateHumanAnnotationPacketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))

    def test_packet_contains_complete_frozen_review_set(self):
        self.assertEqual(
            self.packet["summary"],
            {
                "record_count": 5,
                "scenario_count": 4,
                "complete_rollout_turn_count": 70,
                "required_target_count": 8,
            },
        )
        self.assertTrue(self.packet["blind_to_model_answers"])
        self.assertEqual(self.packet["model_calls"], 0)
        self.assertEqual(
            sum(len(record["targets"]) for record in self.packet["records"]),
            8,
        )
        self.assertEqual(self.packet["format"], "socialflux_state_human_annotation_round_v2")
        self.assertEqual(self.packet["interface_revision"], "state_judgment_primary_v7")
        self.assertNotIn("evidence_feature", self.packet["annotation_schema"])
        self.assertNotIn("suggested_delta", self.packet["annotation_schema"])
        self.assertEqual(
            build_packet(DEFAULT_MANIFEST)["packet_sha256"], self.packet["packet_sha256"]
        )

    def test_sources_are_hash_bound_and_every_turn_is_present(self):
        for record in self.packet["records"]:
            scenario_path = Path(record["scenario_path"])
            rollout_path = Path(record["rollout_path"])
            source_rollout = json.loads(rollout_path.read_text(encoding="utf-8"))
            self.assertEqual(
                record["scenario_sha256"],
                hashlib.sha256(scenario_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                record["rollout_sha256"],
                hashlib.sha256(rollout_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(record["turn_count"], len(source_rollout["turns"]))
            self.assertEqual(len(record["turns"]), len(source_rollout["turns"]))

    def test_blind_payload_excludes_prior_answers_and_deltas(self):
        forbidden = {
            "expected_judgment",
            "label_rationale",
            "target_impact",
            "appraisal",
            "state_delta",
            "calibration",
        }
        for record in self.packet["records"]:
            for turn in record["turns"]:
                self.assertTrue(forbidden.isdisjoint(turn))
            for target in record["targets"]:
                self.assertTrue(forbidden.isdisjoint(target))
                self.assertEqual(target["human_annotation"]["status"], "pending")

    def test_api_and_frontend_expose_the_frozen_packet(self):
        served = api_payload("/api/state-annotation")
        self.assertEqual(served["packet_sha256"], self.packet["packet_sha256"])
        self.assertEqual(served["summary"], self.packet["summary"])
        html = Path("web/static/state_annotation.html").read_text(encoding="utf-8")
        script = Path("web/static/state_annotation.js").read_text(encoding="utf-8")
        self.assertIn("可用于判断的历史与当前动作", script)
        self.assertIn('fetch("/api/state-annotation"', script)
        self.assertIn("socialflux_state_human_annotations_v1", script)
        self.assertNotIn("suggested_delta", script)
        self.assertIn("humanValue(value)", script)
        self.assertIn('numericTable("State（0–10）"', script)
        self.assertIn("原始更新前上下文 JSON（仅供核查）", script)
        self.assertIn("目标动作之后的 environment response 已隐藏", script)
        self.assertIn("盲化人工标注", html)


if __name__ == "__main__":
    unittest.main()
