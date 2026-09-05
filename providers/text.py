"""Quality-gated retries for free-form model text."""

import re
import unicodedata


def normalize_text(value):
    return "".join(
        character
        for character in str(value)
        if not character.isspace()
        and not unicodedata.category(character).startswith("P")
    )


def _bigrams(value):
    normalized = normalize_text(value)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index:index + 2] for index in range(len(normalized) - 1)}


def text_similarity(left, right):
    left_grams = _bigrams(left)
    right_grams = _bigrams(right)
    union = left_grams | right_grams
    return len(left_grams & right_grams) / len(union) if union else 1.0


def follows_dialogue_format(value):
    """Reject screenplay directions and explicit speaker labels."""
    text = str(value).strip()
    has_stage_direction = re.search(r"[（(][^）)]{2,}[）)]", text) is not None
    has_speaker_label = re.match(r"^[\w\u4e00-\u9fff·]{1,12}[：:]", text) is not None
    return bool(text) and not has_stage_direction and not has_speaker_label


def complete_distinct_text(
    provider,
    messages,
    sampling,
    prior_texts,
    *,
    context,
    max_attempts=5,
    similarity_threshold=0.92,
):
    """Retry with provider-side seed progression until text is genuinely new."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    prior = [str(value).strip() for value in prior_texts if str(value).strip()]
    for _ in range(max_attempts):
        candidate = provider.complete(messages, **sampling).strip()
        if not follows_dialogue_format(candidate):
            continue
        if all(
            normalize_text(candidate) != normalize_text(previous)
            and text_similarity(candidate, previous) < similarity_threshold
            for previous in prior
        ):
            return candidate
    raise ValueError(
        f"{context} failed distinct-text validation after {max_attempts} attempts"
    )
