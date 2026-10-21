"""Refresh formal audits from completed machine artifacts without model calls."""
from pathlib import Path
from collections import Counter
import shutil

from offline.choice_builder import load, save, sha
from offline.oracle import ROOT, now
from evaluation.quality_gates import audit_environment_gate
from scripts.prepare_batch_gate2 import machine_evidence_ready, non_video_machine_evidence_ready
from scripts.complete_gate_machine_checks import probes


def main():
    run = ROOT / "data/gate2_machine_20261020_complete"
    evidence = run / "gate2"
    progress = load(run / "progress.json")
    trajectories = probes.load_records(run / "rollouts")
    cohort = {"scenario_ids": sorted(t["scenario_id"] for t in trajectories),
              "trajectory_ids": sorted(t["trajectory_id"] for t in trajectories)}
    for filename in ("history_intervention.json", "paraphrase_robustness.json",
                     "local_counterfactual.json", "persona_intervention.json"):
        path = evidence / filename
        data = load(path)
        data["provenance"]["input_cohort"] = cohort
        # Records with failed subexperiments are still retained in the aggregate;
        # missing successful rows correctly fail the complete-cohort test.
        save(path, data)
    media = ROOT / "data/gate_media_machine_20261020/video_state_consistency.json"
    shutil.copyfile(media, evidence / media.name)
    manifest = load(evidence / "manifest.json")
    if not (run / "prepare_only_manifest.json").exists():
        save(run / "prepare_only_manifest.json", manifest)
    ready, checks = machine_evidence_ready(evidence, trajectories)
    checks[media.name]["machine_screen_passed"] = load(media)["record"]["machine_screen_passed"]
    ready = ready and checks[media.name]["machine_screen_passed"]
    environment = load(run / "rollout.runtime.json")["environment"]
    manifest.update(updated_at_utc=now(), mode="machine_checks_executed_with_recorded_outcomes",
                    machine_evidence_ready=ready, machine_checks=checks,
                    non_video_machine_evidence_ready=non_video_machine_evidence_ready(checks),
                    machine_execution_complete=all(progress[k] == len(trajectories) for k in ("intervention_groups", "backbone_groups")),
                    original_expected_scenarios=50, readable_source_scenarios=len(trajectories),
                    missing_source_scenarios=50-len(trajectories),
                    formal_gate2_audit=audit_environment_gate(
                        [load(p) for p in sorted((run / "scenarios").glob("*.json"))], evidence),
                    source_environment={
                        k: environment.get(k) for k in ("state_appraisal_prompt_id", "state_calibration_profile",
                                                         "ordinary_state_change_budget")},
                    video_audit_source={"path": str(media.relative_to(ROOT)), "sha256": sha(media)})
    # This inherited prepare-only note named a different prompt version.
    manifest.pop("state_transition_repair", None)
    calls = []
    for path in run.glob("**/calls/**/*.json"):
        record = load(path)
        if "messages" in record:
            calls.append(record)
    manifest["new_logged_api_calls"] = len(calls)
    manifest["api_call_status_counts"] = dict(Counter(r.get("status", "unknown") for r in calls))
    manifest["exact_cached_call_reuses"] = len(list(run.glob("**/calls/reuse/*.json")))
    save(evidence / "manifest.json", manifest)
    print({"execution_complete": manifest["machine_execution_complete"], "machine_ready": ready,
           "new_api_calls": len(calls), "formal_status": manifest["formal_gate2_audit"]["status"]})


if __name__ == "__main__":
    main()
