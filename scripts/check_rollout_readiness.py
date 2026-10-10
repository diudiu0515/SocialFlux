"""Offline readiness gate for a versioned rollout batch.

This command validates scenarios, routes, prompts, and rollout contracts without
constructing providers or making network requests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.scenarios import load_scenario_records, require_human_frozen
from prompts.loader import get_prompt
from rollout.configuration import load_rollout_config
from schemas.validate import STATE_CONTRACT_VERSION
from environment.state_transition_contract import (
    STATE_TRANSITION_STANDARD_V3,
    validate_state_v3_scenario,
)


def check(scenario_root, rollout_config, *, require_human):
    records = load_scenario_records(scenario_root)
    config = load_rollout_config(rollout_config)
    standard = config["environment"].get("state_transition_standard")
    failures = []
    for path, scenario in records:
        if scenario.get("state_contract_version") != STATE_CONTRACT_VERSION:
            failures.append(f"{scenario['scenario_id']}: legacy state contract")
        if require_human:
            try:
                require_human_frozen(scenario)
            except ValueError as exc:
                failures.append(f"{scenario['scenario_id']}: {exc}")
        if standard == STATE_TRANSITION_STANDARD_V3:
            try:
                validate_state_v3_scenario(scenario)
            except ValueError as exc:
                failures.append(str(exc))
    prompt_ids = {
        config["environment"].get("appraisal_prompt_id"),
        config["environment"].get("response_prompt_id"),
        *(item.get("prompt_id") for item in config.get("policies", [])),
    }
    missing_prompts = []
    for prompt_id in sorted(item for item in prompt_ids if item):
        try:
            get_prompt(prompt_id)
        except (KeyError, ValueError) as exc:
            missing_prompts.append(f"{prompt_id}: {exc}")
    failures.extend(missing_prompts)
    if failures:
        raise ValueError("rollout readiness failed:\n" + "\n".join(failures))
    return {
        "ready": True,
        "network_requests_performed": 0,
        "scenario_count": len(records),
        "rollout_slots": len(records) * len(config["policies"]),
        "state_contract_version": STATE_CONTRACT_VERSION,
        "state_transition_standard": standard,
        "prompt_ids": sorted(item for item in prompt_ids if item),
        "rollout_config": str(Path(rollout_config)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--rollout-config", type=Path, required=True)
    parser.add_argument("--require-human-frozen", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(
        check(
            args.scenarios,
            args.rollout_config,
            require_human=args.require_human_frozen,
        ),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
