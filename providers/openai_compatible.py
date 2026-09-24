"""Dependency-free OpenAI-compatible chat-completions provider."""

import json
import os
from threading import Lock
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from .base import ModelProvider


_KEY_POOL_LOCK = Lock()
_KEY_POOL_COUNTER = 0


def _next_key_slot(size):
    global _KEY_POOL_COUNTER
    with _KEY_POOL_LOCK:
        slot = (os.getpid() + _KEY_POOL_COUNTER) % size
        _KEY_POOL_COUNTER += 1
    return slot


class OpenAICompatibleProvider(ModelProvider):
    def __init__(
        self, endpoint, model, api_key=None, api_keys=None, timeout=60,
        use_proxy=True, **generation_defaults,
    ):
        self.api_key = api_key
        self.api_keys = tuple(api_keys or ())
        if self.api_key and self.api_keys:
            raise ValueError("set api_key or api_keys, not both")
        if any(not isinstance(key, str) or not key for key in self.api_keys):
            raise ValueError("api_keys must contain non-empty text")
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.generation_defaults = generation_defaults
        self.use_proxy = bool(use_proxy)
        self._call_index = 0
        self._request_count = 0
        self._failed_request_count = 0
        self._request_duration_seconds = 0.0
        self._usage = {}
        self._finish_reasons = {}
        self._credential_slot_requests = {}

    def reset(self):
        self._call_index = 0
        self._request_count = 0
        self._failed_request_count = 0
        self._request_duration_seconds = 0.0
        self._usage = {}
        self._finish_reasons = {}
        self._credential_slot_requests = {}

    def _authorization_key(self):
        if not self.api_keys:
            return self.api_key
        slot = _next_key_slot(len(self.api_keys))
        self._credential_slot_requests[slot] = (
            self._credential_slot_requests.get(slot, 0) + 1
        )
        return self.api_keys[slot]


    def _record_usage(self, value):
        if not isinstance(value, dict):
            return
        for key, amount in value.items():
            if isinstance(amount, int) and not isinstance(amount, bool):
                self._usage[key] = self._usage.get(key, 0) + amount

    def _record_finish_reason(self, value):
        if isinstance(value, str) and value:
            self._finish_reasons[value] = self._finish_reasons.get(value, 0) + 1

    def _merge_provider_metrics(self, provider):
        self._request_count += provider._request_count
        self._failed_request_count += provider._failed_request_count
        self._request_duration_seconds += provider._request_duration_seconds
        for key, amount in provider._usage.items():
            self._usage[key] = self._usage.get(key, 0) + amount
        for reason, count in provider._finish_reasons.items():
            self._finish_reasons[reason] = self._finish_reasons.get(reason, 0) + count

    def complete(self, messages, **generation):
        if not self.api_keys:
            return self._complete_single(messages, **generation)
        options = {**self.generation_defaults, **generation}
        if isinstance(options.get("seed"), int):
            options["seed"] += self._call_index
        self._call_index += 1
        start = _next_key_slot(len(self.api_keys))
        last_error = None
        for offset in range(len(self.api_keys)):
            slot = (start + offset) % len(self.api_keys)
            key = self.api_keys[slot]
            self._credential_slot_requests[slot] = (
                self._credential_slot_requests.get(slot, 0) + 1
            )
            provider = OpenAICompatibleProvider(
                self.endpoint,
                self.model,
                api_key=key,
                timeout=self.timeout,
                use_proxy=self.use_proxy,
            )
            try:
                content = provider._complete_single(messages, **options)
            except Exception as exc:
                self._merge_provider_metrics(provider)
                last_error = exc
                continue
            self._merge_provider_metrics(provider)
            refused = bool(
                provider._finish_reasons.get("refusal")
            )
            if (
                isinstance(content, str)
                and content.strip()
                and not refused
            ):
                return content
            self._failed_request_count += 1
            last_error = ValueError("provider returned empty or refused content")
        if last_error is not None:
            raise last_error
        raise RuntimeError("provider credential pool is empty")

    def _complete_single(self, messages, **generation):
        options = {**self.generation_defaults, **generation}
        if isinstance(options.get("seed"), int):
            options["seed"] += self._call_index
        self._call_index += 1
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            **{key: value for key, value in options.items() if value is not None},
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        authorization_key = self._authorization_key()
        if authorization_key:
            headers["Authorization"] = f"Bearer {authorization_key}"
        request = Request(self.endpoint, data=payload, headers=headers, method="POST")
        hostname = urlparse(self.endpoint).hostname
        bypass_proxy = not self.use_proxy or hostname in {"127.0.0.1", "localhost", "::1"}
        opener = build_opener(ProxyHandler({})) if bypass_proxy else None
        self._request_count += 1
        started = monotonic()
        try:
            try:
                response_context = (
                    opener.open(request, timeout=self.timeout)
                    if opener
                    else urlopen(request, timeout=self.timeout)
                )
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[-4000:]
                raise RuntimeError(
                    f"provider HTTP {exc.code}: {body or exc.reason}"
                ) from exc
            with response_context as response:
                if options.get("stream"):
                    return self._read_stream(response)
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            self._failed_request_count += 1
            raise
        finally:
            self._request_duration_seconds += monotonic() - started
        self._record_usage(data.get("usage"))
        try:
            choice = data["choices"][0]
            self._record_finish_reason(choice.get("finish_reason"))
            return choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("provider response lacks choices[0].message.content") from exc

    def _read_stream(self, response):
        """Aggregate OpenAI-compatible SSE chunks into one assistant message."""
        parts = []
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            data = json.loads(payload)
            self._record_usage(data.get("usage"))
            for choice in data.get("choices", []):
                self._record_finish_reason(choice.get("finish_reason"))
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance((choice.get("message") or {}).get("content"), str):
                    parts.append(choice["message"]["content"])
        if not parts:
            raise ValueError("streaming provider response lacks assistant content")
        return "".join(parts)

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
            "finish_reasons": dict(sorted(self._finish_reasons.items())),
            "credential_pool_size": len(self.api_keys) or int(bool(self.api_key)),
            "credential_slot_requests": dict(self._credential_slot_requests),
            "usage": self.usage,
        }

    @property
    def provenance(self):
        return {
            "provider": "openai_compatible",
            "model": self.model,
            "endpoint": self.endpoint,
            "credential_pool_size": len(self.api_keys) or int(bool(self.api_key)),
        }
