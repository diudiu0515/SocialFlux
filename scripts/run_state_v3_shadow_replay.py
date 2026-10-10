#!/usr/bin/env python3
"""Replay accepted fixed transcripts through State v3 appraisal/calibration.

The environment responses remain byte-for-byte fixed.  These artifacts measure
state-transition behavior only and are never labeled as causally valid v3
rollouts.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.appraisal import ModelAppraiser  # noqa: E402
from environment.delta_mapper import flatten_state  # noqa: E402
from environment.env import StatefulEnvironment  # noqa: E402
from environment.state_transition_contract import (  # noqa: E402
    STATE_V3_STAGE_ORDER,
    validate_state_v3_scenario,
)
from environment.state_updater import (  # noqa: E402
    ModelStateUpdater,
    canonicalize_bounded_transition,
    unsupported_consequential_claims,
    validate_transition,
)
from evaluation.state_v3_metrics import state_v3_trajectory_metrics  # noqa: E402
from providers.factory import build_provider, public_provider_config  # noqa: E402
from providers.model_routes import ModelRoutes  # noqa: E402
from rollout.configuration import load_rollout_config  # noqa: E402


FORMAT = "socialflux_state_v31_shadow_replay_v2"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_json(value):
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


class FixedTranscriptResponseGenerator:
    """Return recorded responses without making a response-model request."""

    horizon_mode = "natural_max_20"
    minimum_natural_turns = 10

    def __init__(
        self, source_turns, *, prompt_id, minimum_natural_turns=10
    ):
        self.source_turns = deepcopy(source_turns)
        self.prompt_id = prompt_id
        self.minimum_natural_turns = int(minimum_natural_turns)

    @property
    def provenance(self):
        return {
            "provider": "fixed_transcript",
            "prompt_id": self.prompt_id,
            "response_model_calls": 0,
            "causally_equivalent_to_v3_rollout": False,
        }

    def generate(self, context):
        index = int(context["turn_id"]) - 1
        if not 0 <= index < len(self.source_turns):
            raise IndexError("fixed transcript response index is out of range")
        turn = self.source_turns[index]
        return {
            "response_text": turn["environment_response"],
            "ledger_events": deepcopy(
                turn.get("environment_response_ledger_events") or []
            ),
            "ledger_event_normalizations": deepcopy(
                turn.get("environment_response_ledger_event_normalizations") or []
            ),
            "request_retry_diagnostics": [],
            "reply_obligation": deepcopy(turn.get("response_reply_obligation")),
            "consequential_claims": deepcopy(
                turn.get("response_consequential_claims") or []
            ),
            "expression_intent": turn.get("response_expression_intent"),
            "observable_behavior": deepcopy(
                turn.get("response_observable_behavior")
            ),
        }


def filter_unsupported_claim_impacts(appraisal, claims):
    """Remove state evidence that directly overlaps an unsupported claim."""
    filtered = deepcopy(appraisal)
    claim_spans = [
        str(item.get("claim_span", "")).strip()
        for item in claims
        if str(item.get("claim_span", "")).strip()
    ]
    removed = []
    for field in ("state_impacts", "dynamics_impacts"):
        kept = []
        for impact in filtered.get(field, []):
            evidence_span = str(impact.get("evidence_span", "")).strip()
            overlaps = evidence_span and any(
                evidence_span in claim_span or claim_span in evidence_span
                for claim_span in claim_spans
            )
            if overlaps:
                removed.append({"field": field, "impact": deepcopy(impact)})
            else:
                kept.append(impact)
        filtered[field] = kept
    return filtered, removed


class ShadowReplayStateUpdater(ModelStateUpdater):
    """Calibrate fixed actions while recording native grounding rejections."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.claim_diagnostics = []

    def update(
        self, *, action, previous_state, previous_dynamics, memory,
        longitudinal_context=None, interaction_ledger=None,
    ):
        appraisal_result = self.appraiser.appraise(
            action=action,
            previous_state=previous_state,
            previous_dynamics=previous_dynamics,
            memory=memory,
            longitudinal_context=longitudinal_context,
            interaction_ledger=interaction_ledger,
        )
        appraisal = deepcopy(appraisal_result["appraisal"])
        unsupported = unsupported_consequential_claims(appraisal)
        appraisal, removed = filter_unsupported_claim_impacts(
            appraisal, unsupported
        )
        calibrated = self.calibrator.calibrate(
            appraisal,
            previous_state,
            previous_dynamics,
            surface_duplicate_evidence_ids=memory.get(
                "deterministic_surface_duplicate_ids", []
            ),
        )
        transition = {
            "appraisal": appraisal,
            "evidence_turn_ids": appraisal_result["evidence_turn_ids"],
            "appraisal_request_retry_diagnostics": deepcopy(
                appraisal_result.get("request_retry_diagnostics", [])
            ),
            **calibrated,
        }
        validate_transition(transition, previous_state, previous_dynamics)
        self.claim_diagnostics.append({
            "claims": deepcopy(unsupported),
            "removed_impacts": removed,
            "native_rollout_would_reject_action": bool(unsupported),
        })
        return canonicalize_bounded_transition(
            transition,
            previous_state,
            previous_dynamics,
        )


def transition_summary(turns):
    family = {}
    changed_turns = 0
    trigger_count = 0
    for turn in turns:
        flattened = flatten_state(turn.get("numeric_state_delta") or {})
        if any(value != 0 for value in flattened.values()):
            changed_turns += 1
        for path, value in flattened.items():
            state_family = path.split(".", 1)[0]
            record = family.setdefault(state_family, {
                "variable_turn_count": 0,
                "changed_variable_turn_count": 0,
                "total_absolute_change": 0,
            })
            record["variable_turn_count"] += 1
            if value != 0:
                record["changed_variable_turn_count"] += 1
                record["total_absolute_change"] += abs(value)
        trigger_count += len(turn.get("trigger_events") or [])
    return {
        "turn_count": len(turns),
        "turns_with_any_state_change": changed_turns,
        "turns_with_any_state_change_fraction": (
            changed_turns / len(turns) if turns else 0
        ),
        "state_family_activity": dict(sorted(family.items())),
        "online_multimodal_trigger_count": trigger_count,
    }


def shadow_replay_minimum_natural_turns(configured_minimum, source_turn_count):
    if not 1 <= source_turn_count <= 20:
        raise ValueError("shadow replay source must contain 1-20 turns")
    return max(int(configured_minimum), int(source_turn_count))


def replay_one(source_path, scenario_path, config, runtime_contract):
    source = load(source_path)
    scenario = load(scenario_path)
    validate_state_v3_scenario(scenario)
    source_turns = source.get("turns") or []
    provider_config = config["environment"]["provider"]
    provider = build_provider(provider_config)
    sampling = config["environment"].get("sampling", {})
    prompt_id = config["environment"]["appraisal_prompt_id"]
    calibration_profile = config["environment"]["state_calibration_profile"]
    updater = ShadowReplayStateUpdater(
        scenario,
        provider,
        sampling,
        appraiser=ModelAppraiser(
            scenario,
            provider,
            sampling,
            prompt_id=prompt_id,
        ),
        calibration_profile=calibration_profile,
    )
    response_prompt_id = config["environment"]["response_prompt_id"]
    runtime_revision = config["environment"].get(
        "state_transition_runtime_revision"
    )
    minimum_natural_turns = config["environment"][
        "minimum_natural_turns"
    ]
    replay_minimum_natural_turns = shadow_replay_minimum_natural_turns(
        minimum_natural_turns,
        len(source_turns),
    )
    fixed_responses = FixedTranscriptResponseGenerator(
        source_turns,
        prompt_id=response_prompt_id,
        minimum_natural_turns=replay_minimum_natural_turns,
    )
    environment = StatefulEnvironment(
        scenario,
        state_updater=updater,
        response_generator=fixed_responses,
        provenance={
            "mode": "state_v3_fixed_transcript_shadow_replay",
            "appraisal_provider": public_provider_config(provider_config),
            "appraisal_prompt_id": prompt_id,
            "state_calibration_profile": calibration_profile,
            "state_transition_standard": config["environment"].get(
                "state_transition_standard"
            ),
            "state_transition_runtime_revision": runtime_revision,
            "state_transition_stage_order": list(STATE_V3_STAGE_ORDER),
            "response_prompt_id": response_prompt_id,
            "response_provider": fixed_responses.provenance,
            "shadow_replay_effective_minimum_natural_turns": (
                replay_minimum_natural_turns
            ),
        },
        minimum_natural_turns=replay_minimum_natural_turns,
        multimodal_trigger_policy=config["environment"].get(
            "multimodal_trigger_policy", {}
        ),
    )
    environment.reset(episode_id=f"shadow-{source['trajectory_id']}")
    for expected_index, source_turn in enumerate(source_turns, 1):
        _, replayed = environment.step(source_turn["policy_action"])
        if replayed["turn_id"] != f"t{expected_index}":
            raise ValueError("shadow replay turn alignment failed")
        if replayed["environment_response"] != source_turn["environment_response"]:
            raise ValueError("shadow replay changed a fixed environment response")
    trajectory = environment.private_trajectory()
    if len(updater.claim_diagnostics) != len(trajectory["turns"]):
        raise ValueError("shadow replay claim diagnostics are misaligned")
    for turn, diagnostic in zip(
        trajectory["turns"], updater.claim_diagnostics
    ):
        turn["shadow_replay_grounding_diagnostic"] = deepcopy(diagnostic)
    native_rejection_turn_count = sum(
        item["native_rollout_would_reject_action"]
        for item in updater.claim_diagnostics
    )
    removed_impact_count = sum(
        len(item["removed_impacts"])
        for item in updater.claim_diagnostics
    )
    return {
        "format": FORMAT,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "shadow_replay_only_not_causally_equivalent",
        "scenario_id": source["scenario_id"],
        "source_trajectory_id": source["trajectory_id"],
        "source_status": "catalog_source_unmodified",
        "source_turn_count": len(source_turns),
        "required_native_rollout_turn_window": [10, 20],
        "satisfies_native_rollout_requirement": False,
        "fixed_environment_response_count": len(source_turns),
        "response_model_request_count": 0,
        "shadow_replay_controls": {
            "complete_source_transcript_required": True,
            "effective_minimum_natural_turns": replay_minimum_natural_turns,
            "configured_minimum_natural_turns": minimum_natural_turns,
            "native_grounding_rejection_turn_count": (
                native_rejection_turn_count
            ),
            "unsupported_claim_overlap_removed_impact_count": (
                removed_impact_count
            ),
            "unsupported_claims_are_not_native_rollout_evidence": True,
        },
        "causal_limitations": [
            "source responses were fixed before this state replay and were not regenerated from replayed state",
            "only appraisal, calibration, state update, opportunity, and trigger evaluation were replayed",
            "fixed source actions that native grounding would reject are retained, flagged, and cannot supply overlapping state evidence",
            "the artifact must not be counted as an accepted native State v3.4 rollout",
        ],
        "runtime_contract": deepcopy(runtime_contract),
        "fingerprints": {
            "source_trajectory_sha256": sha256_file(source_path),
            "state_v3_scenario_sha256": sha256_file(scenario_path),
            "state_runtime_contract_sha256": sha256_json(runtime_contract),
        },
        "transition_summary": transition_summary(trajectory["turns"]),
        "state_v3_metrics": state_v3_trajectory_metrics(trajectory),
        "provider_metrics": deepcopy(getattr(provider, "metrics", {})),
        "trajectory": trajectory,
        "human_review": "pending",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--accepted-root", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--rollout-config", type=Path, required=True)
    parser.add_argument("--appraisal-routes", type=Path)
    parser.add_argument("--appraisal-route", default="appraisal")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    config = load_rollout_config(args.rollout_config)
    if args.appraisal_routes is not None:
        config["environment"]["provider"] = ModelRoutes.load(
            args.appraisal_routes
        ).provider_config(args.appraisal_route)
    source_paths = sorted(args.accepted_root.glob("scenario_*/trajectory.json"))
    runtime_contract = {
        "rollout_config_path": str(args.rollout_config.resolve()),
        "rollout_config_sha256": sha256_file(args.rollout_config),
        "appraisal_routes_path": (
            str(args.appraisal_routes.resolve())
            if args.appraisal_routes is not None else None
        ),
        "appraisal_routes_sha256": (
            sha256_file(args.appraisal_routes)
            if args.appraisal_routes is not None else None
        ),
        "appraisal_prompt_id": config["environment"]["appraisal_prompt_id"],
        "response_prompt_id": config["environment"]["response_prompt_id"],
        "state_calibration_profile": config["environment"][
            "state_calibration_profile"
        ],
        "state_transition_standard": config["environment"].get(
            "state_transition_standard"
        ),
        "state_transition_runtime_revision": config["environment"].get(
            "state_transition_runtime_revision"
        ),
        "horizon_mode": config["environment"].get("horizon_mode"),
        "minimum_natural_turns": config["environment"].get(
            "minimum_natural_turns"
        ),
    }
    runtime_contract_sha256 = sha256_json(runtime_contract)
    expected_count = args.expected_count or len(source_paths)
    if len(source_paths) != expected_count:
        raise ValueError(
            f"expected {expected_count} source trajectories, found {len(source_paths)}"
        )

    records = []
    failures = []
    for source_path in source_paths:
        source = load(source_path)
        ordinal = source["scenario_id"].rsplit("_", 1)[1]
        scenario_path = (
            args.scenario_root / f"scenario_{ordinal}" / f"scenario_{ordinal}.json"
        )
        output_path = args.output / f"scenario_{ordinal}" / "shadow_replay.json"
        if not scenario_path.is_file():
            failures.append({
                "scenario_id": source["scenario_id"],
                "status": "pending_state_v3_scenario",
                "scenario_path": str(scenario_path),
            })
            continue
        if args.resume and output_path.is_file():
            existing = load(output_path)
            fingerprints = existing.get("fingerprints") or {}
            if (
                existing.get("format") == FORMAT
                and fingerprints.get("source_trajectory_sha256")
                == sha256_file(source_path)
                and fingerprints.get("state_v3_scenario_sha256")
                == sha256_file(scenario_path)
                and fingerprints.get("state_runtime_contract_sha256")
                == runtime_contract_sha256
            ):
                records.append({
                    "scenario_id": source["scenario_id"],
                    "status": "reused",
                    "output": str(output_path),
                })
                continue
        try:
            artifact = replay_one(
                source_path, scenario_path, config, runtime_contract
            )
            atomic(output_path, artifact)
            record = {
                "scenario_id": source["scenario_id"],
                "status": "completed",
                "source_turn_count": artifact["source_turn_count"],
                "output": str(output_path),
            }
            records.append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
        except Exception as exc:
            failure = {
                "scenario_id": source["scenario_id"],
                "status": "replay_error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failures.append(failure)
            print(json.dumps(failure, ensure_ascii=False), flush=True)
            if "http 429" in str(exc).casefold() or "overloaded" in str(exc).casefold():
                break

    manifest = {
        "format": "socialflux_state_v31_shadow_replay_manifest_v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": f"{expected_count} fixed source transcripts",
        "expected": expected_count,
        "completed_artifact_count": len(list(args.output.glob(
            "scenario_*/shadow_replay.json"
        ))),
        "run_records": records,
        "failures": failures,
        "real_rollout_equivalent": False,
        "runtime_contract": runtime_contract,
        "state_runtime_contract_sha256": runtime_contract_sha256,
        "human_review": "pending",
        "appraisal_route_override": (
            str(args.appraisal_routes.resolve())
            if args.appraisal_routes is not None else None
        ),
    }
    atomic(args.output / "manifest.json", manifest)
    print(json.dumps({
        "output": str(args.output),
        "completed_artifact_count": manifest["completed_artifact_count"],
        "failure_count": len(failures),
    }, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
