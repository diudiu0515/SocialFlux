"""Read-only visualizer for canonical scenarios and natural model trajectories."""

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
PIPELINE_DIR = ROOT / "build" / "pipeline_v2"
ACCEPTANCE_DIR = ROOT / "build" / "acceptance_v2"
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
        (
            (path, scenario)
            for path, scenario in load_scenario_records()
            if scenario["scenario_id"] == scenario_id
        ),
        None,
    )


def _pipeline_summary(scenario_id):
    return read_json(PIPELINE_DIR / scenario_id / "pipeline_manifest.json", {}) or {}


def scenario_summary(scenario, source_path):
    pipeline = _pipeline_summary(scenario["scenario_id"])
    bundle = source_path.parent
    rollout_manifest = read_json(bundle / "rollouts" / "manifest.json", {}) or {}
    local_rollout_ready = (
        rollout_manifest.get("config", {}).get("origin")
        == "free_form_model_interaction"
    )
    trajectory_count = pipeline.get(
        "trajectory_count",
        rollout_manifest.get("trajectory_count", 0) if local_rollout_ready else 0,
    )
    return {
        "scenario_id": scenario["scenario_id"],
        "title": scenario["title"],
        "mechanism": scenario["mechanism"],
        "source_type": scenario["source"]["type"],
        "quality_gate": scenario["construction_status"]["quality_gate"],
        "initial_state_status": scenario["construction_status"]["initial_state"],
        "background": scenario["background"],
        "persona": scenario["environment_agent"].get("persona", {}),
        "selected_state_variables": scenario.get("selected_state_variables", {}),
        "trigger_count": len(scenario.get("video_triggers", [])),
        "max_turns": scenario["max_turns"],
        "scenario_bundle": bundle.relative_to(ROOT).as_posix(),
        "rollout_bundle": (bundle / "rollouts").relative_to(ROOT).as_posix(),
        "pipeline": {
            "trajectory_count": trajectory_count,
            "t1": pipeline.get("t1", 0),
            "t2": pipeline.get("t2", 0),
            "t3": pipeline.get("t3", 0),
            "available": (
                pipeline.get("trajectory_origin") == "free_form_model_interaction"
                or local_rollout_ready
            ),
        },
    }


def acceptance_report():
    return read_json(ACCEPTANCE_DIR / "acceptance_report.json", {
        "criteria": [],
        "gate": {
            "automated_artifacts_ready": False,
            "research_acceptance": False,
        },
    })


def load_rollouts(scenario_id):
    record = _scenario_record(scenario_id)
    if record is None:
        return []
    rollout_dir = record[0].parent / "rollouts"
    manifest = read_json(rollout_dir / "manifest.json", {}) or {}
    if manifest.get("config", {}).get("origin") != "free_form_model_interaction":
        return []
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
    dialogue_path = source_path.parent / "rollouts" / "dialogues.md"
    return {
        "summary": scenario_summary(scenario, source_path),
        "scenario": scenario,
        "documentation": source_path.with_suffix(".md").read_text(encoding="utf-8"),
        "rollout_dialogues": (
            dialogue_path.read_text(encoding="utf-8")
            if dialogue_path.exists()
            and "Free-form Rollout Dialogues" in dialogue_path.read_text(encoding="utf-8")
            else ""
        ),
        "rollouts": load_rollouts(scenario_id),
    }


def api_payload(path):
    parts = [unquote(part) for part in path.strip("/").split("/") if part]
    records = load_scenario_records()
    catalog = read_json(SCENARIO_DIR / "manifest.json", {}) or {}
    if parts == ["api", "health"]:
        return {"ok": True, "scenario_count": len(records), "pipeline_version": "v2"}
    if parts == ["api", "summary"]:
        return {
            "scenario_count": len(records),
            "source_counts": catalog.get("source_counts", {}),
            "scenarios": [scenario_summary(scenario, path) for path, scenario in records],
            "pipeline_manifest": read_json(PIPELINE_DIR / "manifest.json", {}) or {},
            "acceptance": acceptance_report(),
        }
    if parts == ["api", "scenarios"]:
        return {
            "scenarios": [
                scenario_summary(scenario, path)
                for path, scenario in records
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
            self.send_json(payload if payload is not None else {"error": "not found"},
                           200 if payload is not None else 404)
            return
        if parsed.path in ("/", ""):
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
