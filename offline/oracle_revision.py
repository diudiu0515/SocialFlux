"""Repair explicitly failed oracle authoring groups with frozen evidence.

Revisions are new artifacts; failed requests and previous proposals are retained.
No human labels or source admission are manufactured.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
from pathlib import Path

from offline.choice_builder import load, save, sha
from offline.oracle import ROOT, AUTHOR_PROMPT, json_call, patch_item, evidence_packet, summarize, review_group
from offline.reuse_audit import digest
from providers.factory import public_provider_config
from providers.model_routes import ModelRoutes
from tasks.offline_choice import visible_evidence, ERROR_TYPES


def repair_group(items, run, config, round_name):
    name = items[0]["story_id"] + "-" + items[0]["task"]
    original_dir = run / "groups" / name
    directory = run / "repairs" / round_name / name
    packet = load(original_dir / "evidence.json") if (original_dir / "evidence.json").exists() else evidence_packet(items[0], run)
    save(original_dir / "evidence.json", packet)
    save(directory / "evidence.json", packet)
    failures = [load(p) for p in sorted((original_dir / "errors").glob("*.json"))]
    previous = []
    for path in sorted((original_dir / "calls").glob("*.json"), key=lambda p: load(p)["started_at_unix"]):
        record = load(path)
        if record.get("raw_output"):
            previous.append({"raw_output": record["raw_output"], "call_path": str(path.relative_to(ROOT))})
    public_questions = [{k: item[k] for k in ("instance_id", "task", "subtype", "question", "options", "target_spec")} for item in items]
    payload = {
        "public_input": packet["public_input"],
        "private_evidence": {k: v for k, v in packet.items() if k != "public_input"},
        "allowed_state_paths": packet["allowed_state_paths"],
        "questions": public_questions, "allowed_option_errors": sorted(ERROR_TYPES),
        "allowed_public_evidence_ids": sorted(visible_evidence(items[0])),
        "allowed_private_evidence_ids": packet["evidence_ids"],
        "previous_execution_errors": failures,
        "previous_proposal_to_repair": previous[0] if previous else None,
        "strict_schema_notes": [
            "逐字保留 subtype 和 target_spec 中除 target_state_ids/risk_event/risk_window/goal/time_scope 以外的字段；不存在的字段不要增加。",
            "option_errors 的键恰好是 A/B/C/D 中除 answer 之外的三个；正确选项不要写入 option_errors。",
            "evidence_ids 和 counterevidence_ids 只能从 allowed_public_evidence_ids 选，T2必须同时引用A:和B:；不能写不带A:/B:的 t1、t2。",
            "oracle_evidence_ids 只能从 allowed_private_evidence_ids 选；它与公开 evidence_ids 是两个不同编号空间。",
            "state_combination 和 joint_comparison 必须同时判断恰好两个实际记录的状态变量；不要把组合题缩为单变量。",
            "只要 target_state_ids 包含 consequence_risk.*，target_spec 必须单独包含非空 risk_event 和 risk_window 字段；写进 time_scope 不能代替这两个字段。",
            "选项必须真实判断所选两个状态变量。若回放两侧相同，可正确回答相同；不要用公开措辞的差别冒充实际状态差别。公开材料无法判别时明确保留歧义问题。",
            "T3 horizon=immediate 时，oracle_evidence_ids 只可用 private: 前史和 action_N:immediate，不得引用任何 step2 以后的状态或事件，解释也不得以后来发生的事情支撑即时结论。",
        ],
    }
    payload["mandatory_repairs"] = [
        {"instance_id": item["instance_id"], "required_target_count":
            2 if item["subtype"] in ("state_combination", "joint_comparison") else "one_or_two",
         "current_structural_issues": structural_issues(item)}
        for item in items]
    artifact = directory / "result.json"
    def validate(data):
        if [q["instance_id"] for q in data["questions"]] != [x["instance_id"] for x in items]:
            raise ValueError("both original question IDs required")
        for item, proposal in zip(items, data["questions"]):
            try:
                patch_item(item, proposal, packet, artifact)
                if proposal["subtype"] in ("state_combination", "joint_comparison") and len(proposal["target_spec"]["target_state_ids"]) != 2:
                    raise ValueError("组合题必须恰好两个实际记录变量，且所有选项映射同时覆盖两个变量")
                if item["task"] == "T3" and item["target_spec"]["horizon"] == "immediate" and any(
                        ":step" in ev for ev in proposal["oracle_evidence_ids"]):
                    raise ValueError("即时题不能引用 step2 或更晚分支")
            except ValueError as exc:
                raise ValueError(str(exc) + "; exact public IDs=" + str(payload["allowed_public_evidence_ids"])) from exc
    data = json_call(run, "repairs/" + round_name + "/" + name, AUTHOR_PROMPT, payload, config, validate, 7000)
    revised = [patch_item(x, q, packet, artifact) for x, q in zip(items, data["questions"])]
    if (original_dir / "items.json").exists():
        old = load(original_dir / "items.json")
        history = run / "revision_history" / name / digest(old)
        save(history / "items.json", old)
        review_dir = run / "reviews" / name
        if review_dir.exists():
            review_dir.rename(history / "oracle_review")
        blind_path = run / "blind/blind_review" / (name + ".json")
        if blind_path.exists():
            blind_path.rename(history / "public_blind_review.json")
    save(original_dir / "items.json", revised)
    return revised


def structural_issues(item):
    issues = []
    if item["subtype"] in ("state_combination", "joint_comparison") and len(item["target_spec"]["target_state_ids"]) != 2:
        issues.append("combination_requires_two_recorded_variables")
    if item["task"] == "T3" and item["target_spec"]["horizon"] == "immediate" and any(
            ":step" in ev for ev in item["authoring"].get("oracle_reference", {}).get("evidence_ids", [])):
        issues.append("immediate_reference_uses_later_branch")
    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="data/offline_oracle_20261020_complete")
    parser.add_argument("--round", default="failed_schema_repair")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--structural", action="store_true")
    args = parser.parse_args()
    run = ROOT / args.run
    config = ModelRoutes.load(ROOT / "configs/gpt50_experiment/model_routes.hybrid.v3_2.json").provider_config("quality_review")
    config.update(timeout=120, max_transport_attempts=1, retry_backoff_seconds=0, max_tokens=7000)
    groups = defaultdict(list)
    source = ([x for p in sorted((run / "groups").glob("*/items.json")) for x in load(p)]
              if args.structural else map(json.loads, (run / "source.items.jsonl").read_text().splitlines()))
    for item in source:
        groups[item["story_id"] + "-" + item["task"]].append(item)
    failed = {p.name.rsplit("-", 1)[0] for p in (run / "failures").glob("*.json") if load(p)["phase"] == "author"}
    selected = ({name: rows for name, rows in groups.items() if any(structural_issues(x) for x in rows)} if args.structural else
                {name: rows for name, rows in groups.items() if name in failed and not (run / "groups" / name / "items.json").exists()})
    save(run / "repairs" / args.round / "manifest.json", {"code_sha256": sha(Path(__file__)),
         "selected_groups": sorted(selected), "provider": public_provider_config(config)})
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(repair_group, rows, run, config, args.round): name for name, rows in selected.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                items = future.result()
                print("repaired", name, flush=True)
                if args.review:
                    review_group(items, run, config)
            except Exception as exc:
                save(run / "repairs" / args.round / name / "failure.json", {"type": type(exc).__name__, "error": str(exc)})
                print("repair FAILED", name, str(exc)[:220], flush=True)
            summarize(run)


if __name__ == "__main__":
    main()
