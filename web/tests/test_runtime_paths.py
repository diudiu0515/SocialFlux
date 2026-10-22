"""Deployment must share persistent data without serving source or secrets."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class RuntimePathsTest(unittest.TestCase):
    def test_separate_data_root_is_used_by_every_lab_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "reports/experiments/example.md"
            report.parent.mkdir(parents=True)
            report.write_text("persistent report")
            (root / ".secrets").mkdir()
            (root / ".secrets/password").write_text("not public")
            source = """
import json
from web import server, experiment_hub, human_gt, gate2_human, offline_review, live_rollouts, annotation_sessions
from web.runtime_paths import CODE_ROOT
modules = [server, experiment_hub, human_gt, gate2_human, offline_review, live_rollouts, annotation_sessions]
assert all(module.ROOT == server.ROOT for module in modules)
assert experiment_hub.source_document('reports/experiments/example.md')['content'] == 'persistent report'
assert experiment_hub.source_document('.secrets/password') is None
assert server.STATIC_DIR == CODE_ROOT / 'web/static'
assert experiment_hub.STORE == server.ROOT / 'data/experiment_hub'
assert human_gt.STORE.is_relative_to(server.ROOT)
print(json.dumps({'root': str(server.ROOT), 'code': str(CODE_ROOT)}))
"""
            result = subprocess.run([sys.executable, "-c", source], check=True,
                                    capture_output=True, text=True,
                                    env={**os.environ, "SOCIALFLUX_DATA_ROOT": directory})
            values = json.loads(result.stdout)
            self.assertEqual(values["root"], str(root.resolve()))
            self.assertNotEqual(values["root"], values["code"])

    def test_missing_data_root_fails_instead_of_creating_empty_database(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-c", "import web.runtime_paths"],
                                    capture_output=True, text=True,
                                    env={**os.environ, "SOCIALFLUX_DATA_ROOT": directory + "/missing"})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("existing project data directory", result.stderr)


if __name__ == "__main__":
    unittest.main()
