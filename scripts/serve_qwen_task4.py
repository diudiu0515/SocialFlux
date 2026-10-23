#!/usr/bin/env python3
"""Local Task4 environment API; the Qwen model API must already be running."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import signal
import sys
import threading
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.qwen_task4 import DEFAULT_CONFIG, QwenTask4EnvironmentFactory, digest, load_config
from environment.qwen_task4_session import QwenTask4Session, SessionConflict


class Task4Server(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, port, config_path, catalog, output):
        self.config_path = Path(config_path).resolve()
        self.config = load_config(self.config_path)
        self.scenarios = {}
        for sid, entry in json.loads(Path(catalog).read_text())["scenarios"].items():
            path = Path(entry["path"])
            if digest(path) != entry["sha256"]:
                raise ValueError("Scenario checksum mismatch: " + sid)
            scenario = json.loads(path.read_text())
            if scenario["scenario_id"] != sid:
                raise ValueError("Scenario ID mismatch: " + sid)
            self.scenarios[sid] = scenario
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.sessions = {}
        self.registry_lock = threading.Lock()
        self.generation_slot = threading.Lock()
        super().__init__(("127.0.0.1", port), Handler)


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, value):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            endpoint = self.server.config["environment"]["provider"]["endpoint"]
            try:
                with build_opener(ProxyHandler({})).open(endpoint.removesuffix("/v1/chat/completions") + "/health", timeout=3) as response:
                    healthy = response.status == 200
            except Exception:
                healthy = False
            return self.reply(200 if healthy else 503, {
                "ready": healthy, "profile": self.server.config["profile"],
                "model": self.server.config["model"], "observation_condition": "text_only",
                "reward_status": "unconfigured",
            })
        if self.path == "/scenarios":
            return self.reply(200, {"scenario_ids": sorted(self.server.scenarios)})
        parts = self.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "sessions":
            session = self.server.sessions.get(parts[1])
            if session:
                with session.lock:
                    return self.reply(200, session.result())
        self.reply(404, {"error": "not_found"})

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536:
                return self.reply(400, {"error": "invalid_request_size"})
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("JSON object required")
            if self.path == "/sessions":
                if set(data) != {"scenario_id"} or data["scenario_id"] not in self.server.scenarios:
                    return self.reply(400, {"error": "unknown_scenario"})
                with self.server.registry_lock:
                    if len(self.server.sessions) >= 64:
                        return self.reply(409, {"error": "session_limit"})
                    factory = QwenTask4EnvironmentFactory(
                        self.server.scenarios[data["scenario_id"]], self.server.config_path)
                    session = QwenTask4Session(factory, self.server.output)
                    self.server.sessions[session.episode_id] = session
                return self.reply(201, session.result())
            parts = self.path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "step":
                session = self.server.sessions.get(parts[1])
                if not session:
                    return self.reply(404, {"error": "not_found"})
                if set(data) != {"text", "expected_turn_id"}:
                    return self.reply(400, {"error": "text_and_expected_turn_id_required"})
                if not self.server.generation_slot.acquire(blocking=False):
                    return self.reply(503, {"error": "generation_busy"})
                try:
                    result = session.step(data["text"], expected_turn_id=data["expected_turn_id"])
                finally:
                    self.server.generation_slot.release()
                return self.reply(502 if result["failed"] else 200, result)
            self.reply(404, {"error": "not_found"})
        except SessionConflict:
            self.reply(409, {"error": "episode_inactive_or_stale_turn"})
        except (ValueError, TypeError, KeyError):
            self.reply(400, {"error": "invalid_request"})
        except Exception:
            self.reply(500, {"error": "internal_error"})

    def do_DELETE(self):
        parts = self.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "sessions":
            with self.server.registry_lock:
                session = self.server.sessions.get(parts[1])
                if session:
                    # Keep all private files when releasing the in-memory slot.
                    with session.lock:
                        session.failed = True
                        from shared.artifacts import atomic_json
                        atomic_json(session.output / "client_closed.json", {"closed": True})
                        del self.server.sessions[parts[1]]
                    return self.reply(200, {"closed": True})
        self.reply(404, {"error": "not_found"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--catalog", type=Path, required=True,
                        help="Frozen scenario ID -> path/sha256 catalog; never an arbitrary client-supplied file")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()
    server = Task4Server(args.port, args.config, args.catalog, args.output)
    def shutdown(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print(json.dumps({"listening": f"http://127.0.0.1:{server.server_port}",
                      "scenario_count": len(server.scenarios), "profile": server.config["profile"]}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
