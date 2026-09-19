"""End-to-end builder for source-adapted SocialFlux T2 pairs."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from evaluation.leakage import assert_no_leaks
from providers.factory import build_provider
from providers.text import copies_latest_other_utterance
from tasks.T2.runtime import (
    ROOT,
    environment_call_counts,
    environment_for,
    flat_private,
    internal_direction,
    load,
    now,
    public_turn,
    scenario_path,
    selected_state_ids,
    supported_t2_candidates,
    target_preference_ids,
)
from tasks.T2.branch_authoring import author_branch
from tasks.T2.pair_completion import PairCompletion
from tasks.T2.source_selection import assess_source, find_audit_record, source_index


BUILDER_VERSION = "t2_source_adapted_v2"


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_json(value):
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_control(turn, *, behavior_override=None, scope="t2_source_a_replay"):
    control = {
        "control_scope": scope,
        "current_response": turn["environment_response"],
        "media": deepcopy(turn.get("media", [])),
    }
    behavior = behavior_override
    if behavior is None and "observable_expression" in turn:
        behavior = turn["observable_expression"]
    if behavior is not None:
        control["observable_expression"] = deepcopy(behavior)
    return control


def authored_control(turn):
    return {
        "control_scope": "t2_authored_b_replay",
        "current_response": turn["environment_character"],
        "media": [],
    }


def ending_public(log):
    return {
        "turn_id": log["turn_id"],
        "evaluated_agent": log["policy_action"]["text"],
        "environment_character": log["environment_response"],
        "observable_expression": deepcopy(log["observable_expression"]),
        "media": deepcopy(log["media"]),
    }


def public_source_turn(turn):
    return public_turn(turn)


def cross_speaker_echo_violations(history):
    """Surface exact ownership-risk echoes as diagnostics, not pass/fail rules."""
    violations = []
    previous_environment = ""
    for turn in history:
        turn_id = turn["turn_id"]
        agent = turn["evaluated_agent"]
        environment = turn["environment_character"]
        if previous_environment and (
            agent.strip() == previous_environment.strip()
            or copies_latest_other_utterance(agent, previous_environment)
        ):
            violations.append({"turn_id": turn_id, "speaker": "evaluated_agent"})
        if (
            environment.strip() == agent.strip()
            or copies_latest_other_utterance(environment, agent)
        ):
            violations.append({"turn_id": turn_id, "speaker": "environment_agent"})
        previous_environment = environment
    return violations


class T2PairBuilder:
    def __init__(self, model_routes, audit, *, run_id, selection_settings=None):
        self.model_routes = model_routes
        self.audit = audit
        self.run_id = run_id
        self.selection_settings = selection_settings or {}

    def _provider(self, route_name):
        return build_provider(self.model_routes.provider_config(route_name))

    def _result(self, spec, status, stage, **extra):
        result = {
            "format": "socialflux_t2_build_result_v2",
            "builder_version": BUILDER_VERSION,
            "run_id": self.run_id,
            "created_at_utc": now(),
            "ordinal": spec.get("ordinal"),
            "status": status,
            "stage": stage,
            "human_review": "pending",
        }
        result.update(extra)
        return result

    def _failed(self, spec, status, stage, error, **extra):
        error_record = {
            "type": type(error).__name__,
            "message": str(error),
        }
        if getattr(error, "last_error", None) is not None:
            error_record["last_validation_error"] = str(error.last_error)
        if getattr(error, "diagnostics", None):
            error_record["attempt_diagnostics"] = deepcopy(error.diagnostics)
        if getattr(error, "last_raw", None):
            error_record["last_raw_output"] = error.last_raw
        return self._result(
            spec, status, stage,
            error=error_record,
            **extra,
        )

    def build(self, spec):
        try:
            scenario = load(scenario_path(spec["ordinal"]))
            source_path = ROOT / spec["source_rollout"]
            source = load(source_path)
        except Exception as exc:
            return self._failed(spec, "skipped_source_quality", "source_selection", exc)

        audit_record = find_audit_record(
            self.audit,
            ordinal=spec["ordinal"],
            trajectory_id=source.get("trajectory_id"),
        )
        selection = assess_source(
            spec, scenario, source, audit_record, self.selection_settings,
        )
        base = {
            "scenario_id": scenario["scenario_id"],
            "scenario_title": scenario.get("title"),
            "relationship": spec.get("relationship"),
            "source_selection": selection,
            "request_counts": {},
        }
        if not selection["eligible"]:
            return self._result(
                spec, "skipped_source_quality", "source_selection", **base,
            )

        indexes = source_index(source)
        fork_index = indexes[spec["fork_turn_id"]]
        ending_index = indexes[spec["ending_turn_id"]]
        source_turns = source["turns"]
        prefix_source = source_turns[:fork_index]
        a_tail_source = source_turns[fork_index:ending_index]
        ending_source = source_turns[ending_index]
        fork_snapshot = deepcopy(source_turns[fork_index]["environment_snapshot_before"])
        seed = 97000 + spec["ordinal"] * 10

        public_prefix = [public_source_turn(turn) for turn in prefix_source]
        public_a_tail = [public_source_turn(turn) for turn in a_tail_source]
        shared_ending_seed = {
            "turn_id": ending_source["turn_id"],
            "evaluated_agent": ending_source["policy_action"]["text"],
            "environment_character": ending_source["environment_response"],
            "observable_expression": deepcopy(spec["shared_ending_behavior"]),
        }

        author_provider = self._provider("t2_branch_authoring")
        try:
            authored, author_requests = author_branch(
                author_provider, spec, scenario, public_prefix, public_a_tail,
                shared_ending_seed, seed + 2000,
            )
            base["request_counts"]["branch_authoring"] = author_requests
            base["authored_branch"] = authored
        except Exception as exc:
            base["request_counts"]["branch_authoring"] = int(
                getattr(author_provider, "_call_index", 0) or 0
            )
            return self._failed(
                spec, "branch_authoring_failed", "branch_authoring", exc, **base,
            )

        appraisal_config = self.model_routes.provider_config("appraisal")
        response_config = self.model_routes.provider_config("response")
        env_a = environment_for(
            scenario, appraisal_config, response_config, seed,
        )
        env_b = environment_for(
            scenario, appraisal_config, response_config, seed + 1,
        )
        replay_a = []
        replay_b = []
        try:
            env_a.restore(
                fork_snapshot,
                episode_id=f"{scenario['scenario_id']}_{self.run_id}_t2_a",
            )
            env_a.session["counterfactual_timeline_lock"] = True
            for source_turn in a_tail_source:
                _, log = env_a.step(
                    deepcopy(source_turn["policy_action"]),
                    controlled_observation=source_control(source_turn),
                )
                replay_a.append(log)
            _, ending_a = env_a.step(
                deepcopy(ending_source["policy_action"]),
                controlled_observation=source_control(
                    ending_source,
                    behavior_override=spec["shared_ending_behavior"],
                    scope="t2_shared_ending",
                ),
            )

            env_b.restore(
                fork_snapshot,
                episode_id=f"{scenario['scenario_id']}_{self.run_id}_t2_b",
            )
            env_b.session["counterfactual_timeline_lock"] = True
            for authored_turn in authored["turns"]:
                _, log = env_b.step(
                    {"text": authored_turn["evaluated_agent"]},
                    controlled_observation=authored_control(authored_turn),
                )
                replay_b.append(log)
            _, ending_b = env_b.step(
                deepcopy(ending_source["policy_action"]),
                controlled_observation=source_control(
                    ending_source,
                    behavior_override=spec["shared_ending_behavior"],
                    scope="t2_shared_ending",
                ),
            )
            base["request_counts"]["environment_a_replay"] = environment_call_counts(env_a)
            base["request_counts"]["environment_b_replay"] = environment_call_counts(env_b)
        except Exception as exc:
            base["request_counts"]["environment_a_replay"] = environment_call_counts(env_a)
            base["request_counts"]["environment_b_replay"] = environment_call_counts(env_b)
            base["replay_progress"] = {
                "a_completed_turns": len(replay_a),
                "b_completed_turns": len(replay_b),
                "failed_turn_context": deepcopy(getattr(exc, "failed_turn_context", None)),
            }
            return self._failed(spec, "replay_failed", "formal_environment_replay", exc, **base)

        try:
            pair = self._assemble_pair(
                spec=spec,
                scenario=scenario,
                source=source,
                source_path=source_path,
                selection=selection,
                fork_index=fork_index,
                ending_index=ending_index,
                fork_snapshot=fork_snapshot,
                prefix_source=prefix_source,
                a_tail_source=a_tail_source,
                ending_source=ending_source,
                authored=authored,
                replay_a=replay_a,
                replay_b=replay_b,
                ending_a=ending_a,
                ending_b=ending_b,
                request_counts=deepcopy(base["request_counts"]),
            )
        except Exception as exc:
            return self._failed(
                spec, "assembly_failed", "pair_assembly", exc, **base,
            )
        base.pop("authored_branch", None)
        base["pair"] = pair

        outcome = PairCompletion(self.model_routes).complete(pair, seed)
        if outcome.get("error"):
            base["error"] = outcome["error"]

        return self._result(
            spec, outcome["status"], outcome["stage"], **base,
        )

    def resume(self, spec, prior_result):
        """Resume review/answer stages without replaying the environment."""
        if prior_result.get("run_id") != self.run_id:
            raise ValueError("cannot resume a result from another run")
        pair = prior_result.get("pair")
        if not isinstance(pair, dict):
            raise ValueError("resume requires a saved replayed pair")
        resumable_stages = {"pair_semantic_review", "answer_generation", "answer_semantic_review"}
        prior_stage = prior_result.get("stage")
        if prior_stage not in resumable_stages:
            raise ValueError(f"result stage is not resumable: {prior_stage}")
        history = list(prior_result.get("attempt_history", []))
        history.append({
            "status": prior_result.get("status"),
            "stage": prior_result.get("stage"),
            "error": deepcopy(prior_result.get("error")),
            "request_counts_before_resume": deepcopy(pair.get("request_counts", {})),
        })
        if prior_stage == "pair_semantic_review":
            pair["model_pair_review"] = None
        if prior_stage == "answer_semantic_review":
            pair["model_answer_review"] = None
        outcome = PairCompletion(self.model_routes).complete(
            pair, 97000 + spec["ordinal"] * 10,
        )
        extra = {
            "scenario_id": prior_result.get("scenario_id"),
            "scenario_title": prior_result.get("scenario_title"),
            "relationship": prior_result.get("relationship"),
            "source_selection": deepcopy(prior_result.get("source_selection")),
            "request_counts": deepcopy(pair.get("request_counts", {})),
            "pair": pair,
            "attempt_history": history,
        }
        if outcome.get("error"):
            extra["error"] = outcome["error"]
        return self._result(
            spec, outcome["status"], outcome["stage"], **extra,
        )

    def _assemble_pair(
        self, *, spec, scenario, source, source_path, selection, fork_index,
        ending_index, fork_snapshot, prefix_source, a_tail_source, ending_source,
        authored, replay_a, replay_b, ending_a, ending_b, request_counts,
    ):
        history_a = [public_source_turn(turn) for turn in source["turns"][:ending_index]]
        history_b = [public_source_turn(turn) for turn in prefix_source + replay_b]
        ending_a_public = ending_public(ending_a)
        ending_b_public = ending_public(ending_b)
        state_a = flat_private(ending_a)
        state_b = flat_private(ending_b)
        changed = supported_t2_candidates(scenario, state_a, state_b)
        candidate_state_ids = list(dict.fromkeys(
            changed + target_preference_ids(scenario) + selected_state_ids(scenario)
        ))[:8]
        target = ending_a["observation_after"]["target_character"]
        instance_id = f"{scenario['scenario_id']}_T2_{self.run_id}"
        instance = {
            "instance_id": instance_id,
            "benchmark_version": "socialflux_t2_source_adapted_v2",
            "story_id": scenario["scenario_id"],
            "task_type": "T2_history_sensitive_merge",
            "language": "zh",
            "modality": "text_with_observable_behavior_reference",
            "input": {
                "target_character": target,
                "shared_background": scenario["background"],
                "history_a": history_a,
                "history_b": history_b,
                "shared_current_action": {
                    "turn_id": ending_a_public["turn_id"],
                    "text": ending_a_public["evaluated_agent"],
                },
                "shared_current_observation": {
                    "current_response": ending_a_public["environment_character"],
                    "observable_cues": deepcopy(
                        ending_a_public["observable_expression"].get("behavioral_cues", [])
                    ),
                    "observable_expression": deepcopy(ending_a_public["observable_expression"]),
                    "media": deepcopy(ending_a_public["media"]),
                },
            },
            "target_spec": {
                "prediction_format": "pairwise_state_difference_v2_sparse",
                "target_character_id": target.get(
                    "name", scenario["environment_agent"]["persona"].get("name"),
                ),
                "candidate_state_ids": candidate_state_ids,
                "select_state_count": {"minimum": 1, "maximum": 3},
                "direction_labels": [
                    "higher_in_a", "similar", "higher_in_b", "cannot_determine",
                ],
                "requires_bilateral_evidence_when_determinate": True,
                "allows_empty_side_evidence_for_cannot_determine": True,
                "requires_key_history_events": True,
                "requires_shared_expression_explanation": True,
                "ground_truth_source": "human_verification_of_llm_answer",
            },
            "ground_truth": None,
            "label_status": "llm_answer_pending_human_verification",
            "metadata": {
                "construction": "real_a_complete_authored_b_formal_replay_shared_ending",
                "source_a_trajectory_id": source.get("trajectory_id"),
                "fork_turn_id": spec["fork_turn_id"],
                "shared_prefix_turns": fork_index,
                "branch_turns_before_ending": len(a_tail_source),
                "controlled_ending_source_turn_id": spec["ending_turn_id"],
                "same_checkpoint_for_a_b": True,
                "a_state_suffix_recomputed": True,
                "b_state_suffix_recomputed": True,
                "environment_stage_count_per_turn": 2,
                "private_state_exposed": False,
                "human_review": "pending",
            },
        }
        assert_no_leaks(instance)

        replay_a_public = [public_turn(turn) for turn in replay_a]
        expected_a_public = [public_turn(turn) for turn in a_tail_source]
        checks = {
            "source_a_public_history_preserved": history_a == [
                public_turn(turn) for turn in source["turns"][:ending_index]
            ],
            "source_a_replayed_suffix_preserved": replay_a_public == expected_a_public,
            "shared_prefix_identical": history_a[:fork_index] == history_b[:fork_index],
            "histories_distinct_after_fork": history_a[fork_index:] != history_b[fork_index:],
            "history_lengths_match": len(history_a) == len(history_b),
            "controlled_ending_identical_between_a_b": ending_a_public == ending_b_public,
            "formal_two_stage_fields_present_a": all(
                all(key in log for key in ("appraisal", "calibration", "state_after", "environment_response"))
                for log in replay_a + [ending_a]
            ),
            "formal_two_stage_fields_present_b": all(
                all(key in log for key in ("appraisal", "calibration", "state_after", "environment_response"))
                for log in replay_b + [ending_b]
            ),
            "scenario_approved_state_divergence": bool(changed),
            "source_human_acceptance_not_claimed": not selection["audit"]["human_acceptance_claimed"],
        }
        structural_keys = set(checks) - {"scenario_approved_state_divergence"}
        failed = [key for key in structural_keys if not checks[key]]
        if failed:
            raise ValueError(f"T2 structural program checks failed: {failed}")

        internal_directions = {
            state_id: internal_direction(state_a, state_b, state_id)
            for state_id in candidate_state_ids
        }
        request_counts.update({
            "environment_stage_count_per_turn": 2,
            "actual_requests_include_retries": True,
        })
        return {
            "format": "socialflux_t2_source_adapted_pair_v2",
            "builder_version": BUILDER_VERSION,
            "run_id": self.run_id,
            "created_at_utc": now(),
            "scenario_id": scenario["scenario_id"],
            "scenario_title": scenario.get("title"),
            "relationship": spec.get("relationship"),
            "source_a": {
                "trajectory_id": source.get("trajectory_id"),
                "artifact_path": spec["source_rollout"],
                "artifact_sha256": sha256_file(source_path),
                "quality_selection": selection,
                "selected_ending_turn_id": spec["ending_turn_id"],
                "original_rollout_turn_count": len(source["turns"]),
                "public_history_sha256": sha256_json(history_a),
            },
            "adaptation": {
                "fork_turn_id": spec["fork_turn_id"],
                "checkpoint_sha256": sha256_json(fork_snapshot),
                "adaptation_point": spec["adaptation_point"],
                "history_b_direction": spec["history_b_direction"],
                "protected_facts": deepcopy(spec["protected_facts"]),
                "b_authoring": "single_complete_history_call_then_formal_controlled_replay",
                "authoring_summary": authored["authoring_summary"],
                "external_timeline_after_fork": "locked_no_fill_events",
            },
            "instance": instance,
            "llm_answer": None,
            "answer_provenance": None,
            "backend": {
                "private_environment_persona": deepcopy(
                    scenario["environment_agent"]["persona"]
                ),
                "state_a": state_a,
                "state_b": state_b,
                "changed_state_ids": changed,
                "internal_directions_not_ground_truth": internal_directions,
                "expression_intent_a": ending_a.get("response_expression_intent"),
                "expression_intent_b": ending_b.get("response_expression_intent"),
                "ending_log_a": ending_a,
                "ending_log_b": ending_b,
                "recomputed_suffix_logs_a": replay_a,
                "recomputed_suffix_logs_b": replay_b,
                "authored_branch": deepcopy(authored),
            },
            "program_checks": checks,
            "diagnostics": {
                "cross_speaker_echo_a": cross_speaker_echo_violations(history_a),
                "cross_speaker_echo_b": cross_speaker_echo_violations(history_b),
            },
            "media": {
                "status": "not_generated",
                "same_asset_required_for_text_video": True,
                "shared_asset_id": None,
                "actual_av_review": "not_started",
            },
            "request_counts": request_counts,
            "model_pair_review": None,
            "model_answer_review": None,
            "human_review": "pending",
        }
