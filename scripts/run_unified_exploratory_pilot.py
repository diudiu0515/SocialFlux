#!/usr/bin/env python3
"""User-authorized exploration despite disputed fixed labels; never formal admission."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_unified_three_pilot as pilot
from scripts.validate_state_context_samples import BASE, load, save
from providers.factory import public_provider_config

OUT = BASE / "unified_current_trust_v1_exploratory_three"
AUTHORIZATION = "是的，你放下吧，感觉state转换也不是这么严格的事情，你可以多跑几个场景"


def prepare():
    fixed_path = pilot.FIXED / "results.json"
    fixed = load(fixed_path)
    review_path = pilot.FIXED / "semantic_review.json"
    review = load(review_path)
    if fixed.get("status") != "completed" or not fixed.get("code_freeze_unchanged"):
        raise ValueError("Completed frozen fixed run required; exploration does not waive integrity")
    if review["fixed_results_sha256"] != pilot.sha(fixed_path):
        raise ValueError("Fixed review hash mismatch")
    frozen = load(pilot.FIXED / "preregistration.json")["code_sha256"]
    for path, expected in frozen.items():
        if pilot.sha(ROOT / path) != expected:
            raise ValueError("Frozen appraiser changed: " + path)
    selected = deepcopy(pilot.plans())
    for plan in selected:
        plan["policy"]["policy_id"] = plan["case"]["policy"] + "_unified_v1_exploratory_" + plan["case"]["scenario_id"]
    public = [{"case": p["case"],
               "environment": {k: public_provider_config(v) if k.endswith("provider") else v for k, v in p["environment"].items()},
               "policy": {**p["policy"], "provider": public_provider_config(p["policy"]["provider"])},
               "initial_observation": p["observation"]} for p in selected]
    paths = [Path(__file__).relative_to(ROOT), Path("scripts/run_unified_three_pilot.py"),
             Path("scripts/run_role_visible_shadow_pilot.py"), Path("scripts/export_shadow_pilot_review.py")]
    for directory in ("environment", "policies", "providers", "rollout", "evaluation", "pipeline", "schemas", "scenario_design", "shared"):
        paths.extend(p.relative_to(ROOT) for p in (ROOT / directory).rglob("*.py"))
    paths.extend(p.relative_to(ROOT) for p in (ROOT / "prompts").iterdir() if p.is_file())
    paths.extend(Path(p["case"]["candidate"]) for p in selected)
    frozen = {**frozen, **{str(path): pilot.sha(ROOT / path) for path in paths}}
    prereg = {"status": "prepared_not_started", "mode": "explicit_user_authorized_exploration",
              "user_authorization": AUTHORIZATION, "plans": public, "code_sha256": frozen,
              "fixed_results_sha256": pilot.sha(fixed_path), "fixed_review_sha256": pilot.sha(review_path),
              "original_fixed_gate_passed": fixed["mechanical_gate_passed"],
              "disputed_label_indices": review["label_mismatch_indices"],
              "labels_or_scores_changed": False, "workers": 3, "first_pass_only": True,
              "maximum_turns": 20, "target_turns": [10, 20], "pad_short_trajectories": False,
              "quality_review_status": "pending", "formal_human_annotation_status": "not_started",
              "formal_admission": False, "automatic_scale": False,
              "review_axes": ["actor ownership", "semantic repetition", "state continuity", "dialogue naturalness", "task constructibility"]}
    path = OUT / "preregistration.json"
    if path.exists():
        if load(path) != prereg:
            raise ValueError("Exploration preparation changed")
    else:
        save(path, prereg)
    return selected, prereg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    selected, prereg = prepare()
    if not args.run:
        print("Prepared three review-only slots under explicit user authorization; no API calls.", flush=True)
        return
    if (OUT / "results.json").exists():
        raise FileExistsError("Preserve every first-pass result; no automatic reruns")
    pilot.OUT = OUT
    report = {"status": "running", "mode": prereg["mode"], "rows": {},
              "original_fixed_gate_passed": prereg["original_fixed_gate_passed"],
              "user_authorization": AUTHORIZATION, "quality_review_status": "pending",
              "formal_admission": False, "automatic_scale": False}
    save(OUT / "results.json", report)
    pilot.refresh_exports()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(pilot.run_one, i, plan): i for i, plan in enumerate(selected)}
        for future in as_completed(futures):
            report["rows"][str(futures[future])] = future.result()
            save(OUT / "results.json", report)
            pilot.refresh_exports()
    report["status"] = "completed"
    report["code_freeze_unchanged"] = all(pilot.sha(ROOT / path) == expected for path, expected in prereg["code_sha256"].items())
    save(OUT / "results.json", report)
    pilot.refresh_exports()
    print("All three attempts finished; review full dialogues before expanding. Fixed labels and scores remain unchanged.", flush=True)


if __name__ == "__main__":
    main()
