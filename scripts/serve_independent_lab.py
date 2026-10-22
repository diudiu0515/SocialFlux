"""Serve Lab on an independent host with a persistent disk and Pages frontend."""
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import urlparse

CODE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_ROOT))


def initialize_data_root(root):
    root.mkdir(parents=True, exist_ok=True)
    # Seed repository documents once. Restored data and user edits win thereafter.
    for name in ["configs", "docs", "reports", "reviews", "tasks/examples"]:
        source, destination = CODE_ROOT / name, root / name
        if source.is_dir() and not destination.exists():
            shutil.copytree(source, destination)
    for name in ["DESIGN_CONTRACT.md", "PROJECT_PROGRESS.md", "self_check.md"]:
        if (CODE_ROOT / name).is_file() and not (root / name).exists():
            shutil.copy2(CODE_ROOT / name, root / name)


def handler_type(frontend_origin, root, username, password):
    from web.server import App

    class HostedLab(App):
        auth_username = username
        auth_password = password
        trusted_api_origins = frozenset([frontend_origin])

        def end_headers(self):
            if self.headers.get("Origin") == frontend_origin:
                self.send_header("Access-Control-Allow-Origin", frontend_origin)
                self.send_header("Vary", "Origin")
            super().end_headers()

        def do_OPTIONS(self):
            origin = self.headers.get("Origin")
            method = self.headers.get("Access-Control-Request-Method")
            requested = {x.strip().lower() for x in self.headers.get("Access-Control-Request-Headers", "").split(",") if x.strip()}
            if (origin != frontend_origin or method not in {"GET", "POST"}
                    or not urlparse(self.path).path.startswith("/api/lab")
                    or not requested <= {"authorization", "content-type"}):
                self.send_json({"error": "不允许此跨站请求"}, 403)
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def data_ready(self):
            return (root / "lab-data-ready.json").is_file()

        def do_GET(self):
            if urlparse(self.path).path == "/healthz":
                self.send_json({"status": "ok", "data_ready": self.data_ready()})
                return
            if self.path.startswith("/api/") and not self.data_ready():
                if self.authenticate():
                    self.send_json({"error": "实验数据尚未迁移完成，请稍后重试。"}, 503)
                return
            if self.path == "/":
                self.path = "/lab"
            super().do_GET()

        def do_POST(self):
            if not self.data_ready():
                if self.authenticate():
                    self.send_json({"error": "实验数据尚未迁移完成，暂不能写入。"}, 503)
                return
            super().do_POST()

    return HostedLab


def main():
    password = os.environ.get("LAB_PASSWORD", "")
    origin = os.environ.get("LAB_FRONTEND_ORIGIN", "")
    parsed = urlparse(origin)
    if (len(password) < 20 or parsed.scheme != "https" or not parsed.hostname
            or parsed.path or parsed.query or parsed.fragment or parsed.username):
        raise SystemExit("Set LAB_PASSWORD (20+ characters) and an exact HTTPS LAB_FRONTEND_ORIGIN")
    root = Path(os.environ.get("SOCIALFLUX_DATA_ROOT", "/var/data/lab")).resolve()
    if root == CODE_ROOT:
        raise SystemExit("SOCIALFLUX_DATA_ROOT must be a separate persistent directory")
    initialize_data_root(root)
    os.environ["SOCIALFLUX_DATA_ROOT"] = str(root)
    from http.server import ThreadingHTTPServer
    handler = handler_type(origin, root, os.environ.get("LAB_USERNAME", "socialflux"), password)
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), handler)
    print("Independent Lab backend ready; research data readiness is reported by /healthz", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
