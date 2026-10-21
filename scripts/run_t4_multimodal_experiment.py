#!/usr/bin/env python3
"""Run a frozen GPT50 cohort under paired text/video policies with complete assets."""

import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from copy import deepcopy
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.t4_asset_coverage import audit_asset_coverage, require_complete_assets
from evaluation.t4_batch import save, digest, summarize, aggregate_scores
from evaluation.t4_human_review import export_human_review
from evaluation.t4_media import extract_frames
from evaluation.t4_multimodal import RequestBudget, AuditedProvider, AssetPolicy, prepare_controls, probe_model, assess_run_health
from environment.online_multimodal import build_online_multimodal_profile
from environment.unified_appraisal import UnifiedEnvironmentFactory
from pipeline.runtime import build_environment_factory
from providers.model_routes import ModelRoutes
from providers.factory import public_provider_config
from rollout.configuration import load_rollout_config
from rollout.runner import RolloutRunner
from tasks.T4.answering import generate_judgment


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def model_configs(config):
    result = {}
    for entry in config["models"]:
        route = ModelRoutes.load(entry["routes"]).provider_config("t4_judge")
        route.update(entry.get("overrides", {}))
        route.update(max_transport_attempts=1, timeout=config.get("provider_timeout_seconds", 360))
        result[entry["id"]] = route
    return result


def policy_configs(config, providers):
    """Select evaluated policies without changing environment or judge routes."""
    names = config.get("policy_models", list(providers))
    if (not isinstance(names, list) or not names
            or any(not isinstance(name, str) for name in names)
            or len(set(names)) != len(names)
            or set(names) - set(providers)):
        raise ValueError("policy_models must name a nonempty unique subset of configured models")
    return {name: providers[name] for name in names}


def environment_for_episode(base_env, config, source_index):
    """Distribute the same environment models across existing credential routes."""
    env, slots = deepcopy(base_env), {}
    allowed = {"api_key_file", "api_key_env"}
    for role, keys in (("appraisal", ("provider", "state_appraisal_provider", "interaction_appraisal_provider")),
                       ("response", ("response_provider",))):
        routes = config.get("environment_credential_routes", {}).get(role, [])
        if not routes:
            continue
        if any(not isinstance(r, dict) or not r or set(r) - allowed for r in routes):
            raise ValueError("environment credential routes may only change secret references")
        slot = source_index % len(routes)
        slots[role] = slot
        for key in keys:
            env[key] = {k: v for k, v in env[key].items()
                        if k not in {"api_key", "api_keys", "api_key_env", "api_key_file", "api_key_files"}}
            env[key].update(routes[slot])
    return env, slots


def configure_media_completion(base_env, config):
    """Apply an explicitly versioned ending rule to both paired conditions."""
    name = config.get("media_completion_policy", "natural_v1")
    if name not in {"natural_v1", "first_event_response_v1"}:
        raise ValueError("unknown media_completion_policy")
    env = deepcopy(base_env)
    if name == "first_event_response_v1":
        if env.get("multimodal_trigger_policy", {}).get("profile") != "online_multimodal_v2":
            raise ValueError("first_event_response_v1 requires online_multimodal_v2")
        env["multimodal_trigger_policy"]["defer_first_media_completion"] = True
    return env


def policy_sampling(config, source_index):
    """Keep paired sampling equal while allowing a seedless API diagnostic."""
    mode = config.get("policy_seed_mode", "scenario_seed_v1")
    if mode not in {"scenario_seed_v1", "omit"}:
        raise ValueError("unknown policy_seed_mode")
    sampling = {"temperature": 0.6, "top_p": 0.9}
    if mode == "scenario_seed_v1":
        sampling["seed"] = 8600 + source_index
    return sampling


def run_capability_probes(providers, out, budget):
    controls = prepare_controls(out / "controls")
    with ThreadPoolExecutor(max_workers=min(3, len(providers))) as pool:
        futures = {name: pool.submit(probe_model, provider, out / "capabilities" / name, budget, controls)
                   for name, provider in providers.items()}
        capabilities = {name: future.result() for name, future in futures.items()}
    save(out / "capabilities.json", capabilities)
    return capabilities


def select_cohort(scenarios, inventory, scenario_ids=None):
    """An explicit subset may shrink scope; every selected scene still needs all media."""
    by_id = {s["scenario_id"]: s for s in scenarios}
    if len(by_id) != len(scenarios):
        raise ValueError("duplicate source scenario IDs")
    if scenario_ids is None:
        if len(scenarios) != 50:
            raise ValueError("the default experiment requires exactly 50 distinct GPT50 scenarios")
        scenario_ids = list(by_id)
    if not isinstance(scenario_ids, list) or not scenario_ids or len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("scenario_ids must be an explicit nonempty list of unique IDs")
    if set(scenario_ids) - set(by_id):
        raise ValueError("selected scenario missing from source manifest")
    selected = [by_id[sid] for sid in scenario_ids]
    media = {**inventory, "requests": [r for r in inventory["requests"] if r["scenario_id"] in set(scenario_ids)]}
    return selected, media


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--probe-only", action="store_true", help="Validate model media transport without scenario rollouts")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        providers = model_configs(config)
        policies = policy_configs(config, providers)
        policy_sampling(config, 0)
        source = json.loads(Path(config["scenario_manifest"]).read_text())
        scenarios = [json.loads(Path(r["candidate"]).read_text()) for r in source["cases"]]
        source_indices = {s["scenario_id"]: index for index, s in enumerate(scenarios)}
        inventory = json.loads(Path(config["video_manifest"]).read_text())
        scenarios, inventory = select_cohort(scenarios, inventory, config.get("scenario_ids"))
        cohort_size = len(scenarios)
        base_env = load_rollout_config(config["environment_config"])["environment"]
        base_env.update(minimum_natural_turns=1, horizon_mode="natural_max_20",
                        provider=providers["gpt"], state_appraisal_provider=providers["gpt"],
                        interaction_appraisal_provider=providers["gpt"], response_provider=providers["claude"])
        for key in ("provider", "state_appraisal_provider", "interaction_appraisal_provider"):
            base_env[key] = {**base_env[key], "max_tokens": 6500}
        base_env["response_provider"] = {**base_env["response_provider"], "max_tokens": 6000}
        base_env = configure_media_completion(base_env, config)
        for scenario in scenarios:
            scenario_env, _ = environment_for_episode(base_env, config, source_indices[scenario["scenario_id"]])
            UnifiedEnvironmentFactory(build_environment_factory(scenario, scenario_env))()
        plan = {"status": "prepared_waiting_for_all_videos", "config": config,
                "scenario_sha256": {s["scenario_id"]: digest(s) for s in scenarios},
                "cohort_size": cohort_size, "source_indices": {s["scenario_id"]: source_indices[s["scenario_id"]] for s in scenarios},
                "providers": {k: public_provider_config(v) for k, v in providers.items()},
                "policy_prompt": "task_t4_action_v21", "max_turns": 20, "minimum_natural_turns": 1,
                "environment": "canonical UnifiedEnvironmentFactory / StatefulEnvironment",
                "human_validation_status": "not_human_validated", "formal_admission": False,
                "primary_comparison": "within-model paired end-to-end text_video minus text_only on the same scenario",
                "interpretation": "Exploratory study; divergent trajectories estimate total condition effect, not a matched-checkpoint causal effect."}
        if "media_completion_policy" in config:
            plan["media_completion_policy"] = config["media_completion_policy"]
        if (out / "plan.json").exists() and json.loads((out / "plan.json").read_text()) != plan:
            raise ValueError("frozen experiment plan changed")
        save(out / "plan.json", plan)
        if args.prepare_only:
            print(f"Validated {cohort_size} scenarios and paired experiment configuration; no API calls.")
            return
        if args.probe_only:
            budget = RequestBudget(out / "request_budget.json", config["request_budget"])
            save(out / "status.json", {"status": "probing_model_media_inputs", "updated_at": now()})
            capabilities = run_capability_probes(policies, out, budget)
            save(out / "status.json", {"status": "probes_complete_waiting_for_all_videos", "updated_at": now(),
                 "api_requests": budget.count, "capabilities": capabilities, "scenario_episodes_started": False})
            return
        coverage = audit_asset_coverage(inventory, config["video_batch_root"], expected_scenarios=cohort_size)
        save(out / "asset_coverage.json", coverage)
        require_complete_assets(coverage)
        save(out / "status.json", {"status": "preparing_video_frames", "updated_at": now(), "cohort_size": cohort_size})
        assets, event_assets = {}, {}
        for record in inventory["requests"]:
            path = (Path(config["video_batch_root"]) / record["video_file"]).resolve()
            assets[record["media_asset_id"]] = {"path": str(path), "sha256": record["video_sha256"],
                "frames": extract_frames(path, Path(config.get("frame_cache", out / "frames")) / record["video_sha256"])}
            event_assets.setdefault(record["scenario_id"], {})[record["event_family"]] = {
                "media_asset_id": record["media_asset_id"], "asset_path": str(path),
                "asset_url": None, "duration_seconds": 4}
        base_env["multimodal_trigger_policy"]["event_assets"] = event_assets
        for scenario in scenarios:
            profile = build_online_multimodal_profile(scenario, event_assets)
            if any(t["media_asset_id"] not in assets for t in profile["triggers"]):
                raise ValueError("current scenario triggers require assets absent from the completed inventory")
        code_paths = [p for folder in ("environment", "policies", "providers", "rollout", "evaluation", "prompts", "schemas")
                      for p in Path(folder).rglob("*") if p.is_file() and p.suffix in {".py", ".md", ".json", ".txt"}]
        code_paths.append(Path(__file__))
        freeze = {"plan_sha256": digest(plan), "assets": assets,
                  "code_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in code_paths},
                  "environment_config_sha256": digest(base_env)}
        prereg = out / "preregistration.json"
        if prereg.exists() and json.loads(prereg.read_text()) != freeze:
            raise ValueError("frozen experiment inputs or code changed")
        save(prereg, freeze)
        budget = RequestBudget(out / "request_budget.json", config["request_budget"])
        save(out / "status.json", {"status": "probing_model_media_inputs", "updated_at": now(), "cohort_size": cohort_size})
        capabilities = run_capability_probes(policies, out, budget)
        rows = []

        def run_one(index, scenario, name, condition):
            directory = out / "episodes" / scenario["scenario_id"] / name / condition
            result_file = directory / "result.json"
            if result_file.exists():
                return json.loads(result_file.read_text())
            transport = capabilities[name]["selected_transport"]
            row = {"scenario_id": scenario["scenario_id"], "model_id": name,
                   "condition": condition, "transport": transport if condition == "text_video" else None,
                   "modality": {"policy_condition": condition}, "started_at": now()}
            if condition == "text_video" and not transport:
                row.update(status="unsupported_video_input", error="model did not pass temporal media controls")
                save(result_file, row)
                return row
            if (directory / "checkpoint.json").exists():
                row.update(status="interrupted_retained", error="existing partial trajectory retained; no resampling")
                save(result_file, row)
                return row
            env, row["environment_route_slots"] = environment_for_episode(
                base_env, config, source_indices[scenario["scenario_id"]])
            factory = UnifiedEnvironmentFactory(build_environment_factory(scenario, env))
            provider = AuditedProvider({**providers[name], "max_tokens": 1800}, directory / "calls" / "policy", budget,
                                       max_attempts=config.get("audited_transport_attempts", 1))
            called_providers = {"policy": provider}
            policy = AssetPolicy(f"t4_{scenario['scenario_id']}_{name}", provider,
                    prompt_id="task_t4_action_v21", validation_profile="hard_only", minimum_natural_turns=1,
                    sampling=policy_sampling(config, source_indices[scenario["scenario_id"]]),
                    observation_condition=condition, media_input_format="openai_video_url" if condition == "text_video" else None,
                    assets=assets, transport=transport, audit_path=directory / "video_deliveries.json")

            def audited_environment():
                environment = factory()
                # Replace only provider transport; keep the canonical appraisers,
                # response generation, deterministic updater, and ledger intact.
                for role, key in (("state", "state_appraisal_provider"), ("interaction", "interaction_appraisal_provider"), ("response", "response_provider")):
                    called_providers[role] = AuditedProvider(env[key], directory / "calls" / role, budget,
                        max_attempts=config.get("audited_transport_attempts", 1))
                environment.state_updater.state_appraiser.provider.provider = called_providers["state"]
                environment.state_updater.interaction_appraiser.provider = called_providers["interaction"]
                environment.response_generator.provider = called_providers["response"]
                return environment
            try:
                trajectory = RolloutRunner(audited_environment, checkpoint_writer=lambda value: save(directory / "checkpoint.json", value)).run(policy, max_turns=20)
                save(directory / "trajectory.json", trajectory)
                row["human_review"] = export_human_review(
                    trajectory, scenario, directory, out / "human_review")
                judge = AuditedProvider({**providers[config["judge"]], "max_tokens": 4000}, directory / "calls" / "judge", budget,
                    max_attempts=config.get("audited_transport_attempts", 1))
                called_providers["judge"] = judge
                packet, judgment, _ = generate_judgment(judge, trajectory, scenario, 7401, max_attempts=2)
                row.update(status="completed", observed_turns=len(trajectory["turns"]), ending=trajectory["ending"],
                    scores=aggregate_scores(judgment), judgment=judgment, judge_packet=packet,
                    video_delivery_count=len(policy.deliveries), policy_provenance=policy.provenance)
                if condition == "text_video" and not policy.deliveries:
                    row["status"] = "completed_without_video_exposure"
            except Exception as exc:
                row.update(status="failed", error=str(exc))
                if hasattr(exc, "partial_trajectory"):
                    save(directory / "partial_trajectory.json", exc.partial_trajectory)
            row["finished_at"] = now()
            row["provider_metrics"] = {"request_count": sum(p.metrics.get("request_count", 0) for p in called_providers.values()),
                                       "by_role": {k: p.metrics for k, p in called_providers.items()}}
            save(result_file, row)
            return row

        # A bounded initial block makes implementation failures visible before
        # the rest of the dataset is scheduled. No outcomes are filtered.
        block_size = config.get("scenario_block_size", 2)
        if not isinstance(block_size, int) or block_size < 1:
            raise ValueError("scenario_block_size must be a positive integer")
        pilot_size = min(block_size, cohort_size)
        for block_start in range(0, cohort_size, pilot_size):
            indices = range(block_start, min(block_start + pilot_size, cohort_size))
            block_rows = []
            with ThreadPoolExecutor(max_workers=config["workers"]) as pool:
                pending = {pool.submit(run_one, i, scenarios[i], name, condition): (i, name, condition)
                           for i in indices for name in policies for condition in ("text_only", "text_video")}
                while pending:
                    done, _ = wait(pending, timeout=30, return_when=FIRST_COMPLETED)
                    for future in done:
                        i, name, condition = pending.pop(future)
                        try:
                            row = future.result()
                        except Exception as exc:
                            row = {"scenario_id": scenarios[i]["scenario_id"], "model_id": name,
                                   "condition": condition, "status": "runner_failed", "error": str(exc)}
                        rows.append(row)
                        block_rows.append(row)
                        save(out / "results.json", rows)
                    summaries = {name: summarize([r for r in rows if r["model_id"] == name]) for name in policies}
                    save(out / "summary.json", summaries)
                    save(out / "status.json", {"status": "running", "updated_at": now(),
                         "finished": len(rows), "planned": cohort_size * len(policies) * 2,
                         "api_requests": budget.count, "models": summaries})
            health = assess_run_health(
                block_rows, [name for name in policies if capabilities[name]["selected_transport"]],
                max_failure_fraction=config.get("max_episode_failure_fraction", 0.2),
                require_pairs=block_start == 0,
            )
            save(out / "health_checks" / f"{block_start:04d}.json", health)
            if config.get("stop_on_health_gate", True) and not health["passed"]:
                save(out / "status.json", {"status": "stopped_health_gate", "updated_at": now(),
                     "finished": len(rows), "planned": cohort_size * len(policies) * 2,
                     "api_requests": budget.count, "health": health})
                return
        save(out / "status.json", {"status": "completed_with_recorded_outcomes", "updated_at": now(),
             "finished": len(rows), "planned": cohort_size * len(policies) * 2, "api_requests": budget.count})
        lines = ["GPT50 T4 text / text+video 多 API 配对实验", f"完成时间：{now()}",
                 "完整结果与失败见 results.json；五维分数及配对差值见 summary.json。",
                 "所有统计按被测模型分组；不支持视觉输入与未触发视频的轨迹单独标记。",
                 "video_frames 代表 4 个带时间戳的视频帧，不含音频；native_video 代表直接发送真实视频。",
                 "人工审核与校准尚未完成，结果为探索性机器实验，不代表正式研究结论。"]
        (out / "report.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
