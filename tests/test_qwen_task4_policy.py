import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_qwen_task4_policy import checked_run, sha


class FrozenPolicyRunTests(unittest.TestCase):
    def test_reject_modified_code_catalog_and_scenario_before_policy_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "runtime").mkdir()
            code = run / "runtime/module.py"
            code.write_text("pass\n")
            scenario = run / "scenario.json"
            scenario.write_text(json.dumps({"scenario_id": "test"}))
            catalog = run / "catalog.json"
            catalog.write_text(json.dumps({"scenarios": {"test": {
                "path": str(scenario), "sha256": sha(scenario)}}}))
            (run / "manifest.json").write_text(json.dumps({
                "runtime_sha256": {"module.py": sha(code)},
                "scenario_catalog_sha256": sha(catalog)}))
            self.assertEqual(checked_run(run, "test")[1]["scenario_id"], "test")
            for path in (code, catalog, scenario):
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, "changed"):
                    checked_run(run, "test")
                path.write_bytes(original)
            with self.assertRaises(KeyError):
                checked_run(run, "unknown")


if __name__ == "__main__":
    unittest.main()
