"""Deployment must share persistent data without serving source or secrets."""
import json
import base64
import http.client
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from threading import Thread


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

    def test_proxy_origin_accepts_only_authenticated_same_site_json(self):
        from web.server import App

        class ProxyApp(App):
            public_origin = "https://lab.example:8443"
            auth_username = "test-user"
            auth_password = "test-password"

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), ProxyApp)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        auth = "Basic " + base64.b64encode(b"test-user:test-password").decode()

        def post(origin, authenticated=True, content_type="application/json"):
            connection = http.client.HTTPConnection(*server.server_address, timeout=5)
            headers = {"Host": "backend.internal:6006", "Origin": origin, "Content-Type": content_type}
            if authenticated:
                headers["Authorization"] = auth
            try:
                connection.request("POST", "/api/lab/records", body="{}", headers=headers)
                response = connection.getresponse()
                response.read()
                return response.status
            finally:
                connection.close()

        try:
            with patch("web.server.save_experiment_record", return_value={"id": "test"}) as save:
                self.assertEqual(post(ProxyApp.public_origin, authenticated=False), 401)
                self.assertEqual(post("https://untrusted.example"), 403)
                self.assertEqual(post("https://lab.example"), 403)
                self.assertEqual(post(ProxyApp.public_origin, content_type="text/plain"), 403)
                self.assertEqual(post(ProxyApp.public_origin), 200)
                save.assert_called_once_with({})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
