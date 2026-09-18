"""Bounded retries for schema-constrained model output."""

import json


class StructuredOutputError(ValueError):
    """Expose bounded failure evidence without silently accepting malformed JSON."""

    def __init__(
        self, message, *, last_raw=None, last_error=None, diagnostics=None
    ):
        super().__init__(message)
        self.last_raw = last_raw
        self.last_error = last_error
        self.diagnostics = list(diagnostics or [])


def _decode_one(text):
    decoder = json.JSONDecoder()
    value, end = decoder.raw_decode(text)
    trailing = text[end:].strip()
    if trailing and any(character not in "]}" for character in trailing):
        raise json.JSONDecodeError(
            "unexpected trailing content after JSON value", text, end
        )
    return value


def _parse_json_output(raw):
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        opening = lines[0].strip().lower()
        if opening in {"```", "```json"} and len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    try:
        return _decode_one(text)
    except json.JSONDecodeError as original_error:
        # Some local chat models stop after closing the inner object. Repair only
        # an end-of-string delimiter error; never alter interior JSON content.
        if original_error.pos < len(text) - 1:
            raise
        for suffix in ("}", "}}"):
            try:
                return _decode_one(text + suffix)
            except json.JSONDecodeError:
                continue
        raise original_error


def complete_json(
    provider, messages, sampling, validator, *, context, max_attempts=3,
    retry_guidance="", diagnostics_sink=None,
):
    """Retry malformed JSON/schema output without changing the fixed prompt."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    last_error = None
    last_raw = None
    base_messages = [dict(item) for item in messages]
    retry_messages = base_messages
    diagnostics = []
    for attempt in range(1, max_attempts + 1):
        attempt_sampling = dict(sampling)
        if attempt > 1 and isinstance(
            attempt_sampling.get("temperature"), (int, float)
        ):
            attempt_sampling["temperature"] = max(
                0.7, float(attempt_sampling["temperature"])
            )
            attempt_sampling["top_p"] = max(
                0.9, float(attempt_sampling.get("top_p", 0.9))
            )
        last_raw = provider.complete(retry_messages, **attempt_sampling)
        try:
            value = _parse_json_output(last_raw)
            result = validator(value)
            if diagnostics_sink is not None:
                diagnostics_sink.extend(diagnostics)
            return result
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError, KeyError) as exc:
            last_error = exc
            diagnostics.append({
                "attempt": attempt, "raw": last_raw, "reason": str(exc)
            })
            retry_messages = base_messages + [
                {"role": "assistant", "content": last_raw},
                {
                    "role": "user",
                    "content": (
                        "Runtime schema validation rejected that JSON: "
                        f"{exc}. Return a corrected JSON object only, using "
                        "exactly the required keys and no extra fields. "
                        f"This is revision attempt {attempt + 1}; do not "
                        "repeat the rejected content unchanged. "
                        f"{retry_guidance}"
                    ),
                },
            ]
    raise StructuredOutputError(
        f"{context} failed JSON/schema validation after {max_attempts} attempts",
        last_raw=last_raw,
        last_error=last_error,
        diagnostics=diagnostics,
    ) from last_error
