"""Allowlisted accounting of single-run T4 result slots; never pools runs."""
from collections import Counter


def execution_accounting(plan, results, model_names):
    scenarios = plan.get("scenario_sha256")
    if not isinstance(scenarios, dict) or not isinstance(results, list):
        return []
    slots = {}
    for row in results:
        if not isinstance(row, dict) or row.get("scenario_id") not in scenarios:
            continue
        condition = row.get("condition") or row.get("modality", {}).get("policy_condition")
        key = (row["scenario_id"], row.get("model_id"), condition)
        slots.setdefault(key, []).append(row)
    output = []
    for model in model_names:
        for condition in ("text_only", "text_video"):
            groups = [rows for (_, name, mode), rows in slots.items()
                      if name == model and mode == condition]
            # Identical inherited copies count once; conflicting copies require review.
            conflicts = sum(any(row != rows[0] for row in rows[1:]) for rows in groups)
            rows = [copies[0] for copies in groups if all(row == copies[0] for row in copies[1:])]
            counts = Counter(row.get("status", "unknown") for row in rows)
            completed = counts["completed"] + counts["completed_without_video_exposure"]
            valid = sum(row.get("status") == "completed" and
                        (condition == "text_only" or row.get("video_delivery_count", 0) > 0)
                        for row in rows)
            failed = sum(n for status, n in counts.items()
                         if status == "failed" or status.endswith("_failed"))
            no_video = sum(condition == "text_video" and
                           row.get("status") in ("completed", "completed_without_video_exposure") and
                           not row.get("video_delivery_count", 0) for row in rows)
            transports = sorted({row.get("transport") for row in rows
                                 if row.get("transport") in ("native_video", "video_frames")})
            planned = len(scenarios)
            output.append(dict(model=model, condition=condition, planned=planned,
                recorded=len(groups), completed=completed, valid_scored=valid, failed=failed,
                unrecorded=planned-len(groups), completion_rate=completed/planned if planned else None,
                unsupported=counts["unsupported_video_input"], missing_video=no_video,
                delegated=counts["delegated_to_run"],
                duplicate_records=sum(len(rows)-1 for rows in groups), conflicting_slots=conflicts,
                transports=transports))
    return output
