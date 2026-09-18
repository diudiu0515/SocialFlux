#!/usr/bin/env python3
"""One bounded answer/judge revision for completed T2 expression development pairs."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.factory import build_provider
from providers.model_routes import ModelRoutes
from providers.structured import complete_json
from scripts.build_t2_expression_dev_pairs import (
    DEFAULT_MODEL_ROUTES,
    OUT,
    answer_prompt,
    atomic,
    internal_direction,
    load,
    now,
    review_prompt,
    scenario_path,
    supported_t2_candidates,
    validate_answer,
    validate_review,
)


def revise(path, model_routes):
    pair = json.loads(path.read_text(encoding="utf-8"))
    previous = {
        "llm_answer": deepcopy(pair["llm_answer"]),
        "answer_provenance": deepcopy(pair["answer_provenance"]),
        "model_semantic_review": deepcopy(pair["model_semantic_review"]),
        "candidate_state_ids": deepcopy(
            pair["instance"]["target_spec"]["candidate_state_ids"]
        ),
        "program_answer_direction_check": pair["program_checks"].get(
            "answer_top_direction_matches_internal_update"
        ),
    }
    ordinal = int(pair["scenario_id"].rsplit("_", 1)[1])
    scenario = load(scenario_path(ordinal))
    state_a = pair["backend"]["state_a"]
    state_b = pair["backend"]["state_b"]
    candidates = supported_t2_candidates(scenario, state_a, state_b)
    if not candidates:
        raise ValueError("T2 pair has no changed approved state variable")
    pair["instance"]["target_spec"]["candidate_state_ids"] = candidates
    answer_provider = build_provider(model_routes.provider_config("t2_answer"))
    answer = complete_json(
        answer_provider,
        [{"role": "user", "content": answer_prompt(pair["instance"])}],
        {"temperature": 0.15, "top_p": 0.9, "seed": 98000 + int(pair["scenario_id"].rsplit("_", 1)[1])},
        lambda value: validate_answer(value, pair["instance"]),
        context=f"T2 v2 sparse target-locked answer revision {pair['scenario_id']}",
        max_attempts=4,
        retry_guidance=(
            "The target is environment_character, never evaluated_agent. Select only one "
            "state when only one has strong bilateral evidence. Every target_quote must be "
            "an exact substring of environment_character at its cited t1-t5 turn."
        ),
    )
    pair["llm_answer"] = answer
    pair["answer_provenance"] = {
        "model_route": "t2_answer",
        **answer_provider.provenance,
        "request_count": answer_provider._call_index,
        "machine_answer_not_ground_truth": True,
        "human_review": "pending",
        "revision": "role_safe_quotes_and_supported_variables_v2",
    }
    state_a = pair["backend"]["state_a"]
    state_b = pair["backend"]["state_b"]
    internal = {
        state_id: internal_direction(state_a, state_b, state_id)
        for state_id in pair["instance"]["target_spec"]["candidate_state_ids"]
    }
    answer_top = {
        row["state_id"]: max(
            row["direction_probabilities"], key=row["direction_probabilities"].get
        )
        for row in answer["predictions"]
    }
    pair["program_checks"]["answer_top_direction_matches_internal_update"] = all(
        answer_top[state_id] in {internal.get(state_id), "cannot_determine"}
        for state_id in answer_top
    )
    pair["program_checks"]["role_safe_quoted_evidence"] = True
    pair["backend"]["internal_directions_not_ground_truth"] = internal

    review_provider = build_provider(model_routes.provider_config("t2_answer_review"))
    review = complete_json(
        review_provider,
        [{"role": "user", "content": review_prompt(pair)}],
        {"temperature": 0.1, "top_p": 0.9, "seed": 99000 + int(pair["scenario_id"].rsplit("_", 1)[1])},
        validate_review,
        context=f"T2 v2 target-locked semantic review {pair['scenario_id']}",
        max_attempts=3,
        retry_guidance=(
            "Reject or request revision for target-role confusion, repeated no-information "
            "environment replies, or private expression explanations detached from the text."
        ),
    )
    pair["model_semantic_review"] = {
        **review,
        "reviewer_type": "llm_semantic_review_not_human",
        "model_route": "t2_answer_review",
        **review_provider.provenance,
        "request_count": review_provider._call_index,
        "revision": "target_role_lock_and_loop_sensitive_v1",
    }
    pair.setdefault("answer_revision_history", []).append(previous)
    pair["answer_revision"] = {
        "status": "completed",
        "updated_at_utc": now(),
        "answer_requests": answer_provider._call_index,
        "review_requests": review_provider._call_index,
        "script": "scripts/revise_t2_expression_answers.py",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    pair["request_counts"]["answer_revision"] = answer_provider._call_index
    pair["request_counts"]["semantic_review_revision"] = review_provider._call_index
    pair["request_counts"]["total"] += (
        answer_provider._call_index + review_provider._call_index
    )
    atomic(path, pair)
    return {
        "scenario_id": pair["scenario_id"],
        "selected_state_ids": answer["selected_state_ids"],
        "program_direction_match": pair["program_checks"][
            "answer_top_direction_matches_internal_update"
        ],
        "semantic_decision": review["decision"],
        "issues": review["issues"],
        "requests": answer_provider._call_index + review_provider._call_index,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair-index", type=int, required=True)
    parser.add_argument("--model-routes", default=str(DEFAULT_MODEL_ROUTES))
    args = parser.parse_args()
    model_routes = ModelRoutes.load(args.model_routes).require(
        {"t2_answer", "t2_answer_review"}
    )
    paths = sorted(OUT.glob("pair_*.json"))
    result = revise(paths[args.pair_index], model_routes)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
