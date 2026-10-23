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

    def test_current_bank_replaces_legacy_counts_and_paper_sources(self):
        from web.experiment_tables import build_paper_tables
        bank = 'data/offline_annotation400_en_20261022'
        directory = self.root / bank
        directory.mkdir(parents=True)
        raw = b'current questions\n'
        (directory / 'items.jsonl').write_bytes(raw)
        (directory / 'pairing_report.json').write_text(json.dumps({
            'items_sha256': hashlib.sha256(raw).hexdigest()}))
        self.live['dataset_counts'] = {'offline': {'bank_path': bank, 'release': 'current',
            'tasks': {'T1': {'total': 150, 'pairs': 150}, 'T2': {'total': 100, 'pairs': 100},
                      'T3': {'total': 150, 'pairs': 150}}}}
        matrix = load_matrix(self.root, self.live, [])
        self.assertEqual([r['evidence']['items'] for r in matrix['experiments'][:3]], [150, 100, 150])
        self.assertEqual([r['evidence']['media_pairs'] for r in matrix['experiments'][:3]], [150, 100, 150])
        table = next(t for t in build_paper_tables(self.live, matrix) if t['id'] == 'offline-results')
        self.assertIn(bank, table['exports']['markdown'])
        self.assertNotIn(BANK, table['exports']['markdown'])
        (directory / 'items.jsonl').write_text('changed after inventory was loaded')
        stale = load_matrix(self.root, self.live, [])['experiments'][0]
        self.assertIsNone(stale['evidence']['media_pairs'])
        self.assertEqual(stale['evidence_status'], 'unavailable')

    def test_unreadable_current_bank_does_not_fall_back_to_old_counts(self):
        self.live['dataset_counts'] = {'offline': None, 'read_errors': [
            {'path': 'data/current/manifest.json', 'error': 'AnnotationBankHashMismatch'}]}
        matrix = load_matrix(self.root, self.live, [])
        self.assertIsNone(matrix['experiments'][0]['evidence']['items'])
        self.assertIsNone(matrix['experiments'][0]['evidence']['media_pairs'])
        self.assertTrue(matrix['read_errors'])

    def test_latest_t4_recorded_slots_are_not_all_successful(self):
        self.live['t4_runs'] = [dict(id='current', kind='persistent_pair_recovery',
            reported_status='needs_repair', process_alive=False, planned_slots=164,
            finished_slots=164, models={
                'gpt': {'status_counts': {'completed': 77, 'failed': 5}, 'matched_scenarios': 37},
                'claude': {'status_counts': {'completed': 73, 'failed': 9}, 'matched_scenarios': 33}})]
        row = next(r for r in load_matrix(self.root, self.live, [])['experiments'] if r['id'] == 'study-t4')
        self.assertEqual(row['evidence']['completed'], 150)
        self.assertEqual(row['evidence']['failed'], 14)
        self.assertIn('成功 150/164', row['evidence_summary'])
        self.assertIn('待修复后续跑', row['evidence_summary'])

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
