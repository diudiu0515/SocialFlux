"""Independent, evidence-complete state and interaction appraisals."""

from __future__ import annotations

from copy import deepcopy

from providers.structured import complete_json

from .appraisal import (
    SOCIAL_ACTS,
    _exact_span_or_empty,
    _validate_dialogue_diagnostics,
    _validate_ledger_resolutions,
    appraisal_preserves_action_owner,
)
from .appraisal_normalization import canonicalize_social_act
from .calibration import FEATURE_NAMES, immediate_update_contract
from .appraisal_context import semantic_context, refreshed_memory
from .delta_mapper import flatten_state
from .interaction_ledger import validate_semantic_ledger_events
from .observation import build_public_evaluated_role
from .prompts import build_appraisal_prompt
from .public_situation import render_public_background
from .state_ontology import build_state_semantics


JUDGMENT_LABELS = {
    "no_relevant_evidence",
    "repeated_evidence_only",
    "ordinary_new_evidence",
    "decisive_new_evidence",
}
_JUDGMENT_KEYS = {
    "variable", "judgment", "direction", "evidence_span",
    "directness", "evidence_feature", "rationale",
}


def _provider_audit_records(provider):
    return list(getattr(provider, "audit_records", []))


def _validate_evidence_ids(value, allowed):
    if not isinstance(value, list):
        raise ValueError("evidence_turn_ids must be a list")
    allowed = set(allowed or [])
    result = []
    for item in value:
        if isinstance(item, str) and item in allowed and item not in result:
            result.append(item)
        if len(result) == 4:
            break
    return result


def _validate_features(value):
    if not isinstance(value, dict) or set(value) != set(FEATURE_NAMES):
        raise ValueError("event_features must contain every fixed feature exactly once")
    for name, amount in value.items():
        if isinstance(amount, bool) or not isinstance(amount, int) or amount not in range(-2, 3):
            raise ValueError(f"event feature {name} must be an integer from -2 to 2")
    return dict(value)


def _validate_judgments(items, variables, action_text, semantics, features, label):
    if not isinstance(items, list):
        raise ValueError(f"{label} must be a list")
    variables = list(variables)
    if len(items) != len(variables):
        raise ValueError(f"{label} must judge every supplied variable exactly once")
    by_variable = {}
    impacts = []
    diagnostics = []
    for raw in items:
        if not isinstance(raw, dict) or set(raw) != _JUDGMENT_KEYS:
            raise ValueError(f"each {label} item must contain exactly {sorted(_JUDGMENT_KEYS)}")
        item = deepcopy(raw)
        variable = item["variable"]
        if variable not in variables or variable in by_variable:
            raise ValueError(f"{label} has an unknown or repeated variable {variable!r}")
        if item["judgment"] not in JUDGMENT_LABELS:
            raise ValueError(f"{label} has an invalid judgment")
        if not isinstance(item["rationale"], str) or not item["rationale"].strip():
            raise ValueError(f"{label} rationale must be non-empty text")
        is_new = item["judgment"] in {
            "ordinary_new_evidence", "decisive_new_evidence"
        }
        if is_new:
            if item["direction"] not in {"increase", "decrease"}:
                raise ValueError(f"{label} new evidence needs a direction")
            if item["directness"] not in {"direct", "indirect"}:
                raise ValueError(f"{label} new evidence needs directness")
            if (
                item["evidence_feature"] is not None
                and item["evidence_feature"] not in FEATURE_NAMES
            ):
                raise ValueError(
                    f"{label} evidence_feature must be null or a fixed feature"
                )
            _exact_span_or_empty(item["evidence_span"], action_text, label)
        elif not (
            item["direction"] is None
            and item["directness"] is None
            and item["evidence_feature"] is None
            and item["evidence_span"] == ""
        ):
            raise ValueError(f"{label} no/repeated evidence must use null fields and an empty span")

        allowed_features = set((semantics.get(variable) or {}).get("evidence_features", []))
        feature = item["evidence_feature"]
        if not is_new:
            interface_status = "not_applicable"
        elif feature is None:
            interface_status = "unmapped_auxiliary_feature"
        elif feature not in allowed_features:
            interface_status = "variable_feature_mismatch"
        elif features.get(feature, 0) == 0:
            interface_status = "zero_feature"
        else:
            interface_status = "valid"
        item["semantic_strength"] = (
            2 if item["judgment"] == "decisive_new_evidence"
            else 1 if item["judgment"] == "ordinary_new_evidence"
            else 0
        )
        item["feature_interface_validation"] = interface_status
        diagnostics.append(item)
        by_variable[variable] = item
        if is_new:
            impacts.append({
                "variable": variable,
                "direction": item["direction"],
                "evidence_feature": feature,
                "evidence_span": item["evidence_span"],
                "evidence_strength": item["semantic_strength"],
                "directness": item["directness"],
                "new_evidence": True,
            })
    if set(by_variable) != set(variables):
        raise ValueError(f"{label} omitted supplied variables")
    return diagnostics, impacts



def _base_messages(scenario, prompt_id, *, action, previous_state, previous_dynamics,
                   memory, longitudinal_context, interaction_ledger,
                   appraisal_context=None, system_prompt):
    agent = scenario["environment_agent"]
    evaluated = build_public_evaluated_role(scenario.get("evaluated_agent_role", {}))
    semantics = build_state_semantics(scenario)
    if prompt_id in {
        "environment_state_appraisal_v5_immediate_context",
        "environment_state_appraisal_v6_observed_evidence",
    }:
        appraisal_context = semantic_context(appraisal_context, action)
        memory = refreshed_memory(memory, appraisal_context)
        contract = immediate_update_contract()
        semantics["update_policy"] = contract
        for entry in semantics["variables"].values():
            entry["update_rule"] = "Use state_semantics.update_policy; timescale does not gate an update."
        semantics["global_rules"] = [
            rule for rule in semantics["global_rules"]
            if "At a 0 or 10 boundary" not in rule
        ]
        semantics["global_rules"].append("Judge evidence independently of numeric endpoints; Python clips deltas at 0 and 10.")
    if prompt_id == "environment_state_appraisal_v6_observed_evidence":
        for entry in semantics["variables"].values():
            entry.pop("scenario_transition_evidence", None)
        semantics["interpretation"] = (
            "These entries define constructs and evidence requirements. The "
            "initialization rationale explains the starting belief only and is "
            "not new evidence. Judge the observed current action in the actual "
            "history; no authored hypothetical transition is a matching target "
            "or an additional necessary condition."
        )
    if "environment_background" in scenario:
        # Author explanations may mention another role's undisclosed facts.
        # Keep numeric starting values, definitions, and actual role context;
        # do not silently treat author omniscience as environment knowledge.
        for entry in semantics["variables"].values():
            entry.pop("scenario_initialization_rationale", None)
            entry.pop("scenario_transition_evidence", None)
        semantics["interpretation"] = (
            "Judge the supplied environment state using variable definitions, "
            "role-visible background and observed dialogue. Author-only "
            "initialization explanations and hypothetical transitions are not "
            "observed facts and are intentionally not supplied."
        )
    prompt = build_appraisal_prompt(
        persona=agent["persona"],
        background=render_public_background(scenario),
        explicit_goal=agent["explicit_goal"],
        hidden_intention=agent["hidden_intention"],
        evaluated_agent=evaluated,
        previous_state=previous_state,
        previous_dynamics=previous_dynamics,
        memory=memory,
        action=action,
        longitudinal_context=longitudinal_context,
        interaction_ledger=interaction_ledger,
        appraisal_context=appraisal_context,
        state_semantics=semantics,
        prompt_id=prompt_id,
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]


class ModelStateAppraiser:
    """Judge every supplied state/dynamics variable; never select updates."""

    def __init__(self, scenario, provider, sampling=None,
                 prompt_id="environment_state_appraisal_v1_per_variable"):
        self.scenario = deepcopy(scenario)
        self.provider = provider
        self.sampling = dict(sampling or {})
        configured = self.sampling.get("max_tokens", 0)
        if isinstance(configured, bool) or not isinstance(configured, int):
            raise ValueError("state appraisal max_tokens must be an integer")
        self.sampling["max_tokens"] = max(6000, configured)
        self.prompt_id = prompt_id

    @property
    def provenance(self):
        return {
            **getattr(self.provider, "provenance", {}),
            "prompt_id": self.prompt_id,
            "sampling": dict(self.sampling),
        }

    def appraise(self, *, action, previous_state, previous_dynamics, memory,
                 longitudinal_context=None, interaction_ledger=None,
                 appraisal_context=None):
        semantics = build_state_semantics(self.scenario)
        variable_semantics = semantics.get("variables", semantics)
        state_variables = list(flatten_state(previous_state))
        dynamics_variables = list(flatten_state(previous_dynamics))
        messages = _base_messages(
            self.scenario, self.prompt_id,
            action=action, previous_state=previous_state,
            previous_dynamics=previous_dynamics, memory=memory,
            longitudinal_context=longitudinal_context,
            interaction_ledger=interaction_ledger,
            appraisal_context=appraisal_context,
            system_prompt=(
                "你是环境私有的逐变量 state appraisal 分析器。只判断环境角色的"
                "state、dynamics 证据和 event features；不处理 ledger、对话诊断、"
                "回应或数值更新。只返回指定 JSON。"
            ),
        )
        audit_start = len(_provider_audit_records(self.provider))
        retry_diagnostics = []

        def validate(result):
            required = {
                "event_features", "state_judgments", "dynamics_judgments",
                "evidence_turn_ids",
            }
            if not isinstance(result, dict) or set(result) != required:
                raise ValueError(f"state appraisal must contain exactly {sorted(required)}")
            features = _validate_features(result["event_features"])
            state_judgments, state_impacts = _validate_judgments(
                result["state_judgments"], state_variables,
                str(action.get("text", "")).strip(), variable_semantics, features,
                "state_judgments",
            )
            dynamics_judgments, dynamics_impacts = _validate_judgments(
                result["dynamics_judgments"], dynamics_variables,
                str(action.get("text", "")).strip(), variable_semantics, features,
                "dynamics_judgments",
            )
            return {
                "appraisal": {
                    "event_features": features,
                    "state_impacts": state_impacts,
                    "dynamics_impacts": dynamics_impacts,
                },
                "state_judgments": state_judgments,
                "dynamics_judgments": dynamics_judgments,
                "evidence_turn_ids": _validate_evidence_ids(
                    result["evidence_turn_ids"], memory.get("relevant_turn_ids", [])
                ),
            }

        result = complete_json(
            self.provider, messages, self.sampling, validate,
            context="state appraiser", diagnostics_sink=retry_diagnostics,
            repair_unescaped_interior_quotes=True,
        )
        result["request_messages"] = messages
        result["request_sampling"] = dict(self.sampling)
        result["provider_audit_records"] = _provider_audit_records(self.provider)[audit_start:]
        result["request_retry_diagnostics"] = retry_diagnostics
        return result


class ModelInteractionAppraiser:
    """Extract ledger events, proposal resolutions, and dialogue diagnostics."""

    def __init__(self, scenario, provider, sampling=None,
                 prompt_id="environment_interaction_appraisal_v1"):
        self.scenario = deepcopy(scenario)
        self.provider = provider
        self.sampling = dict(sampling or {})
        configured = self.sampling.get("max_tokens", 0)
        if isinstance(configured, bool) or not isinstance(configured, int):
            raise ValueError("interaction appraisal max_tokens must be an integer")
        self.sampling["max_tokens"] = max(3500, configured)
        self.prompt_id = prompt_id

    @property
    def provenance(self):
        return {
            **getattr(self.provider, "provenance", {}),
            "prompt_id": self.prompt_id,
            "sampling": dict(self.sampling),
        }

    def appraise(self, *, action, previous_state, previous_dynamics, memory,
                 longitudinal_context=None, interaction_ledger=None,
                 appraisal_context=None):
        agent = self.scenario["environment_agent"]
        evaluated = build_public_evaluated_role(self.scenario.get("evaluated_agent_role", {}))
        messages = _base_messages(
            self.scenario, self.prompt_id,
            action=action, previous_state=previous_state,
            previous_dynamics=previous_dynamics, memory=memory,
            longitudinal_context=longitudinal_context,
            interaction_ledger=interaction_ledger,
            appraisal_context=appraisal_context,
            system_prompt=(
                "你是结构化 interaction appraisal 分析器。最新 action 的唯一作者是 "
                f"evaluated_agent：{evaluated.get('name', '被评估参与者')}。只处理"
                "意图、social act、ledger 和 dialogue diagnostics；不判断 state、"
                "dynamics、event features 或数值更新。只返回指定 JSON。"
            ),
        )
        audit_start = len(_provider_audit_records(self.provider))
        retry_diagnostics = []

        def validate(result):
            if not isinstance(result, dict) or set(result) != {"appraisal", "evidence_turn_ids"}:
                raise ValueError("interaction appraisal needs appraisal and evidence_turn_ids")
            value = result["appraisal"]
            required = {
                "speaker_intent", "social_act", "ledger_events",
                "ledger_resolutions", "dialogue_diagnostics",
            }
            if not isinstance(value, dict) or set(value) != required:
                raise ValueError(f"interaction appraisal must contain exactly {sorted(required)}")
            if not isinstance(value["speaker_intent"], str) or not value["speaker_intent"].strip():
                raise ValueError("speaker_intent must be non-empty text")
            if not appraisal_preserves_action_owner(value, agent.get("persona", agent)):
                raise ValueError("speaker_intent assigned the action to environment_agent")
            value["social_act"] = canonicalize_social_act(value["social_act"], SOCIAL_ACTS)
            normalization_log = []
            value["ledger_events"] = validate_semantic_ledger_events(
                value["ledger_events"], str(action.get("text", "")).strip(),
                "evaluated_agent", drop_irrelevant=True,
                normalize_tentative_commitments=True,
                normalize_pending_commitments=True,
                drop_acceptance_commitments=True,
                drop_acceptance_events=True,
                active_proposals=(interaction_ledger or {}).get("active_proposals", []),
                normalization_log=normalization_log,
                require_assertion_mode=True,
            )
            _validate_ledger_resolutions(
                value["ledger_resolutions"], str(action.get("text", "")).strip(),
                (interaction_ledger or {}).get("active_proposals", []),
            )
            _validate_dialogue_diagnostics(
                value["dialogue_diagnostics"], str(action.get("text", "")).strip(),
                require_after_direct_response=True,
                live_questions=(longitudinal_context or {}).get("segment", {}).get("live_questions", []),
            )
            if normalization_log:
                value["ledger_event_normalizations"] = normalization_log
            return {
                "appraisal": value,
                "evidence_turn_ids": _validate_evidence_ids(
                    result["evidence_turn_ids"], memory.get("relevant_turn_ids", [])
                ),
            }

        result = complete_json(
            self.provider, messages, self.sampling, validate,
            context="interaction appraiser", diagnostics_sink=retry_diagnostics,
            repair_unescaped_interior_quotes=True,
        )
        result["request_messages"] = messages
        result["request_sampling"] = dict(self.sampling)
        result["provider_audit_records"] = _provider_audit_records(self.provider)[audit_start:]
        result["request_retry_diagnostics"] = retry_diagnostics
        return result
