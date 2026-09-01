"""Read-only scenario and pipeline artifact visualizer."""

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scenario_docs import discover_scenario_paths
SCENARIO_DIR = ROOT / "configs" / "scenarios"
PIPELINE_DIR = ROOT / "build" / "pipeline_v1"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def read_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_scenario_records():
    return [(path, read_json(path)) for path in discover_scenario_paths(SCENARIO_DIR)]


def load_scenarios():
    return [scenario for _, scenario in load_scenario_records()]


def _scenario_record(scenario_id):
    return next(
        ((path, scenario) for path, scenario in load_scenario_records()
         if scenario["scenario_id"] == scenario_id),
        None,
    )


def _pipeline_summary(scenario_id):
    return read_json(PIPELINE_DIR / scenario_id / "pipeline_manifest.json", {}) or {}


def scenario_summary(scenario, source_path=None):
    scenario_id = scenario["scenario_id"]
    pipeline = _pipeline_summary(scenario_id)
    bundle = source_path.parent if source_path else SCENARIO_DIR / scenario_id.lower()
    return {
        "scenario_id": scenario_id,
        "title": scenario.get("title", scenario_id),
        "mechanism": scenario.get("mechanism", ""),
        "background": scenario.get("background", ""),
        "persona": scenario.get("environment_agent", {}).get("persona", {}),
        "selected_state_variables": scenario.get("selected_state_variables", {}),
        "action_ids": list(scenario.get("action_effects", {})),
        "trigger_count": len(scenario.get("video_triggers", [])),
        "max_turns": scenario.get("max_turns", 20),
        "scenario_bundle": bundle.relative_to(ROOT).as_posix(),
        "rollout_bundle": (bundle / "rollouts").relative_to(ROOT).as_posix(),
        "pipeline": {
            "trajectory_count": pipeline.get("trajectory_count", 0),
            "t1": pipeline.get("t1", 0),
            "t2": pipeline.get("t2", 0),
            "t3": pipeline.get("t3", 0),
            "available": bool(pipeline),
        },
    }


def acceptance_report():
    return read_json(PIPELINE_DIR / "acceptance_report.json", {
        "criteria": [],
        "gate": {"automated_passed": False, "research_acceptance": False},
    })


def load_rollouts(scenario_id):
    record = _scenario_record(scenario_id)
    if record is None:
        return []
    rollout_dir = record[0].parent / "rollouts"
    manifest = read_json(rollout_dir / "manifest.json", {}) or {}
    rollouts = []
    for trajectory_id in manifest.get("trajectory_ids", []):
        trajectory = read_json(rollout_dir / f"{trajectory_id}.json")
        if trajectory:
            rollouts.append(trajectory)
    return rollouts


def scenario_detail(scenario_id):
    record = _scenario_record(scenario_id)
    if record is None:
        return None
    source_path, scenario = record
    report = acceptance_report()
    acceptance = next((item for item in report.get("criteria", [])
                       if item.get("criterion") == "5. Full Trajectory Plausibility"), {})
    scenario_review = next((item for item in acceptance.get("scenarios", [])
                            if item.get("scenario_id") == scenario_id), {})
    dialogue_path = source_path.parent / "rollouts" / "dialogues.md"
    return {
        "summary": scenario_summary(scenario, source_path),
        "scenario": scenario,
        "documentation": source_path.with_suffix(".md").read_text(encoding="utf-8"),
        "rollout_dialogues": (
            dialogue_path.read_text(encoding="utf-8") if dialogue_path.exists() else ""
        ),
        "rollouts": load_rollouts(scenario_id),
        "acceptance_review": scenario_review,
    }


def api_payload(path):
    parts = [unquote(part) for part in path.strip("/").split("/") if part]
    if parts == ["api", "health"]:
        return {"ok": True, "scenario_count": len(load_scenarios())}
    if parts == ["api", "summary"]:
        records = load_scenario_records()
        manifest = read_json(PIPELINE_DIR / "manifest.json", {}) or {}
        return {
            "scenario_count": len(records),
            "scenarios": [scenario_summary(scenario, path) for path, scenario in records],
            "pipeline_manifest": manifest,
            "acceptance": acceptance_report(),
        }
    if parts == ["api", "scenarios"]:
        return {
            "scenarios": [
                scenario_summary(scenario, path)
                for path, scenario in load_scenario_records()
            ]
        }
    if len(parts) == 3 and parts[:2] == ["api", "scenarios"]:
        return scenario_detail(parts[2])
    return None


class App(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            payload = api_payload(parsed.path)
            if payload is None:
                self.send_json({"error": "not found"}, 404)
            else:
                self.send_json(payload)
            return
        if parsed.path == "/" or parsed.path == "":
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, format, *args):
        print("[web] " + format % args)


def main():
    parser = argparse.ArgumentParser(description="Serve the SocialFlux scenario visualizer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), App)
    print(f"SocialFlux Scenario Visualizer: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
