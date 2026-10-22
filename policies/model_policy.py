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


def _text_items(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result

_POLICY_OBSERVATION_CONDITIONS = {"text_only", "text_video"}
_MEDIA_INPUT_FORMATS = {"openai_video_url"}


def _media_content_blocks(media, media_input_format):
    if not media:
        return []
    if media_input_format not in _MEDIA_INPUT_FORMATS:
        raise ValueError(
            "text_video policy requires a supported media_input_format"
        )
    blocks = []
    for item in media:
        if not isinstance(item, dict) or item.get("media_type") != "video":
            raise ValueError("text_video policy accepts video media records only")
        asset_url = str(item.get("asset_url") or "").strip()
        if not asset_url:
            raise ValueError(
                "text_video policy requires a resolved asset_url for every event"
            )
        blocks.append({
            "type": "video_url",
            "video_url": {"url": asset_url},
        })
    return blocks


def _sanitized_policy_payload(observation):
    payload = dict(observation)
    media = payload.pop("media", [])
    payload.pop("observable_cues", None)
    payload.pop("observable_expression", None)
    return payload, media


def build_evaluated_role_card(observation):
    """Build the policy's own-role card only from supplied, policy-visible data."""
    role = observation.get("role", {})
    target = observation.get("target_character", {})
    situation = observation.get("public_situation", {})
    persona = role.get("persona", {})
    if not isinstance(persona, dict):
        persona = {}
    known = _text_items(role.get("known_experiences"))
    if not known:
        known = _text_items(situation.get("relevant_history"))[-4:]
    preferences = []
    for key in ("preferences", "boundaries", "authority_limits"):
        preferences.extend(_text_items(role.get(key)))
    personality = []
    for key in (
        "personality_traits", "communication_tendencies",
        "expression_tendencies",
    ):
        personality.extend(_text_items(role.get(key)))
    return {
        "identity_and_relationship": {
            "self": {"name": role.get("name", ""), "role": role.get("role", "")},
            "counterpart": {
                "name": target.get("name", ""), "role": target.get("role", ""),
            },
            "relationship": situation.get("relationship_structure", ""),
            "power_and_cooperation": situation.get("power_structure", ""),
        },
        "known_experiences": known,
        "current_task_goal": role.get(
            "explicit_goal", observation.get("explicit_goal", "")
        ),
        "private_context": _text_items(role.get("private_context")),
        "preferences_and_boundaries": list(dict.fromkeys(preferences)),
        "personality_and_expression": list(dict.fromkeys(personality)),
        "self_persona": {
            "name": persona.get("name", role.get("name", "")),
            "role": persona.get("role", role.get("role", "")),
            "core_values": _text_items(persona.get("core_values")),
            "temperament": _text_items(persona.get("temperament")),
            "communication_style": persona.get("communication_style", ""),
            "decision_style": persona.get("decision_style", ""),
            "conflict_style": persona.get("conflict_style", ""),
            "boundaries": _text_items(persona.get("boundaries")),
        },
        "missing_information_rule": (
            "Empty sections were not supplied to the evaluated model; do not invent them."
        ),
    }


class ModelPolicy:
    def __init__(
        self,
        policy_id,
        provider,
        prompt_id="task_t4_action_v21",
        sampling=None,
        provenance_extra=None,
        validation_profile="full",
        horizon_mode="natural_max_20",
        minimum_natural_turns=1,
        observation_condition="text_only",
        media_input_format=None,
    ):
        validate_generation_options(validation_profile, horizon_mode)
        if observation_condition not in _POLICY_OBSERVATION_CONDITIONS:
            raise ValueError("unsupported policy observation condition")
        if (
            observation_condition == "text_video"
            and media_input_format not in _MEDIA_INPUT_FORMATS
        ):
            raise ValueError("text_video policy requires media_input_format")
        self.policy_id = policy_id
        self.provider = provider
        self.prompt_id = prompt_id
        self.sampling = dict(sampling or {})
        self.provenance_extra = dict(provenance_extra or {})
        self.validation_profile = validation_profile
        self.horizon_mode = horizon_mode
        self.minimum_natural_turns = int(minimum_natural_turns)
        self.observation_condition = observation_condition
        self.media_input_format = media_input_format

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
            "minimum_natural_turns": self.minimum_natural_turns,
            "observation_condition": self.observation_condition,
            "media_input_format": self.media_input_format,
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
        payload, media = _sanitized_policy_payload(observation)
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
            minimum_natural_turns=self.minimum_natural_turns,
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
        active_pending_commitments = [
            {
                "speaker": item.get("speaker", ""),
                "text": item.get("text", ""),
                "status": item.get("status", ""),
                "turn_id": item.get("turn_id", ""),
            }
            for item in brief_ledger.get("commitments", [])
            if item.get("status") == "pending"
        ]
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
            "decision_continuity": {
                "active_pending_commitments": active_pending_commitments,
                "instruction": (
                    "Before proposing a different plan on the same decision object, "
                    "explicitly preserve the earlier decision, distinguish its stage, "
                    "add a grounded condition, or amend/rescind it with a public reason. "
                    "Never silently replace it."
                ),
            },
            "suggested_live_question": guide.get("suggested_live_question", ""),
            "guidance_mode": guide.get("mode", ""),
            "do_not_repeat_own_utterances": prior_actions[-3:],
            "final_turn": turn_number == 20,
        }
        if runtime_feedback:
            turn_brief["runtime_generation_feedback"] = runtime_feedback
        if self.prompt_id == "task_t4_action_v21":
            turn_brief["semantic_aid_provenance"] = {
                "included_in_primary_t4": True,
                "fields": ["must_answer_now", "latest_open_proposal"],
                "source": (
                    "quote-grounded semantic annotations of observable dialogue "
                    "plus the deterministic public interaction ledger"
                ),
                "excluded": [
                    "private_state", "hidden_intention", "future_outcome",
                ],
            }
        prompt = render_prompt(
            self.prompt_id, payload,
            role_card_json=build_evaluated_role_card(observation),
            turn_brief_json=turn_brief,
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
        media_blocks = self._observation_media_blocks(media)
        user_content = prompt
        if media_blocks:
            user_content = [{"type": "text", "text": prompt}, *media_blocks]
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        return messages, forbidden_echoes

    def _observation_media_blocks(self, media):
        return (_media_content_blocks(media, self.media_input_format)
                if self.observation_condition == "text_video" else [])

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
