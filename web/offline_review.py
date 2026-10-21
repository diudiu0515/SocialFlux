"""Read-only, hash-bound review of the existing offline choice bank.

Public questions and author references have separate endpoints. Browser drafts
never promote proposals to ground truth or change source admission.
"""

from collections import Counter
from copy import deepcopy
from functools import lru_cache
from contextvars import ContextVar
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from environment.state_ontology import STATE_VARIABLE_ONTOLOGY
from tasks.offline_choice import FAMILIES, public_instance, visible_evidence

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "data/offline_t1_t3_dev60"
_bank_override = ContextVar('offline_review_bank',default=None)
BANK_PATHS = {'dev60':'data/offline_t1_t3_dev60','gpt50-t1-t3':'data/offline_gpt50_t1_t3','design-v2':'tasks/examples/offline_design_v2', 'scenarios-v2':'tasks/examples/offline_scenarios_v2'}


def bank_path():
    return _bank_override.get() or BANK
VIDEO_ROOT = ROOT / "data/gpt50/experiment/multimodal_delivery_v1/online_multimodal/assets"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def item_digest(item):
    return digest(json.dumps(item, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode())


def load_bank():
    path = bank_path() / "items.jsonl"
    if not path.is_file():
        return [], None
    raw = path.read_bytes()
    items = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if len({item["instance_id"] for item in items}) != len(items):
        raise ValueError("duplicate offline instance ID")
    return items, digest(raw)


def read_json(path, fallback=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else fallback


def active_generation_jobs():
    """A stale 'running' file alone is not evidence of a live worker."""
    pids=set()
    for path in (bank_path()/'runs').glob('*.json'):
        row=read_json(path,{})
        pid=row.get('pid')
        if row.get('status')!='running' or not isinstance(pid,int) or pid<1:
            continue
        try:
            command=Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0',b' ')
        except OSError:
            continue
        if b'pipeline offline-build' in command and bank_path().name.encode() in command:
            pids.add(pid)
    return len(pids)


@lru_cache(maxsize=2)
def _migration_index(path, modified_ns, size):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {row["instance_id"]: row for row in data.get("items", []) + data.get("pending_items", [])}


def migration_review(item):
    path = ROOT / "tasks/examples/offline_legacy_api_audit/results.json"
    if not path.is_file():
        return None
    stat = path.stat()
    row = _migration_index(str(path), stat.st_mtime_ns, stat.st_size).get(item["instance_id"])
    # Audit conclusions cannot survive edits to the frozen source question.
    return row if row and row.get("item_sha256") == item_digest(item) else None


def metadata(item):
    author = item["authoring"]
    audit = migration_review(item)
    analysis = item.get("analysis") or (audit or {}).get("review", {})
    return {
        "instance_id": item["instance_id"], "task": item["task"],
        "subtype": item["subtype"], "scenario_id": item["story_id"],
        "trajectory_id": item["metadata"]["source_trajectory_id"],
        "pair_id": item.get("pair_id"), "item_sha256": item_digest(item),
        "question": item["question"],
        "character_name": item["input"]["target_character"].get("name", ""),
        "families": sorted({FAMILIES[p.split(".")[0]] for p in
                            item["target_spec"]["target_state_ids"]}),
        "combination": len(next(iter(author["option_variable_map"].values()))) > 1,
        "replay_status": author.get("replay_status", "pending"),
        "label_status": item["label_status"],
        "source_review_status": author.get('construction_source',{}).get('source_review_status'),
        "primary_capability": analysis.get("primary_capability"),
        "design_difficulty": analysis.get("design_difficulty"),
        "migration_level": (audit or {}).get("migration_level"),
        "migration_status": (audit or {}).get("migration_status"),
        "source_origin": author.get('construction_source',{}).get('origin'),
        "oracle_status": author.get("oracle_reference", {}).get("status"),
    }


def checked_source(relative, expected):
    """Only load an explicitly hash-bound artifact inside this repository."""
    path = (ROOT / relative).resolve()
    if ROOT.resolve() not in path.parents or not path.is_file() or not expected:
        return None
    raw = path.read_bytes()
    if digest(raw) != expected:
        return None
    return json.loads(raw)


@lru_cache(maxsize=2)
def _paired_items(raw):
    # Key on contents: this workspace can retain identical file mtimes on writes.
    return {item["instance_id"]: item for line in raw.splitlines()
            if line.strip() for item in [json.loads(line)]}


def pair_matches(item):
    path = bank_path() / "paired.items.jsonl"
    if not path.is_file():
        return False
    pairs = _paired_items(path.read_bytes())
    for suffix, modality in (("", "text"), ("-video", "text+video")):
        paired = deepcopy(pairs.get(item["instance_id"] + suffix))
        if not paired or paired["modality"] != modality:
            return False
        if paired["metadata"].pop("modality_pair_id", None) != item["instance_id"]:
            return False
        paired["instance_id"], paired["modality"] = item["instance_id"], item["modality"]
        for key in ("media_manifest", "media_human_review", "matched_assets"):
            paired["authoring"].pop(key, None)
        if paired != item:
            return False
    return True


def media_records(item):
    if not pair_matches(item):
        return []
    records = read_json(bank_path() / "media.json", {}).get(item["instance_id"] + "-video", [])
    paired = _paired_items((bank_path() / "paired.items.jsonl").read_bytes())[item["instance_id"] + "-video"]
    bindings = paired["authoring"].get("matched_assets")
    if bindings is not None and bindings != [
            {"sha256": r["sha256"], "evidence_ids": r.get("evidence_ids", [])} for r in records]:
        return []
    if any(not r.get("evidence_ids") or not set(r["evidence_ids"]) <= visible_evidence(item) for r in records):
        return []
    result = []
    for record in records:
        path = (ROOT / record["path"]).resolve()
        available = path.parent == VIDEO_ROOT.resolve() and path.is_file()
        if available:
            available = digest(path.read_bytes()) == record["sha256"]
        result.append({
            "asset_id": record["source_asset_id"], "sha256": record["sha256"],
            "evidence_ids": record.get("evidence_ids", []),
            "human_review": record.get("human_review", "pending"),
            "response_neutral": record.get("response_neutral", False),
            "available": available,
            "url": "/online-video/gpt/" + quote(path.name) if available else None,
        })
    return result


def media_pairing_report(bank_sha):
    report = read_json(bank_path() / "pairing_report.json", {})
    path = bank_path() / "media.json"
    if (report.get("items_sha256") != bank_sha or not path.is_file()
            or report.get("media_sha256") != digest(path.read_bytes())):
        return {}
    return report


def media_coverage(item, records):
    covered = {e for record in records if record["available"] for e in record["evidence_ids"]}
    if item["task"] == "T2":
        required = {t["turn_id"] for key in ("history_a", "history_b") for t in item["input"][key][:-1]}
        required.add(item["input"]["shared_ending"]["turn_id"])
    else:
        required = {t["turn_id"] for t in item["input"]["history"]}
    return {"covered_evidence_ids": sorted(covered),
            "uncovered_evidence_ids": sorted(required - covered),
            "status": "missing" if not covered else "partial" if required - covered else "complete"}


def _state_values(state, variables):
    result = {}
    for variable in variables:
        family, name = variable.split(".")
        result[variable] = state.get(family, {}).get(name)
    return result


def _review_turn(turn, variables):
    """No raw API requests, provider audits, memories or runtime snapshots."""
    return {**{k: turn.get(k) for k in (
        "turn_id", "policy_action", "environment_response", "observable_expression",
        "environment_response_ledger_events", "trigger_events")},
        "state_before": _state_values(turn.get("state_before", {}), variables),
        "state_after": _state_values(turn.get("state_after_public_events", turn.get("state_after", {})), variables)}


def author_reference(item, bank_sha):
    author = item["authoring"]
    source = author["construction_source"]
    variables = item["target_spec"]["target_state_ids"]
    scenario = checked_source(source["scenario_path"], source.get("scenario_sha256")) if source.get("scenario_path") else None
    trajectory = checked_source(source["trajectory_path"], source.get("trajectory_sha256")) if source.get("trajectory_path") else None
    checks = {"scenario": scenario is not None, "trajectory": trajectory is not None}
    reference = {
        "instance_id": item["instance_id"], "bank_sha256": bank_sha,
        "item_sha256": item_digest(item),
        "authoring": author, "ground_truth": item.get("ground_truth"),
        "migration_review": migration_review(item),
        "target_spec": item["target_spec"], "analysis": item.get("analysis"), "source_checks": checks,
        "scenario": scenario, "state_semantics": {
            variable: STATE_VARIABLE_ONTOLOGY[variable] for variable in variables},
        "source_turns": [], "replays": [],
    }
    if source.get('prefix_intervention'):
        binding=source['prefix_intervention']
        record=checked_source(binding['path'],binding.get('sha256'))
        checks['prefix_intervention']=record is not None
        reference['prefix_intervention']=record
    # The source history shown in review matches the question's own cutoff.
    if trajectory:
        visible = visible_evidence(item)
        reference["source_turns"] = [_review_turn(t, variables) for t in trajectory.get("turns", [])
                                     if t["turn_id"] in visible or "A:" + t["turn_id"] in visible]
        if item["task"] == "T2":
            # The original factual t2 response is not the controlled shared
            # ending. Only common earlier turns belong alongside the A/B replay.
            last = item["input"]["history_a"][-1]["turn_id"].split(":")[-1]
            reference["source_turns"] = [t for t in reference["source_turns"] if t["turn_id"] != last]
    if source.get("replay_path"):
        replay = checked_source(source["replay_path"], source.get("replay_sha256"))
        checks["replay"] = replay is not None
        if replay is not None and item["task"] == "T2":
            reference["replays"] = [{"label": "History " + side.upper(),
                                      "turns": [_review_turn(replay[side], variables)]}
                                     for side in ("a", "b")]
        elif replay is not None and item["task"] == "T3":
            actions = item["input"]["candidate_actions"]
            matches = len(actions) == len(replay) and all(
                action["text"] == branch["candidate_action"]["text"]
                for action, branch in zip(actions, replay))
            checks["branch_action_match"] = matches
            if matches:
                reference["replays"] = [{
                    "label": action["action_id"],
                    "window_complete": branch.get("window_complete", False),
                    "delayed_horizon": branch["delayed_horizon"],
                    "construction": branch.get("experiment"),
                    "reused_prefix_responses": (branch.get("prefix_reuse") or {}).get("environment_responses", 0),
                    "external_conditions": branch.get("counterfactual_timeline_control"),
                    "turns": [_review_turn(t, variables) for t in branch["future_turns"]],
                } for action, branch in zip(actions, replay)]
    crosscheck = read_json(bank_path() / "state_reference_crosscheck.json", {})
    if crosscheck.get("items_sha256") == bank_sha:
        reference["state_crosscheck"] = next((row for row in crosscheck["rows"]
                                              if row["instance_id"] == item["instance_id"]), None)
    oracle = author.get("oracle_reference", {})
    if oracle.get("packet_path"):
        reference["oracle_packet"] = checked_source(oracle["packet_path"], oracle.get("packet_sha256"))
        checks["oracle_packet"] = reference["oracle_packet"] is not None
    return reference


def load_review(instance_id=None, reference=False,bank_id=None):
    if bank_id is not None and bank_id not in BANK_PATHS:
        return None
    token=_bank_override.set(ROOT/BANK_PATHS[bank_id] if bank_id else None)
    try:
        return _load_review(instance_id,reference)
    finally:
        _bank_override.reset(token)


def _load_review(instance_id=None, reference=False):
    items, bank_sha = load_bank()
    if instance_id is None:
        rows = [metadata(item) for item in items]
        manifest=read_json(bank_path()/'manifest.json',{})
        pairing = media_pairing_report(bank_sha)
        return {
            "format": "socialflux_offline_choice_review_v1", "bank_id": bank_path().name,
            "bank_sha256": bank_sha, "status": "available" if items else "not_generated",
            "summary": {
                "item_count": len(items), "scenario_count": len({i["story_id"] for i in items}),
                "tasks": dict(Counter(i["task"] for i in items)),
                "combinations": sum(row["combination"] for row in rows),
                "replay_pending": sum(row["task"] in {"T2", "T3"} and
                                      row["replay_status"] != "validated" for row in rows),
                "machine_concerns": sum(row.get("oracle_status") == "machine_concerns_pending_revision" for row in rows),
                "expected_items":manifest.get('expected_items',len(items)),
                "requested_scenarios":manifest.get('requested_scenarios',len({i['story_id'] for i in items})),
                "generation_complete":manifest.get('complete',True),
                "paused_tasks":manifest.get('paused_tasks',[]),
                "active_generation_jobs":active_generation_jobs(),
                "media_pairs": pairing.get("logical_pairs"),
                "media_missing": pairing.get("coverage_counts", {}).get("missing"),
                "primary_capabilities":manifest.get("primary_capabilities",{}),
                "design_difficulties":manifest.get("design_difficulties",{}),
                "authored_illustrations":manifest.get("authored_illustrations",0),
                "scene_coverage":manifest.get("scene_coverage",[]),
                "migration_levels":dict(Counter(row["migration_level"] for row in rows if row.get("migration_level"))),
                "migration_pending":sum(row.get("migration_status")=="pending" for row in rows),
            }, "items": rows,
        }
    item = next((item for item in items if item["instance_id"] == instance_id), None)
    if item is None:
        return None
    if reference:
        return author_reference(item, bank_sha)
    media = media_records(item)
    return {"bank_sha256": bank_sha, "metadata": metadata(item),
            "public": public_instance(item), "evidence_ids": sorted(visible_evidence(item)),
            "media": media, "media_coverage": media_coverage(item, media),
            "nonverbal_history_relation": item["authoring"].get("nonverbal_history_relation")}
