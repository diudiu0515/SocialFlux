"""Resume canonical Gate 2 probes and add the independent Gate 3 audit.

Original natural trajectories, unsuccessful attempts and human packets remain
unchanged. Completion, machine pass and human admission are distinct outcomes.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from offline.choice_builder import load, save, sha
from offline.oracle import json_call, now
from offline.provider_compat import OfflineLoggedProvider, OfflineSamplingProvider, OfflineRuntimeFactory
from offline.reuse_audit import digest
from environment.unified_appraisal import UnifiedEnvironmentFactory
from evaluation.backbone_sensitivity import compare_transitions, failed_comparison, summarize_backbone_sensitivity
from evaluation.rollout_gate import public_judge_packet, audit_rollout
from evaluation.rollout_semantic_review import validate_judgment
from pipeline.runtime import build_environment_factory
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from prompts.loader import render_prompt
from scripts import auto_gate2_unified_gpt50 as adapter
from scripts import run_environment_interventions as probes
from scripts import run_backbone_sensitivity as backbone
from scripts import prepare_batch_gate2 as gate2
from scripts.review_active_rollouts import source_rows, decision
from web.live_rollouts import ACTIVE


def bounded(provider):
    result = deepcopy(provider)
    result.update(timeout=100, max_transport_attempts=1, retry_backoff_seconds=0)
    for key in ("candidates",):
        if key in result:
            result[key] = [bounded(x) for x in result[key]]
    return result


class Replay:
    def __init__(self, plans, output):
        self.plans = {p["case"]["scenario_id"]: p for p in plans}
        self.output = output

    def factory(self, scenario, *args, backbone_spec=None, **kwargs):
        sid = scenario["scenario_id"]
        config = deepcopy(self.plans[sid]["environment"])
        if backbone_spec:
            for key in ("state_appraisal_provider", "interaction_appraisal_provider"):
                config[key] = deepcopy(backbone_spec["provider"])
                config[key]["max_tokens"] = 6000
            for key in ("state_appraisal_sampling", "interaction_appraisal_sampling"):
                config[key].update(backbone_spec.get("sampling", {}))
        for key in ("state_appraisal_provider", "interaction_appraisal_provider", "response_provider"):
            config[key] = bounded(config[key])
        factory = OfflineRuntimeFactory(
            UnifiedEnvironmentFactory(build_environment_factory(scenario, config)),
            self.output / sid / (backbone_spec["model_family"] if backbone_spec else "primary") / "calls")
        save(self.output / sid / ("runtime-" + (backbone_spec["model_family"] if backbone_spec else "primary") + ".json"),
             {"environment": factory.provenance, "response_calls": 0})
        return factory

    def replay(self, factory, snapshot, action):
        env = factory()
        env.restore(adapter.project_history(snapshot))
        return adapter.interpret(env, action)


def materialize(run):
    registered = load(ACTIVE / "preregistration.json")
    plans = deepcopy(registered["plans"])
    for plan in plans:
        path = ROOT / plan["case"]["candidate"]
        if sha(path) != plan["case"]["candidate_sha256"]:
            raise ValueError("frozen scenario changed")
        plan["scenario"] = load(path)
        # Preregistration strips credential locations. Restore locations from
        # the already-used runtime without printing or serializing key contents.
        previous = load(ACTIVE / "gate2_followup/rollout.runtime.json")["environment"]
        def credentials(current, template):
            for key in ("api_key_env", "api_key_file"):
                if key in template and key not in current:
                    current[key] = template[key]
            for child, old in zip(current.get("candidates", []), template.get("candidates", [])):
                credentials(child, old)
        for key in ("provider", "response_provider", "state_appraisal_provider", "interaction_appraisal_provider"):
            credentials(plan["environment"][key], previous[key])
    old_source, old_dest = adapter.SOURCE, adapter.DEST
    adapter.SOURCE, adapter.DEST = ACTIVE, run
    try:
        adapter.materialize(plans)
    finally:
        adapter.SOURCE, adapter.DEST = old_source, old_dest
    config = load(run / "rollout.runtime.json")
    config["construction"]["provider"] = bounded(config["construction"]["provider"])
    config["construction"]["sampling"].pop("top_p", None)
    config["construction"]["sampling"]["temperature"] = 0
    save(run / "rollout.runtime.json", config)
    return plans, config


def intervention_job(trajectory, scenarios, config, replay, run):
    sid = trajectory["scenario_id"]
    path = run / "probes" / sid / "result.json"
    binding = digest({"trajectory": trajectory, "scenario": scenarios[sid], "config": config,
                      "experiment_version": probes.EXPERIMENT_VERSION, "adapter": sha(Path(__file__))})
    if path.exists():
        cached = load(path)
        if cached["binding"] != binding:
            raise ValueError("probe inputs changed")
        return cached["record"]
    checkpoint = probes.select_intervention_checkpoint(trajectory)
    record = {"scenario_id": sid, "source_trajectory_id": trajectory["trajectory_id"],
              "checkpoint_turn_id": checkpoint["turn_id"], "experiment_version": probes.EXPERIMENT_VERSION,
              "attempt": 1}
    factory = replay.factory(scenarios[sid])
    provider = OfflineLoggedProvider(OfflineSamplingProvider(build_provider(config["construction"]["provider"])),
                                    run / "probes" / sid / "construction" / "calls")
    generator = probes.ModelCandidateGenerator(provider, config["construction"]["sampling"])
    for name, fn in (
        ("e3", lambda: probes._e3(factory, trajectory, checkpoint)),
        ("e4", lambda: probes._e4(factory, provider, config["construction"]["sampling"], trajectory, checkpoint)),
        ("e5", lambda: probes._e5(factory, generator, checkpoint)),
        ("e7", lambda: probes._e7(config, provider, config["construction"]["sampling"], scenarios[sid], trajectory, checkpoint)),
    ):
        subpath = path.with_name(name + ".json")
        if subpath.exists():
            part = load(subpath)
            if part["binding"] != binding:
                raise ValueError("probe substep inputs changed")
            record[name] = part["result"]
            continue
        try:
            record[name] = fn()
            save(subpath, {"binding": binding, "result": record[name]})
        except Exception as exc:
            record.setdefault("errors", {})[name] = {"type": type(exc).__name__, "message": str(exc)}
    if record.get("errors"):
        record["error"] = record["errors"]
    save(path, {"binding": binding, "record": record})
    return record


def backbone_job(trajectory, scenario, replay, specs, run):
    path = run / "backbone" / trajectory["scenario_id"] / "result.json"
    binding = digest({"trajectory": trajectory, "scenario": scenario, "backbones": specs,
                      "adapter": sha(Path(__file__))})
    if path.exists():
        cached = load(path)
        if cached["binding"] != binding:
            raise ValueError("backbone input changed")
        return cached["record"]
    checkpoint = backbone.select_checkpoints([trajectory])[0][1]
    outputs, errors = [], []
    for spec in specs:
        try:
            outputs.append(replay.replay(replay.factory(scenario, backbone_spec=spec),
                                         checkpoint["environment_snapshot_before"], checkpoint["policy_action"]))
        except Exception as exc:
            outputs.append(None)
            errors.append({"model_family": spec["model_family"], "type": type(exc).__name__, "message": str(exc)})
    record = {"scenario_id": trajectory["scenario_id"], "source_trajectory_id": trajectory["trajectory_id"],
              "checkpoint_turn_id": checkpoint["turn_id"], "action": checkpoint["policy_action"]["text"],
              "comparison": failed_comparison() if errors else compare_transitions(*outputs),
              "appraisals": [o["appraisal"] if o else None for o in outputs],
              "calibrations": [o.get("calibration", {}) if o else None for o in outputs],
              "replay_errors": errors, "replay_scope": "appraisal_and_state_transition"}
    save(path, {"binding": binding, "record": record})
    return record


def run_gate2(run, workers, limit):
    plans, config = materialize(run)
    scenarios = {p["case"]["scenario_id"]: p["scenario"] for p in plans}
    trajectories = probes.select_one_per_scenario(probes.load_records(run / "rollouts"), None)
    args = ["--batch-root", str(run), "--scenario-root", str(run / "scenarios"),
            "--rollout-root", str(run / "rollouts"), "--rollout-config", str(run / "rollout.runtime.json"),
            "--all-scenarios", "--prepare-only"]
    gate2.main(args)
    old_path = ACTIVE / "gate2_followup/gate2/experiments/environment_interventions.json"
    old = load(old_path)["records"]
    # Reuse only same trajectory/checkpoint and same unified environment plan.
    previous_config = load(ACTIVE / "gate2_followup/rollout.runtime.json")
    def comparable_environment(value):
        result = deepcopy(value)
        for key in ("provider", "response_provider", "state_appraisal_provider", "interaction_appraisal_provider"):
            result[key] = public_provider_config(result[key])
        return result
    if comparable_environment(previous_config["environment"]) != comparable_environment(load(run / "rollout.runtime.json")["environment"]):
        raise ValueError("old probe runtime differs from current frozen runtime")
    by_id = {t["scenario_id"]: t for t in trajectories}
    reusable = [r for r in probes._latest_successful_records(old, probes.EXPERIMENT_VERSION)
                if r["scenario_id"] in by_id
                and r["source_trajectory_id"] == by_id[r["scenario_id"]]["trajectory_id"]
                and r["checkpoint_turn_id"] == probes.select_intervention_checkpoint(by_id[r["scenario_id"]])["turn_id"]]
    save(run / "reused_interventions.json", {"source": str(old_path.relative_to(ROOT)), "sha256": sha(old_path),
                                          "records": reusable, "original_attempts_including_errors": old})
    ready = {r["scenario_id"] for r in reusable}
    replay = Replay(plans, run / "replay")
    primary = bounded(ModelRoutes.load(ROOT / "configs/gpt50_experiment/model_routes.hybrid.v3_2.json").provider_config("quality_review"))
    secondary = bounded(config["environment"]["response_provider"])
    if secondary.get("provider") == "failover":
        secondary = secondary["candidates"][0]
    specs = [{"model_family": "gpt", "provider": primary, "sampling": {"temperature": 0, "seed": 73101}},
             {"model_family": "claude", "provider": secondary, "sampling": {"temperature": 0, "seed": 73102}}]
    if "claude" not in secondary["model"].lower():
        raise ValueError("second backbone must be a different model family")
    save(run / "gate2/backbone_config.runtime.json", {"backbones": specs,
         "appraisal_prompt_id": plans[0]["environment"]["state_appraisal_prompt_id"],
         "state_calibration_profile": plans[0]["environment"]["state_calibration_profile"]})
    selected = trajectories[:limit] if limit else trajectories
    jobs = [("interventions", t) for t in selected if t["scenario_id"] not in ready]
    jobs += [("backbone", t) for t in selected]
    with patch.object(probes, "ModelEnvironmentFactory", replay.factory), patch.object(probes, "_replay", replay.replay):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(intervention_job, t, scenarios, config, replay, run) if kind == "interventions"
                       else pool.submit(backbone_job, t, scenarios[t["scenario_id"]], replay, specs, run): (kind, t["scenario_id"])
                       for kind, t in jobs}
            for future in as_completed(futures):
                kind, sid = futures[future]
                try:
                    result = future.result()
                    print(kind, sid, "error" if result.get("error") or result.get("replay_errors") else "executed", flush=True)
                except Exception as exc:
                    save(run / "failures" / (kind + "-" + sid + ".json"), {"error": str(exc), "type": type(exc).__name__})
                    print(kind, sid, type(exc).__name__, str(exc)[:200], flush=True)
                aggregate_gate2(run, trajectories, reusable, specs, plans)


def aggregate_gate2(run, trajectories, reused, specs, plans):
    records = reused + [load(p)["record"] for p in sorted((run / "probes").glob("*/result.json"))]
    # Retain partial experiments independently: an E7 transport failure must not
    # hide a successfully executed E3/E4/E5.
    partial = [{k: v for k, v in r.items() if k != "error"} for r in records]
    provenance = {"source": str(ACTIVE.relative_to(ROOT)), "factory_adapter": "UnifiedEnvironmentFactory",
                  "state_prompt": plans[0]["environment"]["state_appraisal_prompt_id"],
                  "experiment_version": probes.EXPERIMENT_VERSION,
                  "reused_evidence": str((run / "reused_interventions.json").relative_to(ROOT))}
    probes.write_evidence(run / "gate2", partial, provenance)
    save(run / "gate2/experiments/environment_interventions.json", {"records": records})
    b_records = [load(p)["record"] for p in sorted((run / "backbone").glob("*/result.json"))]
    summary = summarize_backbone_sensitivity(b_records) if b_records else {}
    save(run / "gate2/backbone_sensitivity.json", {
        "format": "socialflux_backbone_sensitivity_v1", "experiment_version": backbone.EXPERIMENT_VERSION,
        "backbones": [{**s, "provider": public_provider_config(s["provider"])} for s in specs],
        "appraisal_prompt_id": plans[0]["environment"]["state_appraisal_prompt_id"],
        "state_calibration_profile": plans[0]["environment"]["state_calibration_profile"],
        "input_scenario_ids": sorted(t["scenario_id"] for t in trajectories),
        "input_trajectory_ids": sorted(t["trajectory_id"] for t in trajectories),
        "record": summary, "records": b_records})
    save(run / "progress.json", {"updated_at": now(), "expected_readable_sources": len(trajectories),
         "intervention_groups": len(records), "intervention_errors": sum(bool(r.get("error")) for r in records),
         "subexperiment_counts": {key: sum(key in r for r in records) for key in ("e3", "e4", "e5", "e7")},
         "backbone_groups": len(b_records), "backbone_errors": sum(bool(r.get("replay_errors")) for r in b_records),
         "human_review": "pending", "formal_admission": False})


def run_gate3(run, workers, limit):
    primary_path = ACTIVE / "gate3_followup/gate3/model_reviews.json"
    primary = load(primary_path)["records"]
    rows = source_rows(ACTIVE / "gate3_followup", len(primary))
    index = {r["scenario_id"]: r for r in primary}
    # Stable 20% (rounded up), plus every reject/borderline result.
    sample = sorted(rows, key=lambda r: digest(r["trajectory_id"]))[:(len(rows) + 4) // 5]
    selected_ids = {r["scenario_id"] for r in sample} | {
        r["scenario_id"] for r in primary if r["decision"] != "approve" or min(r["scores"].values()) <= 3}
    selected = [r for r in rows if r["scenario_id"] in selected_ids]
    if limit:
        selected = selected[:limit]
    config = load(ACTIVE / "gate2_followup/rollout.runtime.json")["environment"]["response_provider"]
    if config.get("provider") == "failover":
        config = config["candidates"][0]
    config = bounded(config)
    config["max_tokens"] = 3500
    save(run / "audit_selection.json", {"primary_path": str(primary_path.relative_to(ROOT)),
        "primary_sha256": sha(primary_path), "selection": "stable_sha256_20_percent_plus_all_rejects_and_scores_at_most_3",
        "selected_scenarios": sorted(selected_ids), "provider": public_provider_config(config),
        "primary_count": len(primary), "unreadable_original_sources": 50 - len(primary)})
    def job(row):
        trajectory, scenario = load(row["trajectory_path"]), load(row["scenario_path"])
        packet = public_judge_packet(trajectory, scenario)
        prompt = render_prompt("rollout_quality_judge_v2", packet)
        data = json_call(run, "reviews/" + row["scenario_id"],
                        "Independently review this fictional benchmark rollout. Return only the requested JSON.",
                        {"review_request": prompt}, config,
                        lambda x: validate_judgment(x, trajectory["trajectory_id"],
                                                    {t["turn_id"] for t in trajectory["turns"]}), 3500)
        result = {**data, **{k: v for k, v in row.items() if not isinstance(v, Path)},
                  "decision": decision(data), "primary_decision": index[row["scenario_id"]]["decision"],
                  "reviewer_type": "independent_second_model_not_human", "model": config["model"]}
        save(run / "records" / (row["scenario_id"] + ".json"), result)
        return result
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(job, row): row["scenario_id"] for row in selected}
        for future in as_completed(futures):
            sid = futures[future]
            try:
                r = future.result()
                print("gate3", sid, r["decision"], flush=True)
            except Exception as exc:
                save(run / "failures" / (sid + ".json"), {"type": type(exc).__name__, "error": str(exc)})
                print("gate3", sid, "FAILED", str(exc)[:200], flush=True)
            records = [load(p) for p in sorted((run / "records").glob("*.json"))]
            save(run / "progress.json", {"updated_at": now(), "expected_audit_count": len(selected_ids),
                 "reviewed": len(records), "decision_counts": dict(Counter(r["decision"] for r in records)),
                 "disagreements": [r["scenario_id"] for r in records if r["decision"] != r["primary_decision"]],
                 "human_review": "pending", "records": records})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", choices=("2", "3"), required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output")
    args = parser.parse_args()
    run = ROOT / (args.output or ("data/gate" + args.gate + "_machine_20261020"))
    run.mkdir(parents=True, exist_ok=True)
    freeze = {"source": str(ACTIVE.relative_to(ROOT)), "code_sha256": sha(Path(__file__)),
              "source_preregistration_sha256": sha(ACTIVE / "preregistration.json")}
    path = run / "freeze.json"
    if path.exists() and load(path) != freeze:
        raise ValueError("frozen run changed; choose a new output directory")
    save(path, freeze)
    (run_gate2 if args.gate == "2" else run_gate3)(run, args.workers, args.limit)


if __name__ == "__main__":
    main()
