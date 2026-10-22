"""Check every designed online asset, not merely one playable clip per scene."""

from collections import Counter, defaultdict
from pathlib import Path
import hashlib


def audit_asset_coverage(manifest, batch_root, *, expected_scenarios=50):
    root = Path(batch_root).resolve()
    by_scenario = defaultdict(list)
    seen = set()
    invalid = []
    for record in manifest.get("requests", []):
        key = (record.get("scenario_id"), record.get("event_family"))
        if key in seen:
            invalid.append({"request_id": record.get("request_id"), "reason": "duplicate scenario/event family"})
        seen.add(key)
        path = (root / record.get("video_file", "")).resolve()
        present = path.is_relative_to(root) and path.is_file()
        checksum_ok = bool(present and record.get("video_sha256") and
                           hashlib.sha256(path.read_bytes()).hexdigest() == record["video_sha256"])
        usable = record.get("status") == "generated_structural_pass" and checksum_ok
        by_scenario[key[0]].append({"request_id": record.get("request_id"), "event_family": key[1],
                                   "status": record.get("status"), "file_present": present,
                                   "checksum_valid": checksum_ok, "generated": usable,
                                   "provider_error": record.get("provider_error")})
    scenarios = [{"scenario_id": sid, "required": len(rows),
                  "generated": sum(r["generated"] for r in rows),
                  "complete": all(r["generated"] for r in rows),
                  "missing": [r for r in rows if not r["generated"]]}
                 for sid, rows in sorted(by_scenario.items())]
    full = sum(r["complete"] for r in scenarios)
    return {"format": "socialflux_t4_asset_coverage_v1", "expected_scenarios": expected_scenarios,
            "manifest_scenarios": len(scenarios), "required_assets": len(manifest.get("requests", [])),
            "generated_assets": sum(r["generated"] for r in scenarios),
            "scenarios_with_any_video": sum(r["generated"] > 0 for r in scenarios),
            "scenarios_with_all_required_videos": full,
            "scenarios_without_video": [r["scenario_id"] for r in scenarios if not r["generated"]],
            "generation_complete": len(scenarios) == expected_scenarios and full == expected_scenarios and not invalid,
            "status_counts": dict(Counter(r.get("status") for r in manifest.get("requests", []))),
            "invalid_records": invalid, "scenarios": scenarios,
            "review_and_delivery": "Separate human review and API media-delivery checks are still required; generation completeness does not certify them."}


def require_complete_assets(report):
    if not report["generation_complete"]:
        raise ValueError(f"Incomplete online assets: {report['generated_assets']}/{report['required_assets']} assets; "
                         f"{report['scenarios_with_all_required_videos']}/{report['expected_scenarios']} fully covered scenarios")
