"""Bounded retries for schema-constrained model output."""

import json


def _parse_json_output(raw):
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        opening = lines[0].strip().lower()
        if opening in {"```", "```json"} and len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    decoder = json.JSONDecoder()
    value, end = decoder.raw_decode(text)
    trailing = text[end:].strip()
    if trailing and any(character not in "]}" for character in trailing):
        raise json.JSONDecodeError(
            "unexpected trailing content after JSON value", text, end
        )
    return value


def complete_json(provider, messages, sampling, validator, *, context, max_attempts=3):
    """Retry malformed JSON/schema output without changing the fixed prompt."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    last_error = None
    for _ in range(max_attempts):
        raw = provider.complete(messages, **sampling)
        try:
            value = _parse_json_output(raw)
            return validator(value)
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError, KeyError) as exc:
            last_error = exc
    raise ValueError(
        f"{context} failed JSON/schema validation after {max_attempts} attempts"
    ) from last_error
