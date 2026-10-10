"""Run free-form model policies against the canonical environment."""

import json
from copy import deepcopy

from schemas.validate import validate_trajectory
from environment.policy_context import public_scenario_context
from environment.state_updater import UnsupportedConsequentialClaim


def _provider_request_count(provider):
    metrics = _provider_metrics(provider)
    if isinstance(metrics, dict):
        value = metrics.get("request_count")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    value = getattr(provider, "_call_index", None)
    return value if isinstance(value, int) else None


def _provider_metrics(provider):
    value = getattr(provider, "metrics", None)
    return value if isinstance(value, dict) else None


def _role_providers(environment, policy):
    providers = {
        "policy": getattr(policy, "provider", None),
        "appraisal": getattr(environment.state_updater, "provider", None),
        "response": getattr(environment.response_generator, "provider", None),
    }
    interaction = getattr(environment.state_updater, "interaction_appraiser", None)
    if interaction is not None:
        providers["interaction_appraisal"] = getattr(interaction, "provider", None)
    return providers


def _actual_request_counts(environment, policy):
    providers = _role_providers(environment, policy)
    counts = {
        role: _provider_request_count(provider)
        for role, provider in providers.items()
    }
    known = [value for value in counts.values() if isinstance(value, int)]
    counts["total"] = sum(known) if len(known) == len(providers) else None
    counts["environment_stage_count_per_turn"] = len(providers) - 1
    counts["actual_requests_can_include_retries"] = True
    return counts


def _provider_run_metrics(environment, policy):
    providers = _role_providers(environment, policy)
    by_role = {
        role: metrics
        for role, provider in providers.items()
        if (metrics := _provider_metrics(provider)) is not None
    }
    usage_keys = {
        key
        for metrics in by_role.values()
        for key in metrics.get("usage", {})
    }
    usage_total = {
        key: sum(
            int(metrics.get("usage", {}).get(key, 0))
            for metrics in by_role.values()
        )
        for key in sorted(usage_keys)
    }
    return {
        "by_role": by_role,
        "totals": {
            "request_duration_seconds": round(sum(
                float(metrics.get("request_duration_seconds", 0.0))
                for metrics in by_role.values()
            ), 3),
            "failed_request_count": sum(
                int(metrics.get("failed_request_count", 0))
                for metrics in by_role.values()
            ),
            "usage": usage_total,
        },
    }


class RolloutRunner:
    def __init__(
        self, environment_factory, logger=None,
        max_action_grounding_attempts=2,
        checkpoint_writer=None,
    ):
        if max_action_grounding_attempts < 1:
            raise ValueError("max_action_grounding_attempts must be positive")
        self.environment_factory = environment_factory
        self.logger = logger
        self.max_action_grounding_attempts = max_action_grounding_attempts
        self.checkpoint_writer = checkpoint_writer

    @staticmethod
    def _trajectory_snapshot(environment, policy):
        trajectory = environment.private_trajectory()
        trajectory["public_scenario_context"] = public_scenario_context(environment.scenario)
        trajectory["policy_id"] = policy.policy_id
        trajectory["policy_provenance"] = getattr(
            policy,
            "provenance",
            {"policy_id": policy.policy_id},
        )
        trajectory["actual_request_counts"] = _actual_request_counts(
            environment, policy
        )
        trajectory["provider_run_metrics"] = _provider_run_metrics(
            environment, policy
        )
        return trajectory

    def _write_checkpoint(self, environment, policy, status):
        if self.checkpoint_writer is None:
            return
        snapshot = self._trajectory_snapshot(environment, policy)
        snapshot["checkpoint_status"] = status
        self.checkpoint_writer(snapshot)

    def _run_turn(self, environment, policy):
        rejected = []
        for attempt in range(1, self.max_action_grounding_attempts + 1):
            observation = environment.observe()
            if rejected:
                observation["runtime_generation_feedback"] = {
                    "reason": "unsupported_consequential_claim",
                    "instruction": (
                        "The previous draft asserted a consequential fact that is "
                        "not established by public history. Remove it, state genuine "
                        "uncertainty, or make a proposal without treating it as fact."
                    ),
                    "unsupported_spans": [
                        item["claim_span"] for item in rejected[-1]["claims"]
                    ],
                }
            try:
                action = policy.generate(observation)
            except Exception as exc:
                if rejected:
                    exc.action_attempt_diagnostics = deepcopy(rejected)
                raise
            try:
                result = environment.step(action)
            except UnsupportedConsequentialClaim as exc:
                rejected.append({
                    "attempt": attempt,
                    "policy_action": deepcopy(action),
                    "reason": "unsupported_consequential_claim",
                    "claims": deepcopy(exc.claims),
                })
                if attempt == self.max_action_grounding_attempts:
                    exc.action_attempt_diagnostics = deepcopy(rejected)
                    raise
                continue
            if rejected:
                environment.session["turns"][-1][
                    "rejected_policy_action_attempts"
                ] = deepcopy(rejected)
            return result
        raise AssertionError("unreachable action grounding retry state")

    def run(self, policy, max_turns=None):
        environment = self.environment_factory()
        if hasattr(policy, "reset"):
            policy.reset()
        event_selection_key = json.dumps({
            "scenario_id": environment.scenario.get("scenario_id"),
            "policy_id": policy.policy_id,
            "model": getattr(policy, "provenance", {}).get("model"),
            "sampling": getattr(policy, "provenance", {}).get("sampling", {}),
        }, ensure_ascii=False, sort_keys=True)
        environment.reset(event_selection_key=event_selection_key)
        limit = max_turns or environment.scenario.get("max_turns", 20)
        try:
            while (
                environment.session["turn_id"] < limit
                and environment.session["status"] == "active"
            ):
                self._run_turn(environment, policy)
                self._write_checkpoint(environment, policy, "turn_completed")
        except Exception as exc:
            partial = self._trajectory_snapshot(environment, policy)
            partial["generation_error"] = {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "error_diagnostics": list(getattr(exc, "diagnostics", [])),
                "failed_after_completed_turns": len(partial.get("turns", [])),
                "failed_turn_context": getattr(exc, "failed_turn_context", None),
                "rejected_policy_action_attempts": deepcopy(
                    getattr(exc, "action_attempt_diagnostics", [])
                ),
            }
            if self.checkpoint_writer is not None:
                partial["checkpoint_status"] = "generation_error"
                self.checkpoint_writer(partial)
            exc.partial_trajectory = partial
            raise
        trajectory = self._trajectory_snapshot(environment, policy)
        validate_trajectory(trajectory)
        if self.checkpoint_writer is not None:
            completed = deepcopy(trajectory)
            completed["checkpoint_status"] = "trajectory_completed"
            self.checkpoint_writer(completed)
        if self.logger:
            self.logger.write(trajectory)
        return trajectory

    def run_many(self, policies, max_turns=None):
        return [self.run(policy, max_turns=max_turns) for policy in policies]
