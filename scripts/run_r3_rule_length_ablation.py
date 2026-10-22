#!/usr/bin/env python3
"""Run the R3 rule-profile × horizon diagnostic without changing formal T4."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.appraisal import ModelAppraiser
from environment.env import StatefulEnvironment
from environment.public_situation import build_public_situation
from environment.response_generator import ModelResponseGenerator
from environment.state_updater import ModelStateUpdater
from evaluation.instance_quality import audit_trajectory
from policies.model_policy import ModelPolicy
from providers.factory import build_provider, public_provider_config
from schemas.validate import validate_scenario, validate_trajectory
from scenario_design.catalog import discover_scenario_paths

VERSION = "r3_rule_length_ablation_v3"
CLOSURE_RE = re.compile(
    r"(?:今天|这次|我们)?(?:就|先)?(?:谈|聊|说)?到这里|"
    r"到此为止|先这样(?:吧)?|暂时不再继续|不必再谈|没有更多(?:要|可)?说"
)
REOPEN_RE = re.compile(
    r"[？?]|(?:接下来|下一步|后续|之后|以后|回头|下次|明天|下周|"
    r"再(?:谈|聊|确认|讨论|联系|推进))|"
    r"(?:我会|我将).{0,18}(?:再谈|联系|发送|提供|推进|处理|"
    r"确认|讨论|执行|转账|还款)"
)


class CountingProvider:
    """Count every physical provider request, including validation retries."""

    def __init__(self, provider, stage):
        self.provider = provider
        self.stage = stage
        self.requests = 0

    @property
    def provenance(self):
        return getattr(self.provider, "provenance", {})

    def complete(self, messages, **generation):
        self.requests += 1
        return self.provider.complete(messages, **generation)

    def reset(self):
        reset = getattr(self.provider, "reset", None)
        if reset:
            reset()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def natural_closure(action, response, turn_number, minimum_turns=4):
    """Conservative diagnostic stop: explicit closure and no future reopening."""
    if turn_number < minimum_turns:
        return False
    action = str(action).strip()
    response = str(response).strip()
    if CLOSURE_RE.search(response) and not REOPEN_RE.search(response):
        return True
    return bool(
        CLOSURE_RE.search(action)
        and CLOSURE_RE.search(response)
        and not REOPEN_RE.search(response)
    )


def semantic_natural_closure(turn, turn_number, minimum_turns=4):
    """Use appraisal semantics only at the final authored interaction fragment."""
    if turn_number < minimum_turns or turn.get("segment_transition_after"):
        return False
    after = turn.get("observation_after", {})
    longitudinal = after.get("longitudinal_context", {})
    if longitudinal.get("next_interaction"):
        return False
    diagnostics = turn.get("appraisal", {}).get("dialogue_diagnostics", {})
    continuation = diagnostics.get("continuation", {})
    if continuation.get("status") != "can_close":
        return False
    obligation = turn.get("interaction_ledger_after_public_events", {}).get(
        "latest_obligation"
    )
    return not obligation or obligation.get("status") not in {
        "awaiting_environment", "awaiting_evaluated_agent"
    }


def public_context(scenario):
    return {
        "background": scenario.get("background", ""),
        "public_situation": build_public_situation(scenario),
        "evaluated_agent_role": scenario.get("evaluated_agent_role", {}),
        "environment_role": scenario.get("environment_agent", {}).get("persona", {}),
    }


def request_counts(
    policy, appraisal, response, completed_turns, attempted_turns=None
):
    attempted_turns = completed_turns if attempted_turns is None else attempted_turns
    env_requests = appraisal.requests + response.requests
    total = policy.requests + env_requests
    return {
        "completed_turns": completed_turns,
        "attempted_turns": attempted_turns,
        "policy_requests": policy.requests,
        "appraisal_requests": appraisal.requests,
        "response_requests": response.requests,
        "environment_requests": env_requests,
        "total_requests": total,
        "nominal_environment_requests_for_attempted_turns": 2 * attempted_turns,
        "environment_retry_overhead": env_requests - 2 * attempted_turns,
        "nominal_all_stage_requests_for_attempted_turns": 3 * attempted_turns,
        "all_stage_retry_overhead": total - 3 * attempted_turns,
        "environment_llm_stage_count_per_turn": 2,
        "evaluated_policy_is_a_separate_third_stage": True,
    }


def build_components(scenario, source, condition):
    env_cfg = source["environment"]
    policy_spec = source["policies"][0]
    policy_provider = CountingProvider(build_provider(policy_spec["provider"]), "policy")
    appraisal_provider = CountingProvider(build_provider(env_cfg["provider"]), "appraisal")
    response_provider = CountingProvider(build_provider(env_cfg["provider"]), "response")
    profile = condition["validation_profile"]
    horizon = condition["horizon_mode"]
    # Keep model prompts and two-stage environment identical across cells.
    # The experiment varies only validator profile and horizon behavior.
    policy_prompt = "task_t4_action_v21"
    response_prompt = "environment_response_v25"
    appraisal_prompt = env_cfg.get(
        "appraisal_prompt_id", "environment_appraisal_v11"
    )
    provenance = {
        "format": VERSION,
        "appraisal_provider": public_provider_config(env_cfg["provider"]),
        "response_provider": public_provider_config(env_cfg["provider"]),
        "appraisal_sampling": deepcopy(env_cfg.get("sampling", {})),
        "response_sampling": deepcopy(env_cfg.get("sampling", {})),
        "appraisal_prompt": appraisal_prompt,
        "state_update": "deterministic_social_delta_calibrator_v1",
        "response_prompt": response_prompt,
        "validation_profile": profile,
        "horizon_mode": horizon,
        "llm_stage_count_per_step": 2,
        "nominal_llm_calls_per_step_without_retries": 2,
        "actual_requests_may_exceed_nominal": True,
        "calls_are_separate": True,
    }
    environment = StatefulEnvironment(
        scenario,
        state_updater=ModelStateUpdater(
            scenario, appraisal_provider, env_cfg.get("sampling", {}),
            appraiser=ModelAppraiser(
                scenario, appraisal_provider, env_cfg.get("sampling", {}),
                prompt_id=appraisal_prompt,
            ),
        ),
        response_generator=ModelResponseGenerator(
            response_provider,
            env_cfg.get("sampling", {}),
            prompt_id=response_prompt,
            validation_profile=profile,
            horizon_mode=horizon,
        ),
        provenance=provenance,
    )
    policy = ModelPolicy(
        f"diagnostic_{condition['id']}",
        policy_provider,
        prompt_id=policy_prompt,
        sampling=policy_spec.get("sampling", {}),
        provenance_extra={
            "source_type": policy_spec.get("source_type", "local"),
            "model_family": policy_spec.get("model_family", "unknown"),
            "diagnostic_condition": condition["id"],
        },
        validation_profile=profile,
        horizon_mode=horizon,
    )
    return environment, policy, policy_provider, appraisal_provider, response_provider


def execute_case(scenario, source, condition, max_turns, natural_min_turns):
    environment, policy, policy_counter, appraisal_counter, response_counter = (
        build_components(scenario, source, condition)
    )
    environment.reset(
        episode_id=f"{scenario['scenario_id']}__{condition['id']}"
    )
    error = None
    try:
        while (
            environment.session["status"] == "active"
            and environment.session["turn_id"] < max_turns
        ):
            action = policy.generate(environment.observe())
            _, turn = environment.step(action)
            if (
                condition["horizon_mode"] == "natural_max_20"
                and (
                    natural_closure(
                        turn["policy_action"]["text"],
                        turn["environment_response"],
                        environment.session["turn_id"],
                        natural_min_turns,
                    )
                    or semantic_natural_closure(
                        turn, environment.session["turn_id"], natural_min_turns
                    )
                )
            ):
                environment.session["status"] = "completed"
                environment.session["ending"] = {
                    "reason": "diagnostic_natural_closure",
                    "turn_id": environment.session["turn_id"],
                }
    except Exception as exc:
        error = {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "error_diagnostics": list(getattr(exc, "diagnostics", [])),
            "failed_turn_context": getattr(exc, "failed_turn_context", None),
        }
    trajectory = environment.private_trajectory()
    trajectory["public_scenario_context"] = public_context(scenario)
    trajectory["policy_id"] = policy.policy_id
    trajectory["policy_provenance"] = policy.provenance
    trajectory["diagnostic_condition"] = deepcopy(condition)
    turns = len(trajectory.get("turns", []))
    if error:
        error["failed_after_completed_turns"] = turns
        trajectory["generation_error"] = error
    if turns:
        validate_trajectory(trajectory)
        audit = audit_trajectory(trajectory)
    else:
        audit = {"passed": False, "checks": {}, "failed_checks": ["no_completed_turn"]}
    attempted_turns = turns + (1 if error else 0)
    counts = request_counts(
        policy_counter, appraisal_counter, response_counter, turns, attempted_turns
    )
    trajectory["diagnostic_evidence"] = {
        "generated_at_utc": utc_now(),
        "status": "generation_failed" if error else "generated",
        "formal_research_setting_changed": False,
        "natural_horizon_is_diagnostic_only": True,
        "machine_audit_is_diagnostic_not_acceptance": True,
        "review_status": "pending_model_semantic_review",
        "request_counts": counts,
        "machine_audit": audit,
    }
    return trajectory


def summarize_case(path, trajectory):
    evidence = trajectory["diagnostic_evidence"]
    audit = evidence["machine_audit"]
    checks = audit.get("checks", {})
    failed = audit.get("failed_checks") or [
        key for key, passed in checks.items() if not passed
    ]
    return {
        "path": str(path),
        "scenario_id": trajectory["scenario_id"],
        "condition_id": trajectory["diagnostic_condition"]["id"],
        "validation_profile": trajectory["diagnostic_condition"]["validation_profile"],
        "horizon_mode": trajectory["diagnostic_condition"]["horizon_mode"],
        "status": evidence["status"],
        "turns": len(trajectory.get("turns", [])),
        "ending": trajectory.get("ending"),
        "machine_audit_passed": audit.get("passed", False),
        "machine_audit_failed_checks": failed,
        "request_counts": evidence["request_counts"],
        "review_status": evidence["review_status"],
    }


def write_dialogues(path, cases):
    lines = [
        "# R3 rule × horizon diagnostic dialogues",
        "",
        "Natural closure is diagnostic only. Machine checks and Codex review are not human acceptance.",
        "",
    ]
    for case in cases:
        lines += [
            f"## {case['scenario_id']} · {case['diagnostic_condition']['id']}",
            "",
            f"Turns: {len(case.get('turns', []))}; ending: `{json.dumps(case.get('ending'), ensure_ascii=False)}`",
            "",
        ]
        for turn in case.get("turns", []):
            lines += [
                f"### {turn['turn_id']}", "",
                f"- Evaluated agent: {turn['policy_action']['text']}", "",
                f"- Environment: {turn['environment_response']}", "",
            ]
        error = case.get("generation_error")
        if error:
            lines += [f"Generation error: `{error['error_type']}: {error['error']}`", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/r3_rule_length_ablation.local.json")
    parser.add_argument("--scenarios", default="configs/scenarios")
    parser.add_argument("--output", default="build/r3_rule_length_ablation_v1")
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--scenario-id", action="append")
    parser.add_argument("--condition-id", action="append")
    parser.add_argument("--turn-cap", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if config.get("format") != "socialflux_r3_rule_length_ablation_v1":
        raise ValueError("unsupported diagnostic config")
    source = json.loads(Path(config["source_rollout_config"]).read_text(encoding="utf-8"))
    all_scenarios = {}
    for path in discover_scenario_paths(Path(args.scenarios)):
        item = json.loads(path.read_text(encoding="utf-8"))
        validate_scenario(item)
        all_scenarios[item["scenario_id"]] = item
    scenario_filter = set(args.scenario_id or config["scenario_ids"])
    condition_filter = set(args.condition_id or [
        item["id"] for item in config["conditions"]
    ])
    planned = [
        (all_scenarios[scenario_id], condition)
        for scenario_id in config["scenario_ids"]
        if scenario_id in scenario_filter
        for condition in config["conditions"]
        if condition["id"] in condition_filter
    ]
    if args.max_cases is not None:
        planned = planned[:args.max_cases]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    summaries = []
    for scenario, condition in planned:
        path = output / "trajectories" / f"{scenario['scenario_id']}__{condition['id']}.json"
        if args.resume and path.exists():
            trajectory = json.loads(path.read_text(encoding="utf-8"))
        else:
            print(f"START {scenario['scenario_id']} {condition['id']}", flush=True)
            trajectory = execute_case(
                scenario,
                source,
                condition,
                min(args.turn_cap or config["max_turns"], config["max_turns"]),
                config["natural_closure_min_turns"],
            )
            atomic_json(path, trajectory)
            print(
                f"DONE {scenario['scenario_id']} {condition['id']} "
                f"turns={len(trajectory.get('turns', []))} "
                f"status={trajectory['diagnostic_evidence']['status']}",
                flush=True,
            )
        cases.append(trajectory)
        summaries.append(summarize_case(path, trajectory))
        summary = {
            "format": VERSION,
            "updated_at_utc": utc_now(),
            "branch": "r3-diagnostic-rule-length-ablation",
            "baseline_frozen": "v53",
            "v54_status": "prepared_but_not_generated_superseded_by_ablation",
            "formal_horizon": "fixed_20_unchanged",
            "diagnostic_natural_horizon_only": True,
            "review_label_policy": {
                "codex_trajectory_reading": "model_semantic_review",
                "human_acceptance": "not_started",
            },
            "planned_case_count": len(planned),
            "completed_case_count": len(summaries),
            "cases": summaries,
        }
        atomic_json(output / "summary.json", summary)
        write_dialogues(output / "dialogues.md", cases)


if __name__ == "__main__":
    main()
