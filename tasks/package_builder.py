"""Build reviewable T1--T4 packages with the active model routes.

The builder never reuses benchmark answers. T2 is admitted only from the
source-adapted pipeline; a missing T2 remains an explicit gap.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import time

from evaluation.leakage import assert_no_leaks
from offline.rollout_builders import build_t1_checkpoints, build_t3_candidates
from providers.factory import build_provider, public_provider_config
from tasks.T1.answering import generate_answer as generate_t1_answer
from tasks.T3.action_authoring import generate_actions
from tasks.T3.answering import (
    canonicalize_instance as canonicalize_t3_instance,
    generate_answer as generate_t3_answer,
)
from tasks.T4.answering import generate_judgment
from tasks.extraction import generate_extraction
from tasks.source_catalog import assess_source


BUILDER_ID = "scale300_active_task_packages"
PACKAGE_FORMAT = "socialflux_scale300_task_package_v4"
def now():
    return datetime.now(timezone.utc).isoformat()


def error_record(error, provider=None):
    return {
        "type": type(error).__name__,
        "message": str(error),
        "last_validation_error": str(getattr(error, "last_error", "")),
        "last_raw_output": str(getattr(error, "last_raw", ""))[-4000:],
        "request_count": int(
            getattr(error, "socialflux_request_count", None)
            or getattr(provider, "_call_index", 0)
            or 0
        ),
    }


def _attach_request_count(error, *providers):
    error.socialflux_request_count = sum(
        int(getattr(provider, "_call_index", 0) or 0)
        for provider in providers
        if provider is not None
    )
    return error


def _task_record(instance, answer, route_name, provider_config, request_count, status):
    assert_no_leaks(instance)
    return {
        "status": status,
        "instance": instance,
        "llm_answer": answer,
        "answer_status": "machine_proposal_pending_human_review",
        "formal_pool_eligible": False,
        "formal_pool_blockers": ["pending_human_review"],
        "model_route": route_name,
        "model_provenance": public_provider_config(provider_config),
        "request_count": int(request_count),
    }


class TaskPackageBuilder:
    """Generate one independent, auditable package from an eligible source."""

    def __init__(self, root, model_routes, *, t2_results=None):
        self.root = root
        self.model_routes = model_routes
        self.t2_results = t2_results or {}

    def _provider(self, route_name):
        config = self.model_routes.provider_config(route_name)
        return config, build_provider(config)

    def _extract(self, scenario, trajectory, ordinal):
        config, provider = self._provider("task_extraction")
        try:
            extraction = generate_extraction(
                provider,
                scenario,
                trajectory,
                seed=400000 + ordinal,
                max_attempts=2,
            )
        except Exception as exc:
            raise _attach_request_count(exc, provider)
        return extraction, {
            "model_route": "task_extraction",
            "model_provenance": public_provider_config(config),
            "request_count": int(getattr(provider, "_call_index", 0) or 0),
        }

    def _t1(self, scenario, trajectory, extraction, ordinal):
        selected = extraction["t1"][0]
        turn_ids = [turn["turn_id"] for turn in trajectory["turns"]]
        checkpoint_index = turn_ids.index(selected["checkpoint_turn_id"])
        instance = build_t1_checkpoints(
            trajectory,
            selected["target_state_ids"],
        )[checkpoint_index]
        instance.setdefault("metadata", {})["builder"] = BUILDER_ID
        instance["metadata"]["extraction_evidence_turn_ids"] = list(
            selected["evidence_turn_ids"]
        )
        instance["metadata"]["extraction_rationale"] = selected["rationale"]
        config, provider = self._provider("t1_answer")
        try:
            answer, requests = generate_t1_answer(
                provider, instance, 410000 + ordinal,
                private_persona=scenario["environment_agent"]["persona"],
                max_attempts=3,
            )
        except Exception as exc:
            raise _attach_request_count(exc, provider)
        return _task_record(
            instance, answer, "t1_answer", config, requests,
            "candidate_pending_human_review",
        )

    def _t2(self, ordinal, source_trajectory_id):
        result = self.t2_results.get(ordinal)
        if not result or result.get("status") != "completed":
            return None
        pair = result.get("pair") or {}
        if (pair.get("source_a") or {}).get("trajectory_id") != source_trajectory_id:
            return None
        if (pair.get("model_pair_review") or {}).get("decision") != "approve":
            return None
        if (pair.get("model_answer_review") or {}).get("decision") != "approve":
            return None
        instance = deepcopy(pair["instance"])
        answer = deepcopy(pair["llm_answer"])
        assert_no_leaks(instance)
        provenance = deepcopy(pair.get("answer_provenance") or {})
        return {
            "status": "candidate_pending_human_review",
            "instance": instance,
            "llm_answer": answer,
            "answer_status": "machine_proposal_pending_human_review",
            "formal_pool_eligible": False,
            "formal_pool_blockers": ["pending_human_review"],
            "model_route": "t2_answer",
            "model_provenance": provenance,
            "request_count": 0,
            "source_request_count": int(provenance.get("request_count", 0)),
            "source_adapted_pair": True,
        }

    def attach_t2(self, package):
        """Attach a newly completed T2 result without regenerating other tasks."""
        updated = deepcopy(package)
        t2 = self._t2(
            int(updated["ordinal"]),
            updated.get("source_trajectory_id"),
        )
        if t2 is None:
            return updated
        tasks = updated.setdefault("tasks", {})
        tasks["T2"] = t2
        updated.setdefault("task_gaps", {}).pop("T2", None)
        updated.setdefault("task_errors", {}).pop("T2", None)
        updated.setdefault("task_statuses", {})["T2"] = t2["status"]
        updated["status"] = (
            "constructed_all_task_machine_proposals"
            if set(tasks) == {"T1", "T2", "T3", "T4"}
            else "constructed_partial_machine_proposals"
        )
        updated["t2_attachment"] = {
            "attached_at_utc": now(),
            "source_adapted_pair": True,
            "source_request_count": t2["source_request_count"],
        }
        return updated

    def _t3(self, trajectory, scenario, extraction, ordinal):
        selected = extraction["t3"]
        if selected is None:
            raise ValueError("trajectory has no checkpoint with a five-turn future window")
        checkpoint_turn = next(
            turn
            for turn in trajectory["turns"]
            if turn["turn_id"] == selected["checkpoint_turn_id"]
        )
        checkpoint = {
            "history": checkpoint_turn["observation"].get("history", []),
            "current_observation": checkpoint_turn["observation"],
            "target_state_ids": selected["target_state_ids"],
        }
        action_config, action_provider = self._provider("t3_action_authoring")
        try:
            authored, action_requests = generate_actions(
                action_provider,
                checkpoint,
                420000 + ordinal,
                max_attempts=3,
            )
        except Exception as exc:
            raise _attach_request_count(exc, action_provider)
        candidate_actions = [
            {"text": row["text"]} for row in authored["actions"]
        ]
        delayed_horizon = int(scenario.get("t3_delayed_horizon", 5))
        available = int(selected["future_turns_available"])
        delayed_horizon = min(delayed_horizon, available, 10)
        if delayed_horizon < 5:
            raise ValueError("T3 delayed horizon is shorter than five turns")
        instance = build_t3_candidates(
            {
                **checkpoint_turn,
                "trajectory_id": trajectory["trajectory_id"],
                "scenario_id": trajectory["scenario_id"],
            },
            candidate_actions,
            delayed_horizon,
            selected["target_state_ids"],
        )
        instance = canonicalize_t3_instance(instance)
        instance.setdefault("metadata", {}).update({
            "builder": BUILDER_ID,
            "extraction_rationale": selected["rationale"],
            "candidate_action_strategies": [
                row["strategy"] for row in authored["actions"]
            ],
            "branch_validation_status": "pending_counterfactual_simulation",
        })
        answer_config, answer_provider = self._provider("t3_answer")
        try:
            answer, answer_requests = generate_t3_answer(
                answer_provider,
                instance,
                430000 + ordinal,
                private_persona=scenario["environment_agent"]["persona"],
                max_attempts=3,
            )
        except Exception as exc:
            raise _attach_request_count(exc, action_provider, answer_provider)
        record = _task_record(
            instance, answer, "t3_answer", answer_config, answer_requests,
            "candidate_pending_counterfactual_and_human_review",
        )
        record["action_authoring"] = {
            "model_route": "t3_action_authoring",
            "model_provenance": public_provider_config(action_config),
            "request_count": action_requests,
        }
        record["request_count"] += action_requests
        record["formal_pool_blockers"].append(
            "pending_counterfactual_branch_validation"
        )
        return record

    def _t4(self, trajectory, scenario, ordinal):
        config, provider = self._provider("t4_judge")
        try:
            packet, answer, requests = generate_judgment(
                provider,
                trajectory,
                scenario,
                440000 + ordinal,
                max_attempts=3,
            )
        except Exception as exc:
            raise _attach_request_count(exc, provider)
        return _task_record(
            packet, answer, "t4_judge", config, requests,
            "candidate_pending_human_review",
        )

    def build(self, ordinal, old_path, old_package, review, scenario):
        started = time.monotonic()
        assessment = assess_source(review, old_package, self.root)
        base = {
            "format": PACKAGE_FORMAT,
            "builder": BUILDER_ID,
            "created_at_utc": now(),
            "scenario_id": old_package["scenario_id"],
            "ordinal": ordinal,
            "source_quality": assessment,
            "source_package": str(old_path.relative_to(self.root)),
            "source_trajectory_id": old_package.get("source_trajectory_id"),
            "source_artifact": old_package.get("source_artifact"),
            "turn_count": old_package.get("turn_count"),
            "human_review": "pending",
        }
        if not assessment["eligible"]:
            return {
                **base,
                "status": "skipped_source_quality",
                "task_statuses": {},
                "tasks": {},
                "task_errors": {},
                "request_count": 0,
                "latency_seconds": round(time.monotonic() - started, 3),
            }

        trajectory = None
        tasks = {}
        errors = {}
        gaps = {}
        extraction = None
        extraction_record = None
        try:
            trajectory = json.loads(
                (self.root / old_package["source_artifact"]).read_text(
                    encoding="utf-8"
                )
            )
            extraction, extraction_record = self._extract(
                scenario, trajectory, ordinal
            )
        except Exception as exc:
            errors["extraction"] = error_record(exc)

        builders = {}
        if extraction is not None:
            builders = {"T1": lambda: self._t1(scenario, trajectory, extraction, ordinal)}
            if extraction["t3"] is None:
                gaps["T3"] = {
                    "reason": "insufficient_five_turn_future_window",
                    "construction_attempted": False,
                }
            else:
                builders["T3"] = lambda: self._t3(
                    trajectory, scenario, extraction, ordinal
                )
        for task_name, build_task in builders.items():
            try:
                tasks[task_name] = build_task()
            except Exception as exc:
                errors[task_name] = error_record(exc)

        try:
            t2 = self._t2(ordinal, old_package.get("source_trajectory_id"))
            if t2 is not None:
                tasks["T2"] = t2
            else:
                gaps["T2"] = {
                    "reason": "source_adapted_pair_unavailable",
                    "description": (
                        "No completed, source-matched, model-approved source-adapted "
                        "T2 pair is available; legacy pairs are not reused."
                    ),
                    "construction_attempted": False,
                }
        except Exception as exc:
            errors["T2"] = error_record(exc)

        try:
            if trajectory is None:
                trajectory = json.loads(
                    (self.root / old_package["source_artifact"]).read_text(
                        encoding="utf-8"
                    )
                )
            tasks["T4"] = self._t4(trajectory, scenario, ordinal)
        except Exception as exc:
            errors["T4"] = error_record(exc)

        request_count = sum(
            int(task.get("request_count", 0)) for task in tasks.values()
        ) + sum(int(error.get("request_count", 0)) for error in errors.values())
        if extraction_record is not None:
            request_count += extraction_record["request_count"]
        return {
            **base,
            "status": (
                "constructed_all_task_machine_proposals"
                if set(tasks) == {"T1", "T2", "T3", "T4"}
                else "constructed_partial_machine_proposals"
            ),
            "task_statuses": {
                name: task["status"] for name, task in tasks.items()
            },
            "tasks": tasks,
            "task_errors": errors,
            "task_gaps": gaps,
            "task_extraction": extraction_record,
            "request_count": request_count,
            "latency_seconds": round(time.monotonic() - started, 3),
        }
