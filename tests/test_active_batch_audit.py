from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import json
from unittest.mock import patch

from scripts.audit_active_batch import (
    audit_batch,
    audit_gate2,
    audit_scenarios,
    failure_report,
    package_complete,
)
from scripts.author_claude150_t2_specs import reusable_record
from scripts.run_claude150_full import command_for


def complete_task():
    return {
        "instance": {"instance_id": "x"},
        "llm_answer": {"answer": "proposal"},
        "answer_status": "machine_proposal_pending_human_review",
    }


class ActiveBatchAuditTest(unittest.TestCase):
    def test_gate2_packet_requires_e9_timescale_sample(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            gate2 = root / "gate2"
            gate2.mkdir()
            manifest = {
                "e1_review_items": 10,
                "e2_review_items": 10,
                "e9_review_items": 9,
            }
            (gate2 / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            self.assertFalse(audit_gate2(root)["packets_ready"])
            manifest["e9_review_items"] = 10
            (gate2 / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            self.assertTrue(audit_gate2(root)["packets_ready"])

    def test_batch_audit_discovers_nested_gpt_scenario_root(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "scenario" / "scenarios" / "scenario_001" / "scenario_001.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "scenario_id": "GPT50_001",
                "state_contract_version": "socialflux_state_v2",
            }), encoding="utf-8")
            with patch("scripts.audit_active_batch.validate_scenario"):
                report = audit_batch(root, expected=1, prefix="GPT50_")
        self.assertEqual(report["stages"]["scenarios"]["valid"], 1)

    def test_empty_batch_reports_exact_missing_ordinals_without_network(self):
        with TemporaryDirectory() as directory:
            report = audit_batch(directory, expected=2, prefix="CF150_")
        self.assertEqual(report["network_requests_performed"], 0)
        self.assertEqual(report["stages"]["scenarios"]["missing_ordinals"], [1, 2])
        self.assertEqual(report["stages"]["tasks"]["missing_ordinals"], [1, 2])
        self.assertIn("scenarios", failure_report(report)["failures"])

    def test_active_scenario_audit_rejects_legacy_state_contract(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "scenarios" / "scenario_001" / "scenario_001.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"scenario_id": "CF150_001"}), encoding="utf-8")
            with patch("scripts.audit_active_batch.validate_scenario"):
                result = audit_scenarios(root, expected=1, prefix="CF150_")
        self.assertEqual(result["valid"], 0)
        self.assertEqual(result["invalid"][0]["ordinal"], 1)
        self.assertIn("socialflux_state_v2", result["invalid"][0]["error"])

    def test_task_package_requires_all_four_instances_and_answers(self):
        package = {"tasks": {name: complete_task() for name in ("T1", "T2", "T3", "T4")}}
        self.assertTrue(package_complete(package))
        package["tasks"]["T3"]["llm_answer"] = None
        self.assertFalse(package_complete(package))

    def test_t2_resume_never_reuses_api_failure(self):
        base = {"model_routes_sha256": "routes", "code_fingerprint": "code"}
        self.assertFalse(reusable_record(
            {**base, "status": "authoring_failed"}, "routes", "code"
        ))
        self.assertTrue(reusable_record({
            **base,
            "status": "authored_pending_pair_construction_and_human_review",
            "spec": {},
        }, "routes", "code"))

    def test_orchestrator_has_offline_gate2_and_strict_completion_flags(self):
        args = SimpleNamespace(
            count=150,
            model_routes=Path("routes.json"),
            rollout_config=Path("rollout.json"),
            scenario_workers=2,
            rollout_workers=2,
            task_workers=2,
            max_attempts=3,
            allow_route_migration=True,
        )
        batch = Path("data/claude150_v1")
        gate2 = command_for("gate2_packet", args, batch)
        self.assertIn("--prepare-only", gate2)
        gate2_experiments = command_for("gate2_experiments", args, batch)
        self.assertIn("--allow-pending-video", gate2_experiments)
        self.assertIn(
            "scripts/prepare_multimodal_video_queue.py",
            command_for("multimodal_plan", args, batch),
        )
        self.assertIn("--require-complete", command_for("t2_specs", args, batch))
        self.assertIn("--resume-incomplete", command_for("t2_pairs", args, batch))
        self.assertIn("--require-complete", command_for("tasks", args, batch))
        gate3 = command_for("gate3_review", args, batch)
        self.assertIn("scripts/review_active_rollouts.py", gate3)
        self.assertIn("--require-complete", gate3)
        gate4 = command_for("gate4_review", args, batch)
        self.assertIn("scripts/review_active_tasks.py", gate4)
        self.assertIn("--require-complete", gate4)


if __name__ == "__main__":
    unittest.main()
