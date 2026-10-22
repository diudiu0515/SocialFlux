#!/usr/bin/env python3
"""Audit the v3.2.24 prompt/config/calibrator interface without model calls."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.calibration import CALIBRATION_PROFILES
from prompts.loader import get_prompt, prompt_manifest
from rollout.configuration import load_rollout_config


DEFAULT_CONFIG = ROOT / "configs/gpt50_experiment/rollout.state_independent_per_variable_v3_state_judgment_primary_candidate.json"
DEFAULT_OUTPUT = ROOT / "data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/interface_consistency_audit.json"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state-prompt-id")
    args = parser.parse_args(argv)
    config = load_rollout_config(args.config)
    environment = config["environment"]
    if args.state_prompt_id:
        environment["state_appraisal_prompt_id"] = args.state_prompt_id
    state_id = environment["state_appraisal_prompt_id"]
    interaction_id = environment["interaction_appraisal_prompt_id"]
    response_id = environment["response_prompt_id"]
    combined_id = environment["appraisal_prompt_id"]
    state_prompt = get_prompt(state_id)
    interaction_prompt = get_prompt(interaction_id)
    response_prompt = get_prompt(response_id)
    combined_prompt = get_prompt(combined_id)
    profile = CALIBRATION_PROFILES[environment["state_calibration_profile"]]

    forbidden_state_patterns = {
        "feature_must_be_nonzero": r"feature.{0,40}(must|requires?).{0,20}(nonzero|non-zero)",
        "feature_two_required_for_decisive": r"(absolute magnitude|feature).{0,50}2.{0,50}(decisive|strength-2)",
        "dialogue_label_controls_update": r"substantive_novelty.{0,80}(update|delta)",
    }
    forbidden_hits = {
        name: match.group(0)
        for name, pattern in forbidden_state_patterns.items()
        for match in [re.search(pattern, state_prompt, flags=re.I | re.S)]
        if match
    }
    checks = {
        "independent_appraisals_enabled": environment.get("independent_appraisals") is True,
        "state_prompt_is_expected": state_id == (
            args.state_prompt_id
            or "environment_state_appraisal_v5_immediate_context"
        ),
        "state_prompt_has_no_legacy_semantic_gates": not forbidden_hits,
        "state_prompt_declares_feature_auxiliary": "auxiliary interface annotation" in state_prompt,
        "state_prompt_allows_null_feature": "otherwise use null" in state_prompt,
        "state_prompt_excludes_dialogue_diagnostics": "Do not generate a response, ledger events, proposal resolutions, dialogue diagnostics" in state_prompt,
        "interaction_prompt_excludes_state_judgment": "Do not judge state variables" in interaction_prompt,
        "response_prompt_runs_after_update": "Python has already applied deterministic calibration and state/dynamics updates" in response_prompt,
        "v7_feature_is_auxiliary": profile.get("feature_is_auxiliary") is True,
        "v7_dialogue_gate_disabled": profile.get("enforce_dialogue_diagnostics_gate") is False,
        "v7_decisive_source_is_state_judgment": profile.get("decisive_evidence_rule") == "state_judgment",
    }
    combined_legacy_hits = {
        "requires_nonzero_feature": "selected feature must describe the same cited act and have a non-zero value" in combined_prompt,
        "requires_feature_two_for_strength_two": "requires a strength-2 impact to have an associated feature with absolute magnitude 2" in combined_prompt,
        "contains_dialogue_diagnostics": "## 7. Dialogue diagnostics" in combined_prompt,
    }
    payload = {
        "format": "socialflux_state_v7_interface_consistency_audit_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(args.config.resolve().relative_to(ROOT)),
        "config_sha256": sha256(args.config),
        "config_runtime_overrides": {
            "state_appraisal_prompt_id": args.state_prompt_id,
        } if args.state_prompt_id else {},
        "runtime_revision": environment["state_transition_runtime_revision"],
        "calibration_profile": environment["state_calibration_profile"],
        "model_calls": 0,
        "checks": checks,
        "forbidden_state_prompt_hits": forbidden_hits,
        "independent_interface_passed": all(checks.values()),
        "prompt_roles": {
            "new_scheme_state": state_id,
            "new_scheme_interaction": interaction_id,
            "post_update_response": response_id,
            "frozen_combined_baseline_only": combined_id,
        },
        "state_prompt_sha256": prompt_manifest()["prompts"][state_id]["sha256"],
        "combined_baseline": {
            "v7_interface_compatible": False,
            "legacy_gate_hits": combined_legacy_hits,
            "execution_policy": "reuse_frozen_results_only; do_not_call_in_v7_fixed_set",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps({
        "output": str(args.output),
        "independent_interface_passed": payload["independent_interface_passed"],
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "combined_baseline_v7_compatible": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
