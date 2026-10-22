#!/usr/bin/env python3
"""Apply the four automated talking-head release gates, including live web sync."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "media" / "talking_head" / "manifest.json"
AV_REPORT = ROOT / "media" / "talking_head" / "av_sync_screen.json"
VISUAL_REPORT = ROOT / "media" / "talking_head" / "visual_stability_screen.json"
REPORT = ROOT / "media" / "talking_head" / "quality_gate_report.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def fetch_json(url):
    with urlopen(url, timeout=10) as response:
        return json.load(response)


def web_check(base_url, manifest):
    health = fetch_json(f"{base_url}/api/health")
    web_assets = {}
    scenario_errors = []
    for scenario_number in range(1, 21):
        scenario_id = f"IA_PIPE_{scenario_number:03d}"
        detail = fetch_json(f"{base_url}/api/scenarios/{scenario_id}")
        assets = detail.get("media_assets", [])
        if len(assets) != 3:
            scenario_errors.append(
                f"{scenario_id}: expected 3 media assets, got {len(assets)}"
            )
        for asset in assets:
            web_assets[asset["asset_id"]] = asset

    transfer_errors = []
    manifest_by_id = {item["asset_id"]: item for item in manifest["assets"]}
    if set(web_assets) != set(manifest_by_id):
        transfer_errors.append("website and manifest asset ID sets differ")
    for asset_id, record in manifest_by_id.items():
        web_record = web_assets.get(asset_id)
        if web_record is None:
            continue
        expected_url = (
            f"/media/{asset_id}?v={record['video_sha256'][:12]}"
        )
        if web_record.get("url") != expected_url:
            transfer_errors.append(f"{asset_id}: stale cache-busting URL")
            continue
        with urlopen(base_url + expected_url, timeout=20) as response:
            payload = response.read()
            content_type = response.headers.get_content_type()
        if content_type != "video/mp4":
            transfer_errors.append(f"{asset_id}: content type {content_type}")
        if hashlib.sha256(payload).hexdigest() != record["video_sha256"]:
            transfer_errors.append(f"{asset_id}: served bytes do not match manifest hash")
    return {
        "passed": (
            health.get("ok") is True
            and health.get("scenario_count") == 20
            and not scenario_errors
            and not transfer_errors
            and len(web_assets) == 60
        ),
        "health": health,
        "scenario_count": health.get("scenario_count"),
        "asset_count": len(web_assets),
        "scenario_errors": scenario_errors,
        "transfer_errors": transfer_errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    manifest = load(MANIFEST)
    av = load(AV_REPORT)
    visual = load(VISUAL_REPORT)
    structure_passed = (
        manifest.get("asset_count") == 60
        and manifest.get("generated_count") == 60
        and manifest.get("structural_validation") == "passed"
        and not manifest.get("validation_errors")
        and all(item.get("status") == "generated" for item in manifest["assets"])
    )
    av_passed = (
        av.get("asset_count") == 60
        and av.get("pass_count") == 60
        and av.get("review_count") == 0
    )
    visual_passed = (
        visual.get("asset_count") == 60
        and visual.get("pass_count") == 60
        and visual.get("review_count") == 0
    )
    website = web_check(args.base_url.rstrip("/"), manifest)
    gates = {
        "gate_1_media_structure": {
            "passed": structure_passed,
            "asset_count": manifest.get("asset_count"),
            "generated_count": manifest.get("generated_count"),
            "validation_error_count": len(manifest.get("validation_errors", [])),
        },
        "gate_2_audio_conditioned_lipsync": {
            "passed": av_passed,
            "pass_count": av.get("pass_count"),
            "review_count": av.get("review_count"),
            "evidence": str(AV_REPORT.relative_to(ROOT)),
        },
        "gate_3_identity_and_visual_stability": {
            "passed": visual_passed,
            "pass_count": visual.get("pass_count"),
            "review_count": visual.get("review_count"),
            "evidence": str(VISUAL_REPORT.relative_to(ROOT)),
        },
        "gate_4_website_manifest_integrity": {
            **website,
        },
    }
    all_passed = all(gate["passed"] for gate in gates.values())
    for record in manifest["assets"]:
        checks = record.setdefault("quality_checks", {})
        checks["gate_4_website_manifest_integrity"] = (
            "pass" if website["passed"] else "review"
        )
        record["quality_status"] = (
            "automated_four_gate_pass_human_playback_recommended"
            if all_passed
            else "quality_gate_review_required"
        )
    manifest["quality_gate"] = {
        "status": "passed" if all_passed else "review_required",
        "gate_count": 4,
        "passed_gate_count": sum(gate["passed"] for gate in gates.values()),
        "report_path": str(REPORT.relative_to(ROOT)),
        "human_review_note": (
            "Automated gross-failure gates passed; subjective naturalness still "
            "benefits from final human playback review."
        ),
    }
    report = {
        "format": "socialflux_talking_head_four_gate_report_v1",
        "status": "passed" if all_passed else "review_required",
        "gates": gates,
        "asset_count": len(manifest["assets"]),
        "generator": manifest.get("generator"),
        "generation_profile": manifest.get("generation_profile"),
        "scope_note": (
            "These four gates apply to talking-head media. They do not replace "
            "the dataset Gate 1-4 contract in docs/protocols/quality_gate.md."
        ),
    }
    dump(MANIFEST, manifest)
    dump(REPORT, report)
    print(json.dumps({
        "status": report["status"],
        "passed_gates": manifest["quality_gate"]["passed_gate_count"],
        "asset_count": report["asset_count"],
        "website_assets": website["asset_count"],
    }))
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
