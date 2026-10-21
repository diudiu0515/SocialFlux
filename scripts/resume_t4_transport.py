#!/usr/bin/env python3
"""Continue failed T4 transport, replaying every earlier response exactly.

Run with T4_FROZEN_RUNTIME pointing at the original runtime. Source artifacts
are immutable; the destination contains the original outcomes plus continuations.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from time import sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get("T4_FROZEN_RUNTIME", str(ROOT)))
from scripts import run_t4_multimodal_experiment as runner
from evaluation.t4_batch import save, digest, summarize, aggregate_scores
from evaluation.t4_media import compact_media, provider_messages
from evaluation.t4_multimodal import AuditedProvider, RequestBudget, AssetPolicy
from evaluation.t4_human_review import export_human_review
from environment.unified_appraisal import UnifiedEnvironmentFactory
from pipeline.runtime import build_environment_factory
from rollout.configuration import load_rollout_config
from rollout.runner import RolloutRunner
from tasks.T4.answering import generate_judgment


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def retryable(error):
    return any(t in error.lower() for t in (
        "the service is busy", "request could not be completed", "upstream_error",
        "timed out", "timeout", "connection reset", "remote end closed",
        "http 429", "http 500", "http 502", "http 503", "http 504",
        "unterminated string starting at",
    )) and not any(t in error.lower() for t in (
        "json/schema", "truncated", "incompatible", "invalid parameter"))


class ReplayBoundary(RuntimeError):
    pass


def turn_content(turn):
    value = deepcopy(turn)
    # Replayed calls do not recreate network metrics. Their original raw wire
    # evidence is retained in the source; all requests/outputs and state match.
    for key in ("state_appraisal_call", "interaction_appraisal_call"):
        if isinstance(value.get(key), dict):
            value[key].pop("provider_audit_records", None)
    return value


class ExactReplayProvider:
    """Require ordered, exact request equality before reusing saved responses."""
    def __init__(self, config, source, directory, budget, *, dry_run=False):
        self.config, self.directory = config, Path(directory)
        self.provider = AuditedProvider(config, directory, budget)
        self.records = [(p, load(p)) for p in sorted(Path(source).glob("*.json"))]
        self.cursor = 0
        self.dry_run = dry_run
        self.reused = []

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def complete(self, messages, **sampling):
        request = {"messages": compact_media(provider_messages(messages, self.config["provider"])),
                   "sampling": sampling}
        if self.cursor < len(self.records):
            path, old = self.records[self.cursor]
            if digest(request) != digest({k: old[k] for k in request}):
                raise RuntimeError(f"saved request mismatch: {path}")
            self.cursor += 1
            if old["status"] == "completed":
                self.reused.append({"source": str(path), "source_sha256": sha(path),
                                    "request_sha256": digest(request)})
                save(self.directory / "replay.json.audit", self.reused)
                return old["raw_output"]
            if not retryable(old.get("error", "")):
                raise RuntimeError("non-transport failure retained: " + old.get("error", ""))
        if self.dry_run:
            raise ReplayBoundary("exact replay reached missing network output")
        for attempt in range(3):
            try:
                return self.provider.complete(messages, **sampling)
            except Exception as exc:
                if attempt == 2 or not retryable(str(exc)):
                    raise
                sleep(5 * (attempt + 1))


def prepare_environment(config, source):
    providers = runner.model_configs(config)
    manifest = load(config["scenario_manifest"])
    scenarios = {s["scenario_id"]: s for r in manifest["cases"] for s in [load(r["candidate"]) ]}
    plan, prereg = load(source / "plan.json"), load(source / "preregistration.json")
    for sid, expected in plan["scenario_sha256"].items():
        if digest(scenarios[sid]) != expected:
            raise ValueError("source scenario changed: " + sid)
    env = load_rollout_config(config["environment_config"])["environment"]
    env.update(minimum_natural_turns=1, horizon_mode="natural_max_20", provider=providers["gpt"],
               state_appraisal_provider=providers["gpt"], interaction_appraisal_provider=providers["gpt"],
               response_provider=providers["claude"])
    for key in ("provider", "state_appraisal_provider", "interaction_appraisal_provider"):
        env[key] = {**env[key], "max_tokens": 6500}
    env["response_provider"] = {**env["response_provider"], "max_tokens": 6000}
    env = runner.configure_media_completion(env, config)
    inventory = load(config["video_manifest"])
    event_assets = {}
    for record in inventory["requests"]:
        if record["scenario_id"] not in plan["scenario_sha256"]:
            continue
        event_assets.setdefault(record["scenario_id"], {})[record["event_family"]] = {
            "media_asset_id": record["media_asset_id"],
            "asset_path": str((Path(config["video_batch_root"]) / record["video_file"]).resolve()),
            "asset_url": None, "duration_seconds": 4}
    env["multimodal_trigger_policy"]["event_assets"] = event_assets
    if digest(env) != prereg["environment_config_sha256"]:
        raise ValueError("frozen environment configuration changed")
    return providers, scenarios, env, prereg["assets"], plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--request-budget", type=int, default=1500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    if source == out or out.is_relative_to(source):
        raise ValueError("recovery must use an independent output directory")
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = load(source / "plan.json")["config"]
        providers, scenarios, base_env, assets, plan = prepare_environment(config, source)
        rows = load(source / "results.json")
        selected = [r for r in rows if r["status"] == "failed" and retryable(r.get("error", ""))]
        source_files = {str(p.relative_to(source)): sha(p) for p in source.rglob("*") if p.is_file()}
        manifest = {"source": str(source), "source_sha256": source_files,
            "selected": [{k: r[k] for k in ("scenario_id", "model_id", "condition", "error")} for r in selected],
            "selection": "all transport-failed episodes, independent of scores",
            "max_transport_attempts": 3, "script_sha256": sha(__file__),
            "source_api_requests": load(source / "request_budget.json")["request_count"],
            "new_request_limit": args.request_budget, "protocol_changed": False}
        frozen = out / "recovery_manifest.json"
        if frozen.exists() and load(frozen) != manifest:
            raise ValueError("recovery inputs changed")
        save(frozen, manifest)
        if not (out / "plan.json").exists():
            for name in ("plan.json", "preregistration.json", "capabilities.json", "asset_coverage.json"):
                shutil.copy2(source / name, out / name)
            shutil.copytree(source / "capabilities", out / "capabilities", dirs_exist_ok=True)
            shutil.copytree(source / "episodes", out / "episodes", dirs_exist_ok=True)
        budget = RequestBudget(out / "request_budget.json", args.request_budget)
        outcomes = {}

        def run_one(old):
            sid, name, condition = (old[k] for k in ("scenario_id", "model_id", "condition"))
            src = source / "episodes" / sid / name / condition
            directory = out / "episodes" / sid / name / condition
            marker = directory / "continuation.json"
            if marker.exists():
                return load(marker)
            save(marker, {"status": "interrupted_retained", "source_status": old["status"],
                          "started_at": runner.now(), "reason": "one bounded continuation only"})
            checkpoint = load(src / "checkpoint.json")
            scenario = scenarios[sid]
            env, slots = runner.environment_for_episode(base_env, config, plan["source_indices"][sid])
            used = {}

            def provider(role, settings):
                p = ExactReplayProvider(settings, src / "calls" / role, directory / "calls" / role,
                                        budget, dry_run=args.dry_run)
                used[role] = p
                return p

            policy = AssetPolicy(f"t4_{sid}_{name}", provider("policy", {**providers[name], "max_tokens": 1800}),
                prompt_id="task_t4_action_v21", validation_profile="hard_only", minimum_natural_turns=1,
                sampling=runner.policy_sampling(config, plan["source_indices"][sid]),
                observation_condition=condition, media_input_format="openai_video_url" if condition == "text_video" else None,
                assets=assets, transport=load(source / "capabilities" / name / "result.json")["selected_transport"],
                audit_path=directory / "video_deliveries.json")
            factory = UnifiedEnvironmentFactory(build_environment_factory(scenario, env))

            def environment():
                instance = factory()
                original_reset = instance.reset
                instance.reset = lambda **kw: original_reset(episode_id=checkpoint["trajectory_id"], **kw)
                instance.state_updater.state_appraiser.provider.provider = provider("state", env["state_appraisal_provider"])
                instance.state_updater.interaction_appraiser.provider = provider("interaction", env["interaction_appraisal_provider"])
                instance.response_generator.provider = provider("response", env["response_provider"])
                return instance

            def save_checkpoint(value):
                prefix = checkpoint.get("turns", [])
                for index, turn in enumerate(value.get("turns", [])[:len(prefix)]):
                    if digest(turn_content(turn)) != digest(turn_content(prefix[index])):
                        save(directory / "replay_mismatch.json", {"turn_index": index,
                            "changed_fields": {key: {"original": prefix[index].get(key), "replayed": turn.get(key)}
                                for key in set(turn) | set(prefix[index]) if turn.get(key) != prefix[index].get(key)}})
                        raise RuntimeError(f"replayed completed turn changed: {sid}/{name}/{condition}/{index}")
                    value["turns"][index] = deepcopy(prefix[index])
                save(directory / "checkpoint.json", value)

            result = deepcopy(old)
            outcome = {"started_at": runner.now(), "source_status": old["status"], "source_error": old["error"]}
            try:
                trajectory = RolloutRunner(environment, checkpoint_writer=save_checkpoint).run(policy, max_turns=20)
                save_checkpoint(trajectory)
                if any(p.cursor != len(p.records) for p in used.values()):
                    raise RuntimeError("trajectory ended before consuming the saved call prefix")
                save(directory / "trajectory.json", trajectory)
                result["human_review"] = export_human_review(trajectory, scenario, directory, out / "human_review")
                judge = provider("judge", {**providers[config["judge"]], "max_tokens": 4000})
                packet, judgment, _ = generate_judgment(judge, trajectory, scenario, 7401, max_attempts=2)
                result.update(status="completed", observed_turns=len(trajectory["turns"]), ending=trajectory["ending"],
                    scores=aggregate_scores(judgment), judgment=judgment, judge_packet=packet,
                    video_delivery_count=len(policy.deliveries), policy_provenance=policy.provenance)
                if condition == "text_video" and not policy.deliveries:
                    result["status"] = "completed_without_video_exposure"
                result.pop("error", None)
                outcome["status"] = result["status"]
            except ReplayBoundary:
                outcome["status"] = "exact_replay_verified_to_network_boundary"
            except Exception as exc:
                outcome.update(status="failed", error=str(exc))
                result.update(status="failed", error=str(exc))
            outcome.update(finished_at=runner.now(), replayed_calls=sum(len(p.reused) for p in used.values()),
                           new_api_requests=sum(p.metrics.get("request_count", 0) for p in used.values()))
            if not args.dry_run:
                result.update(finished_at=runner.now(), transport_continuation=outcome)
                save(directory / "result.json", result)
            save(marker, outcome)
            return outcome

        def snapshot(status):
            effective = [load(out / "episodes" / r["scenario_id"] / r["model_id"] / r["condition"] / "result.json") for r in rows]
            summaries = {n: summarize([r for r in effective if r["model_id"] == n]) for n in config["policy_models"]}
            save(out / "results.json", effective)
            save(out / "summary.json", summaries)
            save(out / "status.json", {"status": status, "updated_at": runner.now(),
                 "finished": len(outcomes), "planned": len(selected), "inherited_slots": len(rows),
                 "api_requests": budget.count, "source_api_requests": manifest["source_api_requests"],
                 "outcomes": outcomes, "dry_run": args.dry_run})

        snapshot("running")
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            pending = {pool.submit(run_one, row): "/".join(row[k] for k in ("scenario_id", "model_id", "condition")) for row in selected}
            while pending:
                done, _ = wait(pending, timeout=30, return_when=FIRST_COMPLETED)
                for future in done:
                    key = pending.pop(future)
                    try:
                        outcomes[key] = future.result()
                    except Exception as exc:
                        outcomes[key] = {"status": "runner_failed", "error": str(exc)}
                snapshot("running")
        if any(sha(source / p) != expected for p, expected in source_files.items()):
            raise RuntimeError("source artifacts changed during continuation")
        snapshot("completed_with_recorded_outcomes")


if __name__ == "__main__":
    main()
