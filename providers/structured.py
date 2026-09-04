"""Bounded retries for schema-constrained model output."""

import json


def complete_json(provider, messages, sampling, validator, *, context, max_attempts=3):
    """Retry malformed JSON/schema output without changing the fixed prompt."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    last_error = None
    for _ in range(max_attempts):
        raw = provider.complete(messages, **sampling)
        try:
            value = json.loads(raw)
            return validator(value)
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError, KeyError) as exc:
            last_error = exc
    raise ValueError(
        f"{context} failed JSON/schema validation after {max_attempts} attempts"
    ) from last_error
