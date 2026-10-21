"""Notebook persistence, concurrent editing and source/API boundaries."""
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from web import experiment_hub as hub
from web.server import App


class ExperimentHubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Path(self.temp.name) / "store"
        self.patch = patch.object(hub, "STORE", self.store)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def payload(self, **changes):
        return dict(title="测试实验", category="T4", status="planned", priority="P1",
                    owner="researcher", due_date="2026-10-25", hypothesis="待核验假设",
                    method="同来源配对比较", acceptance="完整数据与证据",
                    notes="", sources=["reports/experiments/example.md"],
                    metrics=[{"name": "score", "value": "N/A", "n": "0"}], **changes)

    def test_seed_only_once_and_user_edits_survive_reopening(self):
        initial = hub.records()
        self.assertEqual(len(initial), len(hub.SEEDS))
        updated = dict(initial[0], title="修改后的研究问题", status="blocked")
        saved = hub.save_record(updated)
        reopened = hub.records()
        self.assertEqual(len(reopened), len(initial))
        self.assertIn(saved, reopened)
        self.assertEqual(saved["revision"], 2)
        events = hub.history(saved["id"])
        self.assertEqual(events[0]["before"]["title"], initial[0]["title"])
        self.assertEqual(events[0]["after"]["status"], "blocked")

    def test_concurrent_update_accepts_only_one_revision(self):
        original = hub.save_record(self.payload())
        def update(status):
            try:
                return hub.save_record(dict(original, status=status))
            except hub.ConflictError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, ["running", "completed"]))
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(len(hub.history(original["id"])), 2)
        current = next(x for x in hub.records() if x["id"] == original["id"])
        self.assertEqual(current["revision"], 2)

    def test_failed_validation_leaves_record_and_history_unchanged(self):
        original = hub.save_record(self.payload())
        for change in ({"title": ""}, {"status": "passed"}, {"due_date": "2026-02-30"},
                       {"metrics": [{"name": ""}]}, {"sources": "not a list"},
                       {"category": "invalid"}, {"id": "../../secret"}):
            with self.assertRaises(ValueError):
                hub.save_record(dict(original, **change))
        self.assertEqual(len(hub.history(original["id"])), 1)
        self.assertIn(original, hub.records())

    def test_sources_deny_secrets_traversal_and_symlinks(self):
        root = Path(self.temp.name) / "project"
        reports = root / "reports/experiments"
        reports.mkdir(parents=True)
        report = reports / "2026-10-20_test.md"
        report.write_text("# 实验记录\n\n结果待人工核验。")
        secret = root / ".secrets/token.txt"
        secret.parent.mkdir()
        secret.write_text("SHOULD_NOT_ESCAPE")
        (reports / "linked.txt").symlink_to(secret)
        with patch.object(hub, "ROOT", root):
            catalog, errors = hub.report_catalog()
            self.assertEqual(len(catalog), 1)
            self.assertEqual(errors, [])
            self.assertEqual(catalog[0]["title"], "实验记录")
            document = hub.source_document("reports/experiments/2026-10-20_test.md")
            self.assertEqual(len(document["sha256"]), 64)
            for path in (".secrets/token.txt", "reports/experiments/../../.secrets/token.txt",
                         "reports/experiments/linked.txt", "/etc/passwd"):
                self.assertIsNone(hub.source_document(path), path)

    def test_partial_live_failure_keeps_notebook_available(self):
        with patch.object(hub, "load_experiment_status", side_effect=ValueError("partial JSON")):
            data = hub.load_hub()
        self.assertIsNone(data["live"])
        self.assertTrue(data["live_error"])
        self.assertEqual(len(data["records"]), len(hub.SEEDS))

    def test_http_conflicts_and_cross_site_writes(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), App)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        open_local = build_opener(ProxyHandler({})).open
        def post(payload, **headers):
            req = Request(base + "/api/lab/records", data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json", **headers}, method="POST")
            with open_local(req) as response:
                return json.load(response)
        saved = post(self.payload())
        current = post(dict(saved, status="running"))
        self.assertEqual(current["revision"], 2)
        with self.assertRaises(HTTPError) as conflict:
            post(saved)
        self.assertEqual(conflict.exception.code, 409)
        for headers in ({"Origin": "https://untrusted.example"}, {"Sec-Fetch-Site": "cross-site"},
                        {"Content-Type": "text/plain"}):
            with self.assertRaises(HTTPError) as cross_site:
                post(self.payload(), **headers)
            self.assertEqual(cross_site.exception.code, 403)
        with open_local(base + "/lab") as response:
            self.assertEqual(response.status, 200)
        with self.assertRaises(HTTPError) as secret:
            open_local(base + "/api/lab/source?path=.secrets/token.txt")
        self.assertEqual(secret.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
