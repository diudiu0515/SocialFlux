#!/usr/bin/env python3
"""One same-input recovery for the saved empty response, preserving all state outputs."""
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_unified_three_pilot as pilot
from scripts.run_unified_exploratory_pilot import OUT as SOURCE, prepare
from scripts.recover_exploratory_response_budget import ReplayPrefixProvider, BUDGET
from scripts.validate_state_context_samples import BASE, load, save

OUT = BASE / "unified_current_trust_v1_empty_response_recovery"


def main():
    plans, original = prepare()
    index = 1
    plan = deepcopy(plans[index])
    name = "{:02d}_{}_{}".format(index, plan["case"]["scenario_id"], plan["case"]["policy"])
    source, directory = SOURCE / name, OUT / name
    failure = load(source / "result.json")
    if failure.get("error_type") != "ValueError" or failure.get("error") != "provider returned empty content":
        raise ValueError("Expected the exact recorded empty-response failure")
    if directory.exists():
        raise FileExistsError("One recovery only; do not repeat or overwrite")
    roles = ("policy", "state_appraisal", "interaction_appraisal", "response")
    logs = {role: load(source / "calls" / role / "requests.json") for role in roles}
    failed = logs["response"].pop()
    if failed.get("error", {}).get("message") != "provider returned empty content" or failed.get("raw_output"):
        raise ValueError("Failure is not an empty response; never resample semantic failures here")
    if any("error" in row or "raw_output" not in row for rows in logs.values() for row in rows):
        raise ValueError("Saved prefix must consist entirely of returned outputs")
    plan["environment"].setdefault("response_sampling", {})["max_tokens"] = BUDGET
    paths = [Path(__file__).relative_to(ROOT), Path("scripts/recover_exploratory_response_budget.py")]
    freeze = {**original["code_sha256"], **{str(p): pilot.sha(ROOT / p) for p in paths}}
    manifest = {"mode": "one_empty_response_recovery", "source_failure": str((source / "result.json").relative_to(ROOT)),
                "source_failure_sha256": pilot.sha(source / "result.json"),
                "old_response_max_tokens": 2600, "new_response_max_tokens": BUDGET,
                "budget_policy": "Apply the already diagnosed response-budget correction; no semantic rule change",
                "preserved_policy_id": plan["policy"]["policy_id"],
                "saved_prefix_calls": {role: len(rows) for role, rows in logs.items()},
                "source_call_sha256": {role: pilot.sha(source / "calls" / role / "requests.json") for role in roles},
                "code_sha256": freeze, "formal_admission": False, "semantic_failure_resampling": False}
    save(directory / "recovery_manifest.json", manifest)
    original_logger = pilot.RoleLogProvider
    replayers = {}

    def logged_replay(provider, target, expected):
        role = target.name
        replay = ReplayPrefixProvider(provider, logs[role], source / "calls" / role / "requests.json",
            response=role == "response", failed=failed if role == "response" else None)
        replayers[role] = replay
        return original_logger(replay, target, expected)

    pilot.OUT, pilot.RoleLogProvider = OUT, logged_replay
    row = pilot.run_one(index, plan)
    row.update(mode=manifest["mode"], original_failure_preserved=True,
        replayed_prefix_calls={role: r.cursor for role, r in replayers.items()},
        failed_response_input_matched=replayers["response"].failed_request_matched,
        fresh_provider_calls={role: len(getattr(r.provider, "audit_records", [])) for role, r in replayers.items()},
        code_freeze_unchanged=all(pilot.sha(ROOT / p) == h for p, h in freeze.items()))
    save(directory / "result.json", row)
    pilot.exporter.export_one(directory, original["plans"][index])
    print(row, flush=True)


if __name__ == "__main__":
    main()
