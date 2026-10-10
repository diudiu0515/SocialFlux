"""Dependency-free Anthropic Messages API provider."""

from __future__ import annotations

import json
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from .base import IncompleteModelOutputError, ModelProvider


class ProviderHTTPError(RuntimeError):
    """HTTP failure with enough structure for bounded transport retries."""

    def __init__(self, status, detail):
        super().__init__(f"provider HTTP {status}: {detail}")
        self.status = int(status)


class AnthropicProvider(ModelProvider):
    def __init__(
        self,
        endpoint,
        model,
        api_key,
        timeout=60,
        max_tokens=1024,
        use_proxy=True,
        auth_scheme="x-api-key",
        anthropic_version="2023-06-01",
        max_transport_attempts=4,
        retry_backoff_seconds=1.5,
        **generation_defaults,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.use_proxy = bool(use_proxy)
        self.auth_scheme = auth_scheme
        self.anthropic_version = anthropic_version
        self.max_transport_attempts = max(1, int(max_transport_attempts))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.generation_defaults = generation_defaults
        self._call_index = 0
        self._request_count = 0
        self._usage = {}
        self._request_duration_seconds = 0.0
        self._failed_request_count = 0
        self._stop_reasons = {}
        self._audit_records = []

    def reset(self):
        self._call_index = 0
        self._request_count = 0
        self._usage = {}
        self._request_duration_seconds = 0.0
        self._failed_request_count = 0
        self._stop_reasons = {}
        self._audit_records = []

    @staticmethod
    def _messages(messages):
        system = []
        conversation = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role == "system":
                if not isinstance(content, str):
                    raise ValueError("Anthropic system content must be text")
                system.append(content)
            elif role in {"user", "assistant"}:
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") not in {"text", "image"}:
                            raise ValueError("Anthropic content must contain text or image blocks")
                        if block["type"] == "text" and not isinstance(block.get("text"), str):
                            raise ValueError("Anthropic text block requires text")
                        if block["type"] == "image":
                            source = block.get("source", {})
                            if source.get("type") != "base64" or source.get("media_type") not in {
                                "image/jpeg", "image/png", "image/gif", "image/webp"
                            } or not isinstance(source.get("data"), str) or not source["data"]:
                                raise ValueError("Anthropic image block requires base64 image data")
                elif not isinstance(content, str):
                    raise ValueError("Anthropic message content must be text or content blocks")
                conversation.append({"role": role, "content": content})
            else:
                raise ValueError(f"unsupported Anthropic message role: {role}")
        if not conversation:
            raise ValueError("Anthropic request requires a user/assistant conversation")
        return "\n\n".join(system), conversation

    def _headers(self):
        headers = {
            "content-type": "application/json",
            "anthropic-version": self.anthropic_version,
        }
        if self.auth_scheme == "bearer":
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.auth_scheme == "x-api-key":
            headers["x-api-key"] = self.api_key
        else:
            raise ValueError(f"unsupported Anthropic auth scheme: {self.auth_scheme}")
        return headers

    def _open(self, request):
        hostname = urlparse(self.endpoint).hostname
        bypass_proxy = (
            not self.use_proxy
            or hostname in {"127.0.0.1", "localhost", "::1"}
        )
        opener = build_opener(ProxyHandler({})) if bypass_proxy else None
        try:
            return (
                opener.open(request, timeout=self.timeout)
                if opener
                else urlopen(request, timeout=self.timeout)
            )
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[-4000:]
            raise ProviderHTTPError(exc.code, body or exc.reason) from exc

    @staticmethod
    def _is_transient(error):
        return (
            isinstance(error, ProviderHTTPError)
            and error.status in {408, 409, 425, 429, 500, 502, 503, 504}
        ) or isinstance(error, (TimeoutError, URLError))

    def _record_usage(self, value):
        if not isinstance(value, dict):
            return
        for key, amount in value.items():
            if isinstance(amount, int) and not isinstance(amount, bool):
                self._usage[key] = self._usage.get(key, 0) + amount

    def complete(self, messages, **generation):
        options = {**self.generation_defaults, **generation}
        if options.get("stream"):
            raise ValueError("AnthropicProvider does not enable streaming")
        options.pop("stream", None)
        if isinstance(options.get("seed"), int):
            options["seed"] += self._call_index
        self._call_index += 1
        system, conversation = self._messages(messages)
        payload = {
            "model": self.model,
            "max_tokens": options.pop("max_tokens", self.max_tokens),
            "messages": conversation,
            **{key: value for key, value in options.items() if value is not None},
        }
        if system:
            payload["system"] = system
        encoded = json.dumps(payload).encode("utf-8")
        data = None
        for attempt in range(1, self.max_transport_attempts + 1):
            request = Request(
                self.endpoint,
                data=encoded,
                method="POST",
                headers=self._headers(),
            )
            self._request_count += 1
            started = monotonic()
            try:
                with self._open(request) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except Exception as exc:
                self._failed_request_count += 1
                if (
                    attempt >= self.max_transport_attempts
                    or not self._is_transient(exc)
                ):
                    raise
                sleep(self.retry_backoff_seconds * (2 ** (attempt - 1)))
            finally:
                self._request_duration_seconds += monotonic() - started
        self._record_usage(data.get("usage"))
        stop_reason = data.get("stop_reason")
        if isinstance(stop_reason, str) and stop_reason:
            self._stop_reasons[stop_reason] = (
                self._stop_reasons.get(stop_reason, 0) + 1
            )
        parts = [
            block["text"]
            for block in data.get("content", [])
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        if not parts:
            raise ValueError("provider response lacks a text content block")
        raw_output = "".join(parts)
        self._audit_records.append({
            "request": payload,
            "raw_output": raw_output,
            "finish_reason": stop_reason,
            "usage": data.get("usage", {}),
            "complete": stop_reason != "max_tokens",
        })
        if stop_reason == "max_tokens":
            self._failed_request_count += 1
            raise IncompleteModelOutputError(
                "provider response was truncated at max_tokens",
                finish_reason=stop_reason,
                raw_output=raw_output,
                request=payload,
            )
        return raw_output

    @property
    def audit_records(self):
        return [dict(item) for item in self._audit_records]

    @property
    def usage(self):
        return dict(self._usage)

    @property
    def metrics(self):
        return {
            "request_count": self._request_count,
            "failed_request_count": self._failed_request_count,
            "request_duration_seconds": round(
                self._request_duration_seconds, 3
            ),
            "stop_reasons": dict(sorted(self._stop_reasons.items())),
            "usage": self.usage,
        }

    @property
    def provenance(self):
        return {
            "provider": "anthropic",
            "model": self.model,
            "endpoint": self.endpoint,
            "auth_scheme": self.auth_scheme,
        }
