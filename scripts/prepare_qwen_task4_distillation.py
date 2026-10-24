#!/usr/bin/env python3
"""Prepare local teacher examples for isolated Qwen appraisal adaptation.

This exports development-only candidate training data. It does not train a model,
call a remote provider, label human ground truth, or alter an evaluation split.
"""

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.independent_appraisal import _validate_evidence_ids, _validate_features, _validate_judgments
from environment.qwen_task4 import QwenTask4Provider, load_config, load_prompt_profile
from environment.qwen_task4_contract import state_schema, interaction_schema
from environment.interaction_wire_schema import validate_event_pairs
from providers.structured import _parse_json_output
from jsonschema import Draft202012Validator

TRAIN_IDS = ("GPT50_003", "GPT50_011", "GPT50_012", "GPT50_025", "GPT50_043")
REGRESSION_IDS = ("GPT50_006",)
SOURCE = ROOT / "data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/unified_current_trust_v1_gpt50_active"
EVALUATION = ROOT / "data/environment_validation_20261024_qwen_e6_v2/manifest.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_example(stage, payload, raw):
    """Apply canonical source-ID normalization and preserve all model judgments."""
    value = deepcopy(_parse_json_output(raw))
    original_ids = deepcopy(value["evidence_turn_ids"])
    value["evidence_turn_ids"] = _validate_evidence_ids(
        value["evidence_turn_ids"], payload["memory"].get("relevant_turn_ids", []))
    schema = state_schema(payload) if stage == "state" else interaction_schema(payload)
    Draft202012Validator(schema).validate(value)
    action = payload["action"]["text"].strip()
    if stage == "state":
        features = _validate_features(value["event_features"])
        for judgments, paths in (("state_judgments", "state_variable_paths"),
                                  ("dynamics_judgments", "dynamics_variable_paths")):
            _validate_judgments(value[judgments], payload[paths], action,
                                payload["state_semantics"]["variables"], features, judgments)
    else:
        appraisal = value["appraisal"]
        validate_event_pairs(appraisal["ledger_events"])
        for event in appraisal["ledger_events"]:
            if not event["evidence_span"] or event["evidence_span"] not in action:
                raise ValueError("Event must quote the actual current source action")
        for claim in appraisal["dialogue_diagnostics"]["consequential_claims"]:
            if not claim["claim_span"] or claim["claim_span"] not in action:
                raise ValueError("Claim must quote the actual current source action")
    return value, {"source_evidence_turn_ids": original_ids,
                   "canonical_evidence_turn_ids": value["evidence_turn_ids"]}


def check_split(train, regression, evaluation):
    sets = list(map(set, (train, regression, evaluation)))
    if any(sets[i] & sets[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError("Training, regression and independent evaluation scenarios must be disjoint")


def prepare(output):
    config = load_config()
    instructions, _, profile_sha = load_prompt_profile(config)
    evaluation_ids = json.loads(EVALUATION.read_text())["scenario_ids"]
    check_split(TRAIN_IDS, REGRESSION_IDS, evaluation_ids)
    output.mkdir(parents=True, exist_ok=False)
    adapters = {stage: QwenTask4Provider(
        stage=stage, instruction=instructions[stage], profile_sha256=profile_sha,
        **config["environment"][stage + "_appraisal_provider"])
        for stage in ("state", "interaction")}
    records, rejected, source_hashes = [], [], {}
    for scenario_id in TRAIN_IDS:
        matches = list(SOURCE.glob("*_" + scenario_id + "_*/trajectory.json"))
        if len(matches) != 1:
            raise ValueError("Expected exactly one frozen reference trajectory: " + scenario_id)
        trajectory_path = matches[0]
        trajectory = json.loads(trajectory_path.read_text())
        source_hashes[str(trajectory_path.relative_to(ROOT))] = digest(trajectory_path)
        available_turns = {str(t["turn_id"]) for t in trajectory["turns"]}
        for stage in ("state", "interaction"):
            path = trajectory_path.parent / "calls" / (stage + "_appraisal") / "requests.json"
            source_hashes[str(path.relative_to(ROOT))] = digest(path)
            grouped = {}
            for index, row in enumerate(json.loads(path.read_text())):
                try:
                    messages = deepcopy(row["messages"][:2])
                    payload = json.loads(messages[1]["content"].split("## Input\n", 1)[1])
                    turn_id = str(payload["appraisal_context"]["current_turn"]["turn_id"])
                    if turn_id not in available_turns:
                        raise ValueError("Call has no completed source turn")
                    value, projection = validate_example(stage, payload, row["raw_output"])
                    teacher = trajectory["environment_provenance"][stage + "_appraisal_provider"]["model"]
                    record = {
                        "id": f"{scenario_id}:{turn_id}:{stage}", "scenario_id": scenario_id,
                        "turn_id": turn_id, "stage": stage, "teacher_model": teacher,
                        "messages": adapters[stage].prepare_messages(messages) + [
                            {"role": "assistant", "content": json.dumps(value, ensure_ascii=False, separators=(",", ":"))}],
                        "source": str(path.relative_to(ROOT)), "source_record_index": index,
                        "source_raw_output_sha256": hashlib.sha256(row["raw_output"].encode()).hexdigest(),
                        "projection": projection, "human_review": False,
                        "quality_status": "structurally_checked_teacher_candidate",
                    }
                    grouped.setdefault(turn_id, []).append(record)
                except (ValueError, TypeError, KeyError, IndexError) as error:
                    rejected.append({"scenario_id": scenario_id, "stage": stage,
                                     "source_record_index": index, "reason": str(error)[:600]})
                except Exception as error:
                    # jsonschema.ValidationError is not a ValueError. Record it
                    # explicitly while allowing unexpected programming errors out.
                    from jsonschema.exceptions import ValidationError
                    if not isinstance(error, ValidationError):
                        raise
                    rejected.append({"scenario_id": scenario_id, "stage": stage,
                                     "source_record_index": index, "reason": error.message[:600]})
            for turn_id, candidates in grouped.items():
                if len(candidates) != 1:
                    rejected.append({"scenario_id": scenario_id, "stage": stage, "turn_id": turn_id,
                                     "reason": "Multiple valid request candidates; source acceptance is ambiguous"})
                    continue
                records.append(candidates[0])
    if not records:
        raise ValueError("No eligible teacher candidates")
    with (output / "candidates.jsonl").open("x") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (output / "rejected.json").write_text(json.dumps(rejected, ensure_ascii=False, indent=2))
    manifest = {
        "format": "qwen_task4_appraisal_distillation_candidates_v1", "status": "prepared_not_trained",
        "train_scenarios": list(TRAIN_IDS), "regression_scenarios": list(REGRESSION_IDS),
        "independent_evaluation_scenarios": evaluation_ids,
        "evaluation_manifest_sha256": digest(EVALUATION),
        "candidate_count": len(records), "by_stage": dict(Counter(r["stage"] for r in records)),
        "by_scenario": dict(Counter(r["scenario_id"] for r in records)), "rejected_records": len(rejected),
        "source_sha256": source_hashes, "script_sha256": digest(__file__),
        "candidates_sha256": digest(output / "candidates.jsonl"),
        "prompt_manifest_sha256": profile_sha, "formal_admission": False, "human_review": False,
        "external_requests": 0, "training_started": False,
        "limitations": ["Archived model outputs are not human ground truth.",
                       "Structural and citation screening does not certify state semantics.",
                       "Original source-language inputs are used; translated trajectory prose is not mixed with original evidence spans.",
                       "Independent evaluation and the recurring regression scenario were never exported for training."],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return {k: manifest[k] for k in ("status", "candidate_count", "by_stage", "rejected_records")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output.resolve())))
