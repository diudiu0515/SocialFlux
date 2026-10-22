"""Freeze and score saved terminal trajectories with explicit modality accounting."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
from statistics import mean, stdev

from evaluation.t4_evaluation import T4_DIMENSIONS, assert_t4_trajectory
from evaluation.t4_rubric import T4_RUBRIC
from prompts.loader import get_prompt
from providers.factory import build_provider, public_provider_config
from tasks.T4.answering import generate_judgment


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def modality_audit(trajectory):
    provenance = trajectory.get("policy_provenance", {})
    condition = provenance.get("observation_condition")
    if condition not in {"text_only", "text_video"}:
        raise ValueError("missing or unsupported policy observation_condition; cannot infer from media placeholders")
    shown = []
    for turn in trajectory["turns"]:
        # Media after the final action was never observed by the policy.
        for media in turn.get("observation", {}).get("media", []):
            if media.get("media_type") == "video":
                shown.append(media)
    available = sum(m.get("asset_status") == "available" and
                    isinstance(m.get("asset_url"), str) and
                    m["asset_url"].startswith("https://") for m in shown)
    if condition == "text_video" and (not available or available != len(shown)):
        raise ValueError("text_video has absent/unavailable policy-input videos; no text fallback allowed")
    return {"policy_condition": condition,
            "available_video_observations": available,
            "policy_video_observations": available if condition == "text_video" else 0,
            "planned_video_observations": sum(m.get("asset_status") == "planned" for m in shown)}


def aggregate_scores(judgment):
    values = {k: judgment["dimensions"][k]["score"] for k in T4_DIMENSIONS}
    present = [v for v in values.values() if v is not None]
    return {**values,
            "core_four_mean": mean(values[k] for k in T4_DIMENSIONS if k != "recovery"),
            "available_dimension_mean": mean(present),
            "five_dimension_mean": mean(present) if len(present) == 5 else None}


def describe(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0, "mean": None, "sd": None, "bootstrap_ci95": None}
    rng = random.Random(7401)
    boots = sorted(mean(rng.choices(values, k=len(values))) for _ in range(2000)) if len(values) > 1 else []
    return {"n": len(values), "mean": round(mean(values), 4),
            "sd": round(stdev(values), 4) if len(values) > 1 else None,
            "bootstrap_ci95": [round(boots[49], 4), round(boots[1949], 4)] if boots else None}


def summarize(rows):
    completed = [r for r in rows if r["status"] == "completed"]
    metrics = (*T4_DIMENSIONS, "core_four_mean", "available_dimension_mean", "five_dimension_mean")
    groups = {}
    for condition in ("text_only", "text_video"):
        selected = [r for r in completed if r["modality"]["policy_condition"] == condition]
        groups[condition] = {"n": len(selected), "metrics": {
            key: describe([r["scores"][key] for r in selected]) for key in metrics}}
    by_id = {}
    for row in completed:
        by_id.setdefault(row["scenario_id"], {})[row["modality"]["policy_condition"]] = row
    pairs = [pair for pair in by_id.values() if set(pair) == {"text_only", "text_video"}]
    paired = {}
    for key in metrics:
        deltas = [p["text_video"]["scores"][key] - p["text_only"]["scores"][key]
                  for p in pairs if all(p[c]["scores"][key] is not None for c in p)]
        paired[key] = {**describe(deltas), "win": sum(d > 0 for d in deltas),
                       "tie": sum(d == 0 for d in deltas), "loss": sum(d < 0 for d in deltas)}
    return {"status_counts": dict(Counter(r["status"] for r in rows)),
            "conditions": groups, "matched_scenarios": len(pairs),
            "paired_text_video_minus_text": paired,
            "api_request_count": sum(r.get("provider_metrics", {}).get("request_count", 0) for r in rows),
            "human_validation_status": "not_human_validated",
            "limitations": ["Retrospective terminal scoring; source policy prompt and horizon remain unchanged.",
                            "Single automatic judge; no human calibration or independent-model validation.",
                            "Bootstrap intervals describe sampled scenarios, not judge reliability.",
                            "No modality effect can be estimated without actual matched text_video trajectories."]}


def run_saved_batch(manifest_path, output, config, *, workers=3, max_attempts=2, resume=False):
    output = Path(output)
    source = json.loads(Path(manifest_path).read_text())
    judge = config["judge"]
    if judge.get("observation_condition", "text_only") != "text_only":
        raise ValueError("batch comparisons require the same blind text-only terminal judge for both policy conditions")
    if not 1 <= workers <= 8 or not 1 <= max_attempts <= 5:
        raise ValueError("workers must be 1..8 and judge attempts 1..5")
    frozen = output / "manifest.json"
    identity = {"source_manifest_sha256": digest(source), "rubric_sha256": digest(T4_RUBRIC),
                "prompt_sha256": hashlib.sha256(get_prompt("t4_judge_v2").encode()).hexdigest(),
                "judge": {**judge, "provider": public_provider_config(judge["provider"])},
                "max_attempts": max_attempts,
                "code_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
                    Path(__file__), Path("evaluation/t4_evaluation.py"), Path("tasks/T4/answering.py"),
                    Path("providers/structured.py"), Path("providers/openai_compatible.py")]}}
    if frozen.exists():
        if not resume:
            raise ValueError("output already exists; use --resume")
        manifest = json.loads(frozen.read_text())
        if manifest["identity"] != identity:
            raise ValueError("frozen rubric, code, judge, or input manifest changed; use a new output directory")
    else:
        records, seen = [], set()
        for index, item in enumerate(source["records"]):
            record = {**item, "record_id": f"{index:03d}"}
            condition = item.get("observation_condition", "unknown")
            key = (item["scenario_id"], condition)
            if key in seen:
                raise ValueError("duplicate scenario/condition; use one trajectory per scenario per run")
            seen.add(key)
            if item.get("status") != "ready":
                record["status"] = "source_unavailable"
                records.append(record)
                continue
            try:
                scenario = json.loads(Path(item["scenario_path"]).read_text())
                trajectory = assert_t4_trajectory(json.loads(Path(item["trajectory_path"]).read_text()))
                if scenario["scenario_id"] != trajectory["scenario_id"] or scenario["scenario_id"] != item["scenario_id"]:
                    raise ValueError("scenario ID mismatch")
                modality = modality_audit(trajectory)
                if modality["policy_condition"] != condition:
                    raise ValueError("declared modality differs from policy provenance")
                value = {"scenario": scenario, "trajectory": trajectory}
                relative = f"inputs/{index:03d}.json"
                save(output / relative, value)
                record.update(status="ready", input_file=relative, input_sha256=digest(value), modality=modality)
            except (ValueError, KeyError, OSError) as exc:
                record.update(status="invalid_source", error=str(exc))
            records.append(record)
        manifest = {"format": "socialflux_t4_saved_batch_v1", "identity": identity,
                    "created_at": datetime.now(timezone.utc).isoformat(), "records": records,
                    "source_notes": source.get("notes", []), "rubric": T4_RUBRIC,
                    "judge_evidence_condition": "text_only", "blind_to_policy_condition": True}
        save(frozen, manifest)

    def score(record):
        if record["status"] != "ready":
            return record
        path = output / "results" / f"{record['record_id']}.json"
        value = json.loads((output / record["input_file"]).read_text())
        if digest(value) != record["input_sha256"]:
            raise ValueError("frozen trajectory input changed")
        if path.exists() and resume:
            # Failed calls remain in this frozen run; reruns need a new run ID.
            return json.loads(path.read_text())
        provider = build_provider(judge["provider"])
        row = {**record, "source_policy": value["trajectory"]["policy_provenance"],
               "observed_turns": len(value["trajectory"]["turns"]), "ending": value["trajectory"]["ending"]}
        try:
            packet, judgment, _ = generate_judgment(
                provider, value["trajectory"], value["scenario"], judge.get("sampling", {}).get("seed", 7401),
                max_attempts=max_attempts, sampling=judge.get("sampling", {}))
            row.update(status="completed", judgment=judgment, scores=aggregate_scores(judgment), judge_packet=packet)
        except Exception as exc:
            row.update(status="judge_failed", error=str(exc), last_raw_output=getattr(exc, "last_raw", None))
        row["provider_metrics"] = getattr(provider, "metrics", {})
        save(output / "api_audits" / f"{record['record_id']}.json", getattr(provider, "audit_records", []))
        save(path, row)
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(score, r): r for r in manifest["records"]}
        for future in as_completed(futures):
            record = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {**record, "status": "runner_failed", "error": str(exc)}
            rows.append(row)
            save(output / "progress.json", {"finished": len(rows), "total": len(futures),
                                             "status_counts": dict(Counter(r["status"] for r in rows))})
            print(f"{len(rows)}/{len(futures)} {row['scenario_id']} {row['status']}", flush=True)
    rows.sort(key=lambda r: r["record_id"])
    summary = summarize(rows)
    save(output / "summary.json", summary)
    save(output / "all_results.json", rows)
    fields = ["scenario_id", "condition", "status", "observed_turns", *T4_DIMENSIONS,
              "core_four_mean", "available_dimension_mean", "five_dimension_mean"]
    with (output / "scores.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({"scenario_id": row["scenario_id"], "condition": row.get("observation_condition"),
                             "status": row["status"], "observed_turns": row.get("observed_turns"), **row.get("scores", {})})
    return summary
