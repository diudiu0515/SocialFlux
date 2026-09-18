"""Free-form model policy for both rollout generation and online T4."""


from environment.dialogue_support import (
    apply_hard_only_prompt_profile,
    horizon_guidance,
    validate_generation_options,
)
from . import action_validation
from prompts.loader import render_prompt
from providers.text import (
    complete_distinct_text,
    strip_outer_dialogue_quotes,
)


class ModelPolicy:
    def __init__(
        self,
        policy_id,
        provider,
        prompt_id="task_t4_action_v17",
        sampling=None,
        provenance_extra=None,
        validation_profile="full",
        horizon_mode="natural_max_20",
    ):
        validate_generation_options(validation_profile, horizon_mode)
        self.policy_id = policy_id
        self.provider = provider
        self.prompt_id = prompt_id
        self.sampling = dict(sampling or {})
        self.provenance_extra = dict(provenance_extra or {})
        self.validation_profile = validation_profile
        self.horizon_mode = horizon_mode

    def reset(self):
        reset = getattr(self.provider, "reset", None)
        if reset:
            reset()

    @property
    def provenance(self):
        return {
            "policy_id": self.policy_id,
            **getattr(self.provider, "provenance", {}),
            "prompt_id": self.prompt_id,
            "sampling": dict(self.sampling),
            "validation_profile": self.validation_profile,
            "horizon_mode": self.horizon_mode,
            **self.provenance_extra,
        }

    def generate(self, observation):
        messages, forbidden_echoes = self._build_request(observation)
        text = complete_distinct_text(
            self.provider,
            messages,
            self.sampling,
            forbidden_echoes,
            context="model policy action",
            max_attempts=4 if self.validation_profile == "hard_only" else 12,
            similarity_threshold=0.72,
            validator=lambda candidate: self._validate_candidate_for_profile(
                strip_outer_dialogue_quotes(candidate)
                if self.validation_profile == "hard_only" else candidate,
                observation,
            ),
            retry_guidance=self._retry_guidance(observation),
            enforce_repetition=self.validation_profile == "full",
            candidate_transform=(
                strip_outer_dialogue_quotes
                if self.validation_profile == "hard_only" else None
            ),
        )
        if self.validation_profile == "hard_only":
            text = strip_outer_dialogue_quotes(text)
        return {"text": text}


    def _build_request(self, observation):
        prior_actions = [
            item.get("text", "")
            for item in observation.get("history", [])
            if item.get("role") == "evaluated_agent"
        ]
        observed_responses = [
            item.get("text", "")
            for item in observation.get("history", [])
            if item.get("role") == "environment_agent"
        ]
        turn_number = len(prior_actions) + 1
        payload = dict(observation)
        runtime_feedback = payload.pop("runtime_generation_feedback", None)
        payload["anti_repetition"] = {
            "current_turn": turn_number,
            "own_prior_utterances": prior_actions,
            "latest_other_utterance": (
                observation.get("current_response") or
                (observed_responses[-1] if observed_responses else "")
            ),
            "instruction": (
                "respond to the latest turn without reopening a resolved object or "
                "inventing another artifact, condition, or consequence to fill time"
            ),
        }
        role = observation.get("role", {})
        target = observation.get("target_character", {})
        payload["role_lock"] = {
            "you_are": {
                "name": role.get("name", "evaluated participant"),
                "role": role.get("role", "evaluated participant"),
                "goal": role.get("explicit_goal", observation.get("explicit_goal", "")),
                "speaker_id": "evaluated_agent",
            },
            "other_speaker": {
                "name": target.get("name", "environment participant"),
                "role": target.get("role", "environment participant"),
                "speaker_id": "environment_agent",
            },
            "ownership_rule": (
                "Never perform or report completion of an action owned by the other speaker."
            ),
            "fact_rule": (
                "Infer no responsibility, right, completed action, or external "
                "event beyond the public role, background, and observable history."
            ),
        }

        longitudinal = observation.get("longitudinal_context", {})
        segment = longitudinal.get("segment", {})
        segment_turn = int(segment.get("segment_turn_id", 0))
        payload["horizon_guidance"] = horizon_guidance(
            self.horizon_mode,
            turn_number,
            segment_turn,
            fragment_reference="its public time/event record and opening",
            history_scope="the complete earlier history",
        )
        if self.validation_profile == "hard_only":
            apply_hard_only_prompt_profile(payload, "conversation_progress")
        brief_ledger = observation.get("conversation_progress", {})
        latest_obligation = brief_ledger.get("latest_obligation") or {}
        latest_open_proposal = next((
            item for item in reversed(brief_ledger.get("active_proposals", []))
            if item.get("speaker") == "environment_agent"
            and item.get("status") in {"open", "tentative"}
        ), None)
        guide = segment.get("turn_guidance", {})
        turn_brief = {
            "total_turn": turn_number,
            "segment_turn": segment_turn + 1,
            "must_answer_now": latest_obligation.get("owner") == "evaluated_agent",
            "answer_obligation_instruction": (
                "Answer the substance naturally: accept, refuse, counter, clarify, or "
                "say what cannot be confirmed. Do not bounce the same decision back."
                if latest_obligation.get("owner") == "evaluated_agent"
                and not latest_open_proposal else ""
            ),
            "latest_open_proposal": (
                {
                    "text": latest_open_proposal.get("text", ""),
                    "status": latest_open_proposal.get("status", "open"),
                } if latest_open_proposal else None
            ),
            "newest_other_utterance": observation.get("current_response", ""),
            "suggested_live_question": guide.get("suggested_live_question", ""),
            "guidance_mode": guide.get("mode", ""),
            "do_not_repeat_own_utterances": prior_actions[-3:],
            "final_turn": turn_number == 20,
        }
        if runtime_feedback:
            turn_brief["runtime_generation_feedback"] = runtime_feedback
        prompt = render_prompt(
            self.prompt_id, payload, turn_brief_json=turn_brief
        )
        forbidden_echoes = (
            prior_actions
            + observed_responses[-1:]
            + [observation.get("current_response", "")]
        )
        system_prompt = (
            f"你只能扮演 evaluated_agent：{role.get('name', '被评估参与者')}（"
            f"{role.get('role', '被评估参与者')}）。对方是 environment_agent："
            f"{target.get('name', '环境参与者')}（{target.get('role', '环境参与者')}）。"
            "只写 evaluated_agent 的下一句直接台词。对方台词中的‘我’只指对方，"
            "绝不能被改写成你的行动、承诺、完成或立场。不要复述对方整句，也不要用"
            "‘我理解/我接受，但还需要明确’作为默认句式；直接作出这一个角色此刻最自然的反应。"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return messages, forbidden_echoes

    def _validate_candidate_for_profile(self, candidate, observation):
        return action_validation.validate_candidate_for_profile(
            self, candidate, observation
        )

    def _retry_guidance(self, observation):
        return action_validation.retry_guidance(self, observation)

    @staticmethod
    def _validate_candidate(candidate, observation, enforce_fixed_horizon=True):
        return action_validation.validate_candidate(
            candidate,
            observation,
            enforce_fixed_horizon=enforce_fixed_horizon,
        )
