"""Read-only annotation visualizer for scenarios, rollouts, and tasks."""

import argparse
import base64
import hmac
import json
from pathlib import Path
import shutil
import sys
from urllib.parse import unquote, urlparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.quality_gates import SCENARIO_CHECKS, TASK_REVIEW_RATINGS
from evaluation.rollout_gate import HARD_REJECT_REASONS, QUALITY_DIMENSIONS
from scripts.scenario_docs import discover_scenario_paths

SCENARIO_DIR = ROOT / "configs" / "scenarios"
PIPELINE_DIR = ROOT / "build" / "pipeline_v2"
ACCEPTANCE_DIR = ROOT / "build" / "acceptance_v2"
STATIC_DIR = Path(__file__).resolve().parent / "static"
MEDIA_MANIFEST = ROOT / "media" / "talking_head" / "manifest.json"
SCREENING_REPORT = ROOT / "build" / "rollout_screening_v1" / "screening_report.json"
SCENARIO_REVIEW_TEMPLATE = ROOT / "reviews" / "scenario_review_template.json"
ENVIRONMENT_REVIEW_TEMPLATE = ROOT / "reviews" / "environment_evidence_template.json"
FORMAL_ENVIRONMENT_DIR = ROOT / "data" / "formal" / "environment"


def credentials_match(header, username, password):
    """Validate an HTTP Basic Authorization header without timing leaks."""
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
        supplied_username, supplied_password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(supplied_username, username) and hmac.compare_digest(
        supplied_password, password
    )


def read_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path):
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def annotation_contract():
    return {
        "format": "socialflux_annotation_ui_v1",
        "storage": "browser_local_draft",
        "scenario_checks": list(SCENARIO_CHECKS),
        "scenario_rating_scale": {
            "minimum": 1,
            "maximum": 5,
            "dimensions": [
                "social_plausibility",
                "tradeoff_quality",
                "history_necessity",
                "strategy_space",
                "motivation_coherence",
                "surface_originality",
            ],
        },
        "rollout_quality_dimensions": list(QUALITY_DIMENSIONS),
        "rollout_hard_reject_reasons": list(HARD_REJECT_REASONS),
        "rollout_screening": {
            "protocol": "SocialFlux Rollout Screening Protocol v1",
            "automatic_decisions": ["PASS", "REVIEW", "REJECT"],
            "final_per_scenario": 1,
            "human_audit_questions": [
                "automatic_decision_correct", "incorrect_dimensions", "error_reason",
                "issue_scope", "rule_or_prompt_revision",
            ],
            "winner_requires_human_confirmation": True,
        },
        "task_review_ratings": {
            task_type: sorted(ratings)
            for task_type, ratings in TASK_REVIEW_RATINGS.items()
        },
        "task_label_contracts": {
            "T1_state_tracking": {"value_scale": [0, 10], "requires_evidence": True},
            "T2_history_sensitive_merge": {
                "choices": ["A_higher", "similar", "B_higher", "cannot_determine"],
                "requires_evidence": True,
            },
            "T3_counterfactual_choice_effect": {
                "choices": ["decrease", "similar", "increase", "cannot_determine"],
                "horizons": ["immediate", "delayed"],
                "requires_evidence": True,
            },
        },
        "warning": (
            "Browser records are review drafts only. They are not signed Gate 1 "
            "approval or formal human ground truth."
        ),
    }


def load_scenario_records():
    return [(path, read_json(path)) for path in discover_scenario_paths(SCENARIO_DIR)]


def load_scenarios():
    return [scenario for _, scenario in load_scenario_records()]


def load_media_assets():
    manifest = read_json(MEDIA_MANIFEST, {}) or {}
    return manifest.get("assets", [])


def load_screening_report():
    return read_json(SCREENING_REPORT, {}) or {}


def _review_file_status(path):
    value = read_json(path, {}) or {}
    record = value.get("record", value)
    return {
        "exists": path.exists(),
        "human_attestation": record.get("human_attestation") is True,
        "reviewers": record.get("reviewers", []),
        "reviewed_at_utc": record.get("reviewed_at_utc", ""),
    }


def manual_review_catalog():
    """Expose every human-facing stage, including not-yet-generated packets."""
    screening = load_screening_report()
    summary = screening.get("summary", {})
    scenario_records = (read_json(SCENARIO_REVIEW_TEMPLATE, {}) or {}).get("records", [])
    media_count = len(load_media_assets())
    task_count = sum(len(load_instances(item["scenario_id"])) for item in load_scenarios())
    environment_files = {
        name: _review_file_status(FORMAL_ENVIRONMENT_DIR / name)
        for name in (
            "state_transition_agreement.json", "trajectory_plausibility.json",
            "history_intervention.json", "paraphrase_robustness.json",
            "local_counterfactual.json", "backbone_sensitivity.json",
        )
    }
    categories = [
        ["gate1_scenario", "Gate 1 · Scenario 与 S0/D0 冻结", len(scenario_records), 20,
         "pending_human", "人物、冲突、state、D0、视频阈值、来源原创化及姓名/时间/哈希。", "Scenario 情节"],
        ["gate2_environment", "Gate 2 · Environment Validity",
         sum(value["exists"] for value in environment_files.values()), 6,
         "pending_evidence", "E1–E5 真人实验；E6 是双 backbone 模型实验。", "本页证据状态"],
        ["gate3_rollout", "Gate 3 · Rollout Screening",
         summary.get("human_review_queue_count", 0), summary.get("human_review_queue_count", 0),
         "pending_human", "PASS/REVIEW/REJECT 审计、turn-ID 证据与每场景三选一比较。", "Rollout 筛选"],
        ["gate4_tasks", "Gate 4 · Task 1/2/3 逐题审核", task_count, task_count,
         "development_packets_only", "公开题面、来源、专属检查、人工标签和证据句；当前仍是开发包。", "Task 标注"],
        ["formal_gt", "Formal GT · 三人盲标与仲裁", 0, task_count * 3,
         "blocked_by_formal_tasks", "每个正式 task 三人独立盲标，分歧再具名仲裁。", "正式 Task 包生成后"],
        ["media", "Talking Head · 视频人工审核", media_count, media_count,
         "pending_human", "表情—状态、人物连续性、语音自然度和多模态信息效用。", "Scenario 情节"],
        ["filter_holdout", "筛选器校准与 Holdout", 0, 1,
         "pending_split_and_labels", "检查误收/误拒、人机一致性；holdout 通过后才 freeze。", "本页协议"],
        ["dataset_audit", "原创性、污染与公开信息泄漏", 20, 20,
         "pending_human", "影视只保留高层机制，无角色/台词/情节复制；公开输入不泄漏私有状态。", "Scenario 与原始材料"],
    ]
    return {
        "format": "socialflux_manual_review_catalog_v1",
        "categories": [
            dict(zip(("id", "title", "available", "required", "status", "description", "location"), item))
            for item in categories
        ],
        "environment_files": environment_files,
        "screening_summary": summary,
        "protocol_document": (ROOT / "docs" / "protocols" / "SocialFlux_Rollout_Screening_Protocol_v1.md").read_text(encoding="utf-8"),
        "warning": "未生成、未实名签署或仅有开发数据的项目明确保持 pending。",
    }


def _scenario_record(scenario_id):
    return next(
        (
            (path, scenario)
            for path, scenario in load_scenario_records()
            if scenario["scenario_id"] == scenario_id
        ),
        None,
    )


def load_instances(scenario_id):
    return read_jsonl(PIPELINE_DIR / scenario_id / "offline" / "instances.jsonl")

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
    screening = load_screening_report().get("scenarios", {}).get(scenario["scenario_id"], {})
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
        "task_count": sum(pipeline.get(key, 0) for key in ("t1", "t2", "t3")),
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
        "screening": {
            "candidate_count": screening.get("candidate_count", trajectory_count),
            "final_trajectory_count": 1 if screening.get("provisional_selected_id") else 0,
            "provisional_selected_id": screening.get("provisional_selected_id"),
            "selection_status": screening.get("selection_status", "not_generated"),
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
    screening_records = [
        item for item in load_screening_report().get("records", [])
        if item.get("scenario_id") == scenario_id and item.get("human_review_required")
    ]
    if screening_records:
        rollouts = []
        for item in sorted(screening_records, key=lambda value: (
            not value.get("provisional_selected", False),
            value.get("source_stage") != "active_candidate",
            value.get("automatic_decision") != "REVIEW",
            value.get("trajectory_id", ""),
        )):
            target = (ROOT / item["trajectory_path"]).resolve()
            if ROOT not in target.parents or not target.is_file():
                continue
            trajectory = read_json(target)
            if trajectory:
                trajectory["screening"] = item
                rollouts.append(trajectory)
        return rollouts
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
    task_review_path = source_path.parent / "rollouts" / "tasks.md"
    screening = load_screening_report()
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
        "task_review": (
            task_review_path.read_text(encoding="utf-8")
            if task_review_path.exists()
            and "T1/T2/T3 人工抽查包" in task_review_path.read_text(encoding="utf-8")
            else ""
        ),
        "rollouts": load_rollouts(scenario_id),
        "instances": load_instances(scenario_id),
        "task_source_selection": _pipeline_summary(scenario_id).get(
            "task_source_selection", {}
        ),
        "screening": screening.get("scenarios", {}).get(scenario_id, {}),
        "media_assets": [
            {
                **asset,
                "url": (
                    f"/media/{asset['asset_id']}?v="
                    f"{asset.get('video_sha256', 'pending')[:12]}"
                ),
            }
            for asset in load_media_assets()
            if asset.get("scenario_id") == scenario_id
        ],
    }


def api_payload(path):
    parts = [unquote(part) for part in path.strip("/").split("/") if part]
    records = load_scenario_records()
    catalog = read_json(SCENARIO_DIR / "manifest.json", {}) or {}
    if parts == ["api", "health"]:
        return {"ok": True, "scenario_count": len(records), "pipeline_version": "v2", "site_mode": "annotation_workbench"}
    if parts == ["api", "annotation-contract"]:
        return annotation_contract()
    if parts == ["api", "manual-review"]:
        return manual_review_catalog()
    if parts == ["api", "summary"]:
        return {
            "scenario_count": len(records),
            "source_counts": catalog.get("source_counts", {}),
            "scenarios": [scenario_summary(scenario, path) for path, scenario in records],
            "pipeline_manifest": read_json(PIPELINE_DIR / "manifest.json", {}) or {},
            "acceptance": acceptance_report(),
            "screening": load_screening_report().get("summary", {}),
            "manual_review": manual_review_catalog(),
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
    auth_username = None
    auth_password = None

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

    def authenticate(self):
        if self.auth_username is None or self.auth_password is None:
            return True
        if credentials_match(
            self.headers.get("Authorization"),
            self.auth_username,
            self.auth_password,
        ):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="SocialFlux", charset="UTF-8"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        if not self.authenticate():
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/media/"):
            asset_id = unquote(parsed.path.removeprefix("/media/"))
            asset = next(
                (item for item in load_media_assets() if item.get("asset_id") == asset_id),
                None,
            )
            if not asset or asset.get("status") != "generated":
                self.send_error(404, "media asset not found")
                return
            target = (ROOT / asset["video_path"]).resolve()
            asset_root = (ROOT / "media" / "talking_head" / "assets").resolve()
            if asset_root not in target.parents or not target.is_file():
                self.send_error(404, "media asset not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            with target.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile)
            return
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
    parser = argparse.ArgumentParser(description="Serve the SocialFlux annotation workbench")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--username", default="socialflux")
    parser.add_argument("--password-file", type=Path)
    args = parser.parse_args()
    if args.password_file:
        password = args.password_file.read_text(encoding="utf-8").strip()
        if not password:
            parser.error("--password-file must not be empty")
        App.auth_username = args.username
        App.auth_password = password
    elif args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("public binding requires --password-file")
    server = ThreadingHTTPServer((args.host, args.port), App)
    print(f"SocialFlux Annotation Studio: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
