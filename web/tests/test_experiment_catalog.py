import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.publish_experiment_hub import csv_text
from web.experiment_catalog import BANK, definitions, load_matrix


class ExperimentCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        bank = self.root / BANK
        bank.mkdir(parents=True)
        self.items = bank / "items.jsonl"
        self.items.write_text('{"private_state":"DO_NOT_EXPOSE"}\n')
        self.pairing = bank / "pairing_report.json"
        self.pairing.write_text(json.dumps(dict(items_sha256=hashlib.sha256(self.items.read_bytes()).hexdigest(),
                                                paired_by_task=dict(T1=3, T2=2, T3=1))))
        self.live = dict(offline=dict(tasks=dict(T1=4, T2=4, T3=4)), gates=[], t4_runs=[])

    def test_materials_are_not_scores_and_hashes_bind_media_to_bank(self):
        matrix = load_matrix(self.root, self.live, [])
        t1 = matrix["experiments"][0]
        self.assertEqual(t1["evidence"]["media_pairs"], 3)
        self.assertEqual(t1["evidence"]["missing_media"], 1)
        self.assertFalse(t1["evidence"]["independent_evaluation_registered"])
        self.assertNotIn("DO_NOT_EXPOSE", json.dumps(matrix))
        self.items.write_text("new version")
        stale = load_matrix(self.root, self.live, [])["experiments"][0]
        self.assertIsNone(stale["evidence"]["media_pairs"])
        self.assertFalse(stale["evidence"]["pairing_current"])

    def test_target_30_does_not_claim_30_completed(self):
        rows = load_matrix(self.root, self.live, [])["experiments"]
        ablations = [r for r in rows if r["group"] == "Gate2 补充消融"]
        self.assertEqual(len(ablations), 2)
        for row in ablations:
            self.assertEqual(row["target_scenarios"], 30)
            self.assertEqual(row["evidence_status"], "planned")
            self.assertEqual(row["evidence"], {})
            self.assertEqual(row["category"], "Gate 2")
        self.assertEqual(len(definitions()), 16)

    def test_gate_results_and_run_boundaries_survive_integration(self):
        self.live["gates"] = [dict(id="Gate 2", experiments=[dict(id="E3", evidence_present=True,
            human_attestation=False, status="pending", raw_partial=dict(records=46, screen_passed=43))])]
        self.live["t4_runs"] = [dict(id="run-a"), dict(id="run-b")]
        rows = {r["id"]: r for r in load_matrix(self.root, self.live, [])["experiments"]}
        self.assertEqual(rows["study-t4"]["run_ids"], ["run-a", "run-b"])
        e3 = rows["study-gate2-e3"]
        self.assertEqual(e3["evidence_status"], "machine_evidence")
        self.assertFalse(e3["evidence"]["human_attestation"])
        self.assertEqual(e3["evidence"]["status"], "pending")

    def test_malformed_pairing_keeps_plan_and_inventory_available(self):
        self.pairing.write_text("{")
        data = load_matrix(self.root, self.live, [])
        self.assertTrue(data["read_errors"])
        self.assertEqual(len(data["experiments"]), 16)
        self.assertTrue(any(f["status"] == "missing" for f in data["inventory"]))
        self.assertIsNone(data["experiments"][0]["evidence"]["media_pairs"])

    def test_export_escapes_formulas_and_preserves_multiline_cells(self):
        import csv
        import io
        data = csv_text([["=SUM(1)", "line1\nline2", None]])
        self.assertTrue(data.startswith("\ufeff"))
        self.assertEqual(next(csv.reader(io.StringIO(data.lstrip("\ufeff")))), ["'=SUM(1)", "line1\nline2", ""])


if __name__ == "__main__":
    unittest.main()
