"""Review and answer an already replayed T2 pair.

This stage is resumable so a malformed reviewer response never forces another
expensive A/B environment replay.
"""

from __future__ import annotations

from copy import deepcopy

from providers.factory import build_provider
from tasks.T2.answering import generate_answer
from tasks.T2.quality_review import review_answer, review_pair


def error_record(error):
    record = {"type": type(error).__name__, "message": str(error)}
    if getattr(error, "last_error", None) is not None:
        record["last_validation_error"] = str(error.last_error)
    if getattr(error, "diagnostics", None):
        record["attempt_diagnostics"] = deepcopy(error.diagnostics)
    if getattr(error, "last_raw", None):
        record["last_raw_output"] = error.last_raw
    return record


def total_requests(counts):
    total = 0
    for key, value in counts.items():
        if key in {
            "environment_stage_count_per_turn",
            "actual_requests_include_retries",
            "total",
        }:
            continue
        if isinstance(value, dict):
            total += sum(int(item) for item in value.values())
        elif isinstance(value, (int, float)):
            total += int(value)
    return total


class PairCompletion:
    def __init__(self, model_routes):
        self.model_routes = model_routes

    def _provider(self, route_name):
        return build_provider(self.model_routes.provider_config(route_name))

    def complete(self, pair, seed):
        counts = pair["request_counts"]
        if pair.get("model_pair_review") is None:
            provider = self._provider("t2_pair_review")
            previous = int(counts.get("pair_semantic_review", 0) or 0)
            try:
                review, request_count = review_pair(provider, pair, seed + 5000)
            except Exception as exc:
                counts["pair_semantic_review"] = previous + int(
                    getattr(provider, "_call_index", 0) or 0
                )
                counts["total"] = total_requests(counts)
                return {
                    "status": "pair_review_failed",
                    "stage": "pair_semantic_review",
                    "error": error_record(exc),
                }
            counts["pair_semantic_review"] = previous + request_count
            pair["model_pair_review"] = {
                **review,
                "reviewer_type": "llm_semantic_review_not_human",
                "model_route": "t2_pair_review",
                **provider.provenance,
                "request_count": request_count,
                "cumulative_request_count": counts["pair_semantic_review"],
            }

        pair_decision = pair["model_pair_review"]["decision"]
        if pair_decision != "approve":
            counts["total"] = total_requests(counts)
            return {
                "status": (
                    "pair_semantic_rejected"
                    if pair_decision == "reject" else "pair_needs_revision"
                ),
                "stage": "pair_semantic_review",
            }
        if not pair["program_checks"]["scenario_approved_state_divergence"]:
            counts["total"] = total_requests(counts)
            return {
                "status": "no_supported_state_divergence",
                "stage": "task_viability",
            }

        if pair.get("llm_answer") is None:
            provider = self._provider("t2_answer")
            previous = int(counts.get("answer", 0) or 0)
            try:
                answer, request_count = generate_answer(
                    provider, pair["instance"], seed + 6000,
                )
            except Exception as exc:
                counts["answer"] = previous + int(
                    getattr(provider, "_call_index", 0) or 0
                )
                counts["total"] = total_requests(counts)
                return {
                    "status": "answer_failed",
                    "stage": "answer_generation",
                    "error": error_record(exc),
                }
            counts["answer"] = previous + request_count
            pair["llm_answer"] = answer
            pair["answer_provenance"] = {
                "model_route": "t2_answer",
                **provider.provenance,
                "request_count": request_count,
                "cumulative_request_count": counts["answer"],
                "machine_answer_not_ground_truth": True,
                "human_review": "pending",
            }

        if pair.get("model_answer_review") is None:
            provider = self._provider("t2_answer_review")
            previous = int(counts.get("answer_semantic_review", 0) or 0)
            try:
                review, request_count = review_answer(
                    provider, pair["instance"], pair["llm_answer"], seed + 7000,
                )
            except Exception as exc:
                counts["answer_semantic_review"] = previous + int(
                    getattr(provider, "_call_index", 0) or 0
                )
                counts["total"] = total_requests(counts)
                return {
                    "status": "answer_review_failed",
                    "stage": "answer_semantic_review",
                    "error": error_record(exc),
                }
            counts["answer_semantic_review"] = previous + request_count
            pair["model_answer_review"] = {
                **review,
                "reviewer_type": "llm_semantic_review_not_human",
                "model_route": "t2_answer_review",
                **provider.provenance,
                "request_count": request_count,
                "cumulative_request_count": counts["answer_semantic_review"],
            }

        counts["total"] = total_requests(counts)
        decision = pair["model_answer_review"]["decision"]
        return {
            "status": "completed" if decision == "approve" else "answer_review_rejected",
            "stage": "complete",
        }
