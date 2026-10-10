#!/usr/bin/env python3
"""One budget-only recovery per truncated response, replaying its exact saved prefix."""
import argparse
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_unified_three_pilot as pilot
from scripts.run_unified_exploratory_pilot import OUT as SOURCE, prepare
from scripts.validate_state_context_samples import load, save, BASE
from environment.unified_appraisal import UnifiedEnvironmentFactory
from pipeline.runtime import build_environment_factory, build_policy
from rollout.runner import RolloutRunner
from evaluation.rollout_gate import audit_rollout

OUT = BASE / "unified_current_trust_v1_response_budget_recovery"
BUDGET = 6000


class ReplayPrefixProvider:
    def __init__(self, provider, records, source, *, response=False, failed=None):
        self.provider, self.records, self.source = provider, deepcopy(records), str(source)
        self.response, self.failed = response, deepcopy(failed)
        self.cursor = 0
        self.replayed_audits = []
        self.prior_audit_count = 0
        self.failed_request_matched = False

    def __getattr__(self, name):
        return getattr(self.provider, name)

    @property
    def audit_records(self):
        return self.replayed_audits + list(getattr(self.provider, "audit_records", []))

    def check(self, record, messages, generation):
        if messages != record["messages"]:
            raise ValueError("Saved-prefix messages changed: " + self.source)
        expected, actual = deepcopy(record["generation"]), deepcopy(generation)
        if self.response:
            if actual.pop("max_tokens", None) != BUDGET:
                raise ValueError("Recovery must use the one declared response budget")
            expected.pop("max_tokens", None)
        if actual != expected:
            raise ValueError("Saved-prefix sampling changed: " + self.source)

    def complete(self, messages, **generation):
        if self.cursor < len(self.records):
            row = self.records[self.cursor]
            self.check(row, messages, generation)
            if "error" in row or "raw_output" not in row:
                raise ValueError("Only completed saved calls can be replayed")
            audits = row.get("provider_audit_records", [])
            self.replayed_audits.extend({**deepcopy(a), "replayed_saved_call": True,
                "replay_source": self.source, "replay_record_index": self.cursor}
                for a in audits[self.prior_audit_count:])
            self.prior_audit_count = len(audits)
            self.cursor += 1
            return row["raw_output"]
        if self.failed is not None and not self.failed_request_matched:
            self.check(self.failed, messages, generation)
            self.failed_request_matched = True
        return self.provider.complete(messages, **generation)


def recover(index):
    plans, original = prepare()
    plan = deepcopy(plans[index])
    name = "{:02d}_{}_{}".format(index, plan["case"]["scenario_id"], plan["case"]["policy"])
    source = SOURCE / name
    failure = load(source / "result.json")
    if failure.get("error_type") != "IncompleteModelOutputError" or "truncated: length" not in failure.get("error", ""):
        raise ValueError("Only a documented output-length failure is eligible")
    logs = {role: load(source / "calls" / role / "requests.json")
            for role in ("policy", "state_appraisal", "interaction_appraisal", "response")}
    failed = logs["response"][-1]
    audits = failed.get("provider_audit_records", [])
    if not audits or audits[-1].get("finish_reason") != "length" or audits[-1].get("complete") is not False:
        raise ValueError("The failure must be in the response module with explicit length evidence")
    logs["response"] = logs["response"][:-1]
    directory = OUT / name
    if directory.exists():
        raise FileExistsError("One recovery only; preserve all attempts")
    plan["environment"].setdefault("response_sampling", {})["max_tokens"] = BUDGET
    manifest = {"mode": "one_budget_only_recovery", "original_failure": str((source / "result.json").relative_to(ROOT)),
                "original_failure_sha256": pilot.sha(source / "result.json"),
                "old_response_max_tokens": audits[-1]["request"]["max_tokens"], "new_response_max_tokens": BUDGET,
                "unchanged": ["model", "reasoning effort", "prompts", "scenario", "state rules", "other sampling", "policy ID"],
                "saved_prefix_calls": {role: len(rows) for role, rows in logs.items()},
                "source_call_sha256": {role: pilot.sha(source / "calls" / role / "requests.json") for role in logs},
                "code_sha256": {**original["code_sha256"], str(Path(__file__).relative_to(ROOT)): pilot.sha(__file__)},
                "formal_admission": False, "semantic_failure_resampling": False}
    save(directory / "recovery_manifest.json", manifest)
    replayers = {}
    factory = UnifiedEnvironmentFactory(build_environment_factory(plan["scenario"], plan["environment"]))

    def wrap(provider, role):
        replay = ReplayPrefixProvider(provider, logs[role], source / "calls" / role / "requests.json",
            response=role == "response", failed=failed if role == "response" else None)
        replayers[role] = replay
        return pilot.RoleLogProvider(replay, directory / "calls" / role, None)

    def environment_factory():
        env = factory()
        state = env.state_updater.state_appraiser
        state.provider.provider = wrap(state.provider.provider, "state_appraisal")
        env.state_updater.interaction_appraiser.provider = wrap(env.state_updater.interaction_appraiser.provider, "interaction_appraisal")
        env.response_generator.provider = wrap(env.response_generator.provider, "response")
        env.state_updater.provider = state.provider
        return env

    policy = build_policy(plan["policy"])
    policy.provider = wrap(policy.provider, "policy")

    def checkpoint(trajectory):
        trajectory["review_only"] = True
        trajectory["recovery_source"] = str(source.relative_to(ROOT))
        save(directory / "checkpoint.json", trajectory)
        (directory / "review.txt").write_text(pilot.review_text(plan, trajectory))

    row = {"scenario_id": plan["case"]["scenario_id"], "policy": plan["case"]["policy"],
           "formal_admission": False, "status": "running", "original_failure_preserved": True}
    save(directory / "result.json", row)
    try:
        trajectory = RolloutRunner(environment_factory, checkpoint_writer=checkpoint).run(policy, max_turns=20)
        trajectory["review_only"] = True
        trajectory["recovery_source"] = str(source.relative_to(ROOT))
        save(directory / "trajectory.json", trajectory)
        save(directory / "gate.json", audit_rollout(trajectory))
        row.update(status="completed", turns=len(trajectory["turns"]), ending=trajectory.get("ending"))
    except Exception as exc:
        row.update(status="call_or_validation_failure", error_type=type(exc).__name__, error=str(exc))
        partial = getattr(exc, "partial_trajectory", None)
        if partial is not None:
            row["completed_turns"] = len(partial.get("turns", []))
            save(directory / "partial_trajectory.json", partial)
    row["replayed_prefix_calls"] = {role: provider.cursor for role, provider in replayers.items()}
    row["failed_response_input_matched"] = replayers.get("response") is not None and replayers["response"].failed_request_matched
    row["fresh_provider_calls"] = {role: len(getattr(provider.provider, "audit_records", [])) for role, provider in replayers.items()}
    row["code_freeze_unchanged"] = all(pilot.sha(ROOT / path) == expected for path, expected in manifest["code_sha256"].items())
    save(directory / "result.json", row)
    plan_public = original["plans"][index]
    pilot.exporter.export_one(directory, plan_public)
    print(row, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, choices=range(3), required=True)
    args = parser.parse_args()
    recover(args.index)
