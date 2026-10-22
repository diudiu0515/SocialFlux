"""Run-scoped T2 artifacts that cannot mix stale results across runs."""

from __future__ import annotations

from pathlib import Path

from tasks.T2.runtime import load, now
from tasks.T2.pair_builder import BUILDER_VERSION, sha256_file


from tasks.T2.runtime import count_requests
from shared.artifacts import atomic_json as atomic


def result_name(index, spec):
    return f"spec_{index:03d}_scenario_{int(spec['ordinal']):03d}.json"


def initialize_run(
    run_dir, *, run_id, config_path, pair_source, specs, model_routes,
):
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    manifest = {
        "format": "socialflux_t2_run_manifest_v2",
        "builder_version": BUILDER_VERSION,
        "run_id": run_id,
        "created_at_utc": now(),
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "pair_spec_source": str(pair_source),
        "pair_spec_sha256": sha256_file(pair_source),
        "model_routes_path": str(model_routes.source_path),
        "model_routes_sha256": model_routes.sha256,
        "expected_results": [
            {
                "spec_index": index,
                "ordinal": spec["ordinal"],
                "artifact": f"results/{result_name(index, spec)}",
            }
            for index, spec in enumerate(specs)
        ],
    }
    if manifest_path.exists():
        existing = load(manifest_path)
        stable = (
            "builder_version",
            "run_id",
            "config_sha256",
            "pair_spec_sha256",
            "model_routes_sha256",
        )
        if any(existing.get(key) != manifest.get(key) for key in stable):
            raise ValueError("run directory belongs to a different T2 configuration")
        return existing
    atomic(manifest_path, manifest)
    return manifest


def write_result(run_dir, index, spec, result):
    path = Path(run_dir) / "results" / result_name(index, spec)
    atomic(path, result)
    return path


def summarize_run(run_dir):
    run_dir = Path(run_dir)
    manifest = load(run_dir / "manifest.json")
    rows = []
    counts = {}
    environment_issue_counts = {}
    total_requests = 0
    codex_path = run_dir / "codex_full_text_review.json"
    codex_document = load(codex_path) if codex_path.exists() else {}
    codex_reviews = {
        row["scenario_id"]: row
        for row in codex_document.get("reviews", [])
    }
    for expected in manifest["expected_results"]:
        path = run_dir / expected["artifact"]
        if not path.exists():
            row = {**expected, "status": "not_run"}
        else:
            result = load(path)
            if result.get("run_id") != manifest["run_id"]:
                raise ValueError(f"result run_id mismatch: {path}")
            status = result["status"]
            codex_review = codex_reviews.get(result.get("scenario_id"), {})
            codex_issues = codex_review.get("environment_issues") or []
            for item in codex_issues:
                for category in item.get("categories", []):
                    environment_issue_counts[category] = environment_issue_counts.get(category, 0) + 1
            pair = result.get("pair") or {}
            review = pair.get("model_pair_review") or {}
            issues = review.get("environment_issues") or []
            for item in issues:
                for category in item.get("categories", []):
                    environment_issue_counts[category] = environment_issue_counts.get(category, 0) + 1
            requests = (pair.get("request_counts") or result.get("request_counts") or {}).get("total")
            if requests is None:
                requests = count_requests(result.get("request_counts", {}))
            total_requests += int(requests or 0)
            row = {
                **expected,
                "scenario_id": result.get("scenario_id"),
                "title": result.get("scenario_title"),
                "status": status,
                "stage": result.get("stage"),
                "pair_review_decision": review.get("decision"),
                "environment_issue_count": len(issues),
                "codex_review_decision": codex_review.get("decision"),
                "codex_environment_issue_count": len(codex_issues),
                "answer_review_decision": (pair.get("model_answer_review") or {}).get("decision"),
                "human_review": result.get("human_review", "pending"),
                "request_count": int(requests or 0),
            }
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        row["task_candidate_usable"] = (
            row["status"] == "completed"
            and row.get("codex_review_decision") in {None, "approve"}
            and row.get("answer_review_decision") == "approve"
        )
        rows.append(row)
    summary = {
        "format": "socialflux_t2_run_summary_v2",
        "builder_version": BUILDER_VERSION,
        "run_id": manifest["run_id"],
        "updated_at_utc": now(),
        "expected_count": len(manifest["expected_results"]),
        "result_count": sum(row["status"] != "not_run" for row in rows),
        "status_counts": counts,
        "environment_issue_counts": environment_issue_counts,
        "codex_reviewed_count": len(codex_reviews),
        "task_candidate_usable_count": sum(row["task_candidate_usable"] for row in rows),
        "codex_review_file": "codex_full_text_review.json" if codex_path.exists() else None,
        "total_actual_requests_including_retries": total_requests,
        "human_accepted": sum(row.get("human_review") == "accepted" for row in rows),
        "results": rows,
    }
    atomic(run_dir / "summary.json", summary)
    return summary
