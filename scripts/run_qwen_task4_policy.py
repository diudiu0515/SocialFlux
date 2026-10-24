#!/usr/bin/env python3
"""Run a tested policy against a frozen Qwen Task4 canonical environment."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_run(run, scenario_id):
    manifest = json.loads((run / "manifest.json").read_text())
    runtime = run / "runtime"
    for relative, expected in manifest["runtime_sha256"].items():
        if sha(runtime / relative) != expected:
            raise ValueError("Frozen runtime changed: " + relative)
    if sha(run / "catalog.json") != manifest["scenario_catalog_sha256"]:
        raise ValueError("Frozen scenario catalog changed")
    entry = json.loads((run / "catalog.json").read_text())["scenarios"][scenario_id]
    if sha(entry["path"]) != entry["sha256"]:
        raise ValueError("Frozen scenario changed")
    scenario = json.loads(Path(entry["path"]).read_text())
    if scenario["scenario_id"] != scenario_id:
        raise ValueError("Scenario ID mismatch")
    return runtime, scenario


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="Immutable prepared Qwen run")
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--policy", type=Path, required=True, help="Existing build_policy JSON specification")
    parser.add_argument("--output", type=Path, required=True, help="New private artifact directory")
    parser.add_argument("--max-turns", type=int, choices=range(1, 21), default=20)
    args = parser.parse_args()
    run = args.run.resolve()
    runtime, scenario = checked_run(run, args.scenario_id)
    policy_bytes = args.policy.read_bytes()
    spec = json.loads(policy_bytes)
    # All domain code comes from the verified frozen runtime. This CLI is only
    # orchestration; RolloutRunner owns public observations and failure handling.
    sys.path.insert(0, str(runtime))
    from environment.qwen_task4 import QwenTask4EnvironmentFactory, request_providers
    from pipeline.runtime import build_policy
    from rollout.runner import RolloutRunner
    from shared.artifacts import atomic_json

    factory = QwenTask4EnvironmentFactory(scenario)
    policy = build_policy(spec)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "manifest.json", {
        "service_run": str(run), "service_manifest_sha256": sha(run / "manifest.json"),
        "driver_sha256": sha(__file__), "policy_spec_sha256": hashlib.sha256(policy_bytes).hexdigest(),
        "policy_provenance": policy.provenance, "environment_provenance": factory.provenance,
        "scenario_id": args.scenario_id, "max_turns": args.max_turns,
        "formal_admission": False, "reward_status": "unconfigured",
        "automatic_replay": False,
    })
    environment = factory()
    runner = RolloutRunner(lambda: environment, max_action_grounding_attempts=1,
                           checkpoint_writer=lambda row: atomic_json(output / "trajectory.json", row))
    started = time.monotonic()
    summary = {"status": "running", "formal_admission": False}
    atomic_json(output / "summary.json", summary)
    try:
        trajectory = runner.run(policy, max_turns=args.max_turns)
        ending = environment.session.get("ending") or {}
        summary.update(status="completed" if ending.get("reason") == "natural_completion"
                       else "budget_truncated", turns=len(trajectory["turns"]), ending=ending)
    except Exception as exc:
        summary.update(status="failed", error_type=type(exc).__name__,
                       turns=len(environment.private_trajectory().get("turns", [])))
        atomic_json(output / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
    finally:
        providers = {"policy": policy.provider, **request_providers(environment)}
        for name, provider in providers.items():
            atomic_json(output / (name + "_requests.json"), list(getattr(provider, "audit_records", [])))
        summary.update(seconds=round(time.monotonic() - started, 3),
                       provider_metrics={name: provider.metrics for name, provider in providers.items()})
        atomic_json(output / "summary.json", summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "provider_metrics"}))
    return 1 if summary["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
