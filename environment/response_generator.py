"""Model-generated, state-conditioned environment responses."""


from environment.dialogue_support import (
    apply_hard_only_prompt_profile,
    horizon_guidance,
    validate_generation_options,
)
from prompts.loader import render_prompt
from providers.structured import complete_json
from providers.text import (
    strip_outer_dialogue_quotes,
)

from . import response_validation
from .response_completion import complete_environment_response


_STRUCTURED_RESPONSE_PROMPTS = frozenset(
    f"environment_response_v{version}" for version in range(19, 26)
)


class ResponseGenerator:
    def generate(self, context):
        raise NotImplementedError


class ModelResponseGenerator(ResponseGenerator):
    def __init__(
        self, provider, sampling=None, prompt_id="environment_response_v18",
        validation_profile="full", horizon_mode="natural_max_20",
    ):
        validate_generation_options(validation_profile, horizon_mode)
        self.provider = provider
        self.sampling = dict(sampling or {})
        self.prompt_id = prompt_id
        self.validation_profile = validation_profile
        self.horizon_mode = horizon_mode

    @property
    def provenance(self):
        return {
            **getattr(self.provider, "provenance", {}),
            "prompt_id": self.prompt_id,
            "sampling": dict(self.sampling),
            "validation_profile": self.validation_profile,
            "horizon_mode": self.horizon_mode,
        }

    def generate(self, context):
        prior_responses, response_messages = self._build_request(context)
        if self.prompt_id in _STRUCTURED_RESPONSE_PROMPTS:
            retry_diagnostics = []
            result = complete_json(
                self.provider,
                response_messages,
                self.sampling,
                lambda value: self._validate_structured_response(value, context),
                context="structured environment response",
                max_attempts=4,
                retry_guidance=self._structured_retry_guidance(context),
                diagnostics_sink=retry_diagnostics,
            )
            result["request_retry_diagnostics"] = retry_diagnostics
            return result
        forbidden_echoes = prior_responses + [context.get("action", {}).get("text", "")]
        response = complete_environment_response(
            self.provider,
            response_messages,
            self.sampling,
            forbidden_echoes,
            max_attempts=4 if self.validation_profile == "hard_only" else 12,
            validator=lambda candidate: self._validate_candidate_for_profile(
                strip_outer_dialogue_quotes(candidate)
                if self.validation_profile == "hard_only" else candidate,
                context,
            ),
            retry_guidance=(
                self._retry_guidance(context)
                if self.validation_profile == "full" else ""
            ),
            enforce_repetition=self.validation_profile == "full",
            candidate_transform=(
                strip_outer_dialogue_quotes
                if self.validation_profile == "hard_only" else None
            ),
        )
        return (
            strip_outer_dialogue_quotes(response)
            if self.validation_profile == "hard_only" else response
        )

    def _build_request(self, context):
        prior_responses = [
            item.get("text", "")
            for item in context.get("history", [])
            if item.get("role") == "environment_agent"
        ]
        payload = dict(context)
        payload["anti_repetition"] = {
            "current_turn": len(prior_responses) + 1,
            "own_prior_utterances": prior_responses,
            "latest_other_utterance": context.get("action", {}).get("text", ""),
            "instruction": "address the newest request; do not restate an established move",
        }
        scenario = context.get("scenario", {})
        environment_agent = scenario.get("environment_agent", {})
        environment_persona = environment_agent.get("persona", environment_agent)
        evaluated_role = scenario.get("evaluated_agent_role", {})
        payload["role_lock"] = {
            "you_are": {
                "name": environment_persona.get("name", "environment participant"),
                "role": environment_persona.get("role", "environment participant"),
                "speaker_id": "environment_agent",
            },
            "other_speaker": {
                "name": evaluated_role.get("name", "evaluated participant"),
                "role": evaluated_role.get("role", "evaluated participant"),
                "speaker_id": "evaluated_agent",
            },
            "latest_action_owner": "evaluated_agent",
            "ownership_rule": (
                "Respond to the other speaker's action; never take it over as your own."
            ),
            "fact_rule": (
                "Infer no responsibility, right, completed action, or external "
                "event beyond the public role, background, and observable history."
            ),
        }

        turn_number = int(context.get("turn_id", 0))
        longitudinal = context.get("longitudinal_context", {})
        segment = longitudinal.get("segment", {})
        segment_turn = int(segment.get("segment_turn_id", 0))
        payload["horizon_guidance"] = horizon_guidance(
            self.horizon_mode,
            turn_number,
            segment_turn,
            fragment_reference="the public time/event record",
            history_scope="commitments and the complete earlier history",
        )
        if self.validation_profile == "hard_only":
            apply_hard_only_prompt_profile(payload, "interaction_ledger")
        brief_ledger = context.get("interaction_ledger", {})
        latest_obligation = brief_ledger.get("latest_obligation") or {}
        guide = segment.get("turn_guidance", {})
        current_appraisal_events = context.get("appraisal", {}).get("ledger_events", [])
        requested_actions_owned_by_you = [
            event.get("evidence_span", "") for event in current_appraisal_events
            if event.get("event_type") == "request"
            and event.get("action_owner") == "environment_agent"
        ]
        other_speaker_self_owned_moves = [
            event.get("evidence_span", "") for event in current_appraisal_events
            if event.get("event_type") in {"proposal", "commitment", "payment"}
            and event.get("action_owner") == "evaluated_agent"
        ]
        turn_brief = {
            "total_turn": turn_number,
            "segment_turn": segment_turn + 1,
            "must_answer_now": latest_obligation.get("owner") == "environment_agent",
            "newest_other_utterance": context.get("action", {}).get("text", ""),
            "requested_actions_owned_by_you": requested_actions_owned_by_you,
            "other_speaker_self_owned_moves_do_not_take_over": (
                other_speaker_self_owned_moves
            ),
            "suggested_live_question": guide.get("suggested_live_question", ""),
            "guidance_mode": guide.get("mode", ""),
            "do_not_repeat_own_utterances": prior_responses[-3:],
            "final_turn": turn_number == 20,
        }
        prompt = render_prompt(
            self.prompt_id, payload, turn_brief_json=turn_brief
        )
        system_prompt = (
            f"你只能扮演 environment_agent：{environment_persona.get('name', '环境参与者')}（"
            f"{environment_persona.get('role', '环境参与者')}）。对方是 evaluated_agent："
            f"{evaluated_role.get('name', '被评估参与者')}（{evaluated_role.get('role', '被评估参与者')}）。"
            "只写 environment_agent 的回应。最新 action 中的‘我’只指对方，绝不能被"
            "改写成你的行动、承诺、完成或立场。先形成你自己的态度，再回应；不要复述"
            "对方整句，也不要用‘我理解/我接受，但还需要明确’作为默认句式。严格输出所需 JSON。"
        )
        response_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return prior_responses, response_messages

    def _validate_structured_response(self, value, context):
        return response_validation.validate_structured_response(self, value, context)

    def _validate_candidate_for_profile(self, candidate, context):
        return response_validation.validate_candidate_for_profile(
            self, candidate, context
        )

    @staticmethod
    def _answers_current_owned_action_request(candidate, context):
        return response_validation.answers_current_owned_action_request(
            candidate, context
        )

    @staticmethod
    def _structured_retry_guidance(context):
        return response_validation.structured_retry_guidance(context)

    @staticmethod
    def _retry_guidance(context):
        return response_validation.retry_guidance(context)

    @staticmethod
    def _validate_candidate(candidate, context, enforce_fixed_horizon=True):
        return response_validation.validate_candidate(
            candidate,
            context,
            enforce_fixed_horizon=enforce_fixed_horizon,
        )
