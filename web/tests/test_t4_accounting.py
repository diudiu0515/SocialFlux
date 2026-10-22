import json
import unittest

from web.experiment_tables import build_paper_tables
from web.t4_accounting import execution_accounting


class T4AccountingTests(unittest.TestCase):
    def test_plan_denominator_preserves_failures_unsupported_and_unrecorded(self):
        plan = {"scenario_sha256": {name: "hash" for name in "ABCDE"}}
        def row(scene, status, deliveries=0):
            return dict(scenario_id=scene, model_id="model", condition="text_video",
                        transport="video_frames", status=status, video_delivery_count=deliveries)
        rows = [row("A", "completed", 1), row("B", "failed"),
                row("C", "unsupported_video_input"), row("D", "completed_without_video_exposure")]
        audit = execution_accounting(plan, rows, ["model"])
        text, video = audit
        self.assertEqual(text["unrecorded"], 5)
        self.assertEqual(video["planned"], 5)
        self.assertEqual(video["recorded"], 4)
        self.assertEqual(video["completed"], 2)
        self.assertEqual(video["valid_scored"], 1)
        self.assertEqual(video["completion_rate"], .4)
        self.assertEqual([video[k] for k in ("failed", "unsupported", "missing_video", "unrecorded")], [1, 1, 1, 1])
        tables = build_paper_tables({"t4_runs": [dict(id="fixture", models={}, execution_accounting=audit)]}, {"experiments": []})
        table = next(t for t in tables if t["id"] == "fixture-execution")
        self.assertEqual(table["rows"][1][2], "视频帧")
        self.assertEqual(table["rows"][1][7], "40.00%")
        self.assertIn("不跨目录求和", table["exports"]["markdown"])

    def test_inherited_duplicates_count_once_and_conflicts_are_not_selected(self):
        plan = {"scenario_sha256": {"A": "hash", "B": "hash"}}
        original = dict(scenario_id="A", model_id="model", condition="text_only",
                        status="completed", messages="PRIVATE", api_key="SECRET")
        failed = dict(original, scenario_id="B", status="failed")
        rows = [original, dict(original), failed, dict(failed, status="completed")]
        text = execution_accounting(plan, rows, ["model"])[0]
        self.assertEqual(text["recorded"], 2)
        self.assertEqual(text["completed"], 1)
        self.assertEqual(text["completion_rate"], .5)
        self.assertEqual(text["duplicate_records"], 2)
        self.assertEqual(text["conflicting_slots"], 1)
        self.assertNotIn("PRIVATE", json.dumps(text))
        self.assertNotIn("SECRET", json.dumps(text))

    def test_missing_plan_does_not_infer_a_denominator_from_successes(self):
        self.assertEqual(execution_accounting({}, [], ["model"]), [])
        self.assertEqual(execution_accounting({"scenario_sha256": {}}, {}, ["model"]), [])


if __name__ == "__main__":
    unittest.main()
