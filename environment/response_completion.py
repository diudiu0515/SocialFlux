"""Environment-specific response retries without forced consequential novelty."""

from providers.text import (
    follows_dialogue_format,
    normalize_text,
    TextValidationError,
    validation_verdict,
    reused_dialogue_template_signatures,
    template_escape_instructions,
    validation_escape_instructions,
    text_similarity,
)


def complete_environment_response(
    provider,
    messages,
    sampling,
    prior_texts,
    *,
    validator=None,
    max_attempts=12,
    similarity_threshold=0.82,
    retry_guidance="",
    enforce_repetition=True,
    candidate_transform=None,
):
    prior = list(dict.fromkeys(
        str(value).strip() for value in prior_texts if str(value).strip()
    ))
    base_messages = [dict(item) for item in messages]
    retry_messages = base_messages
    last_reason = "unknown validation failure"
    last_templates = []
    diagnostics = []
    for attempt in range(1, max_attempts + 1):
        last_templates = []
        attempt_sampling = dict(sampling)
        if attempt > 1 and isinstance(attempt_sampling.get("temperature"), (int, float)):
            attempt_sampling["temperature"] = max(
                0.7, float(attempt_sampling["temperature"])
            )
            attempt_sampling["top_p"] = max(
                0.9, float(attempt_sampling.get("top_p", 0.9))
            )
        candidate = provider.complete(
            retry_messages, **attempt_sampling
        ).strip()
        if candidate_transform is not None:
            candidate = str(candidate_transform(candidate)).strip()
        closest = max(
            prior,
            key=lambda previous: text_similarity(candidate, previous),
            default="",
        )
        validator_passed = False
        if not follows_dialogue_format(candidate):
            last_reason = "wrong dialogue format"
        else:
            validator_passed, validator_reason = validation_verdict(
                validator, candidate
            )
            if not validator_passed:
                last_reason = (
                    validator_reason
                    or "factual-grounding or speaker-boundary violation"
                )
        if (
            validator_passed
            and enforce_repetition
            and reused_dialogue_template_signatures(candidate, prior)
        ):
            last_templates = reused_dialogue_template_signatures(candidate, prior)
            last_reason = (
                "overused discourse template(s): " + ", ".join(last_templates)
            )
        elif validator_passed and enforce_repetition and any(
            normalize_text(candidate) == normalize_text(previous)
            or text_similarity(candidate, previous) >= similarity_threshold
            for previous in prior
        ):
            last_reason = "semantic repetition"
        elif validator_passed:
            return candidate
        diagnostics.append({
            "attempt": attempt,
            "candidate": candidate,
            "reason": last_reason,
            "closest_prior": closest,
            "similarity_to_closest": text_similarity(candidate, closest) if closest else 0.0,
            "template_signatures": sorted(
                reused_dialogue_template_signatures(candidate, prior)
            ),
        })
        retry_messages = base_messages + [
            {"role": "assistant", "content": candidate},
            {
                "role": "user",
                "content": (
                    f"That draft was rejected for {last_reason}. The closest earlier "
                    f"utterance was {closest!r}. Address the newest request directly by "
                    "answering, clarifying, accepting, reasonably refusing, or deferring "
                    "with a grounded reason. Preserve existing facts and commitments. "
                    "Do not merely rename the same rhetorical frame. When a future "
                    "commitment, request, conditional, confirmation, or artifact-handling "
                    "frame is named above, avoid that construction entirely. Prefer a "
                    "present-tense direct answer, a concise decision, or a natural closure. "
                    "If the matter is already settled, say so briefly and stop; do not "
                    "promise another action just to fill the turn. "
                    f"针对本次命中的具体问题："
                    f"{validation_escape_instructions(last_reason) or template_escape_instructions(last_templates) or '不要改写旧句，改用不同的现实对话动作。'} "
                    "Do not invent a new condition, threat, deadline, institution, or "
                    f"consequence just to be different. {retry_guidance} "
                    "Return only the revised response."
                ),
            },
        ]
    raise TextValidationError(
        f"environment response failed validation after {max_attempts} attempts: {last_reason}",
        diagnostics,
    )
