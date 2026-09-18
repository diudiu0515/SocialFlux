"""Dependency-free OpenAI-compatible chat-completions provider."""

import json
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from .base import ModelProvider


class OpenAICompatibleProvider(ModelProvider):
    def __init__(self, endpoint, model, api_key=None, timeout=60, use_proxy=True, **generation_defaults):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.generation_defaults = generation_defaults
        self.use_proxy = bool(use_proxy)
        self._call_index = 0
        self._request_count = 0
        self._failed_request_count = 0
        self._request_duration_seconds = 0.0
        self._usage = {}
        self._finish_reasons = {}

    def reset(self):
        self._call_index = 0
        self._request_count = 0
        self._failed_request_count = 0
        self._request_duration_seconds = 0.0
        self._usage = {}
        self._finish_reasons = {}

    def _record_usage(self, value):
        if not isinstance(value, dict):
            return
        for key, amount in value.items():
            if isinstance(amount, int) and not isinstance(amount, bool):
                self._usage[key] = self._usage.get(key, 0) + amount

    def _record_finish_reason(self, value):
        if isinstance(value, str) and value:
            self._finish_reasons[value] = self._finish_reasons.get(value, 0) + 1

    def complete(self, messages, **generation):
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
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
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
            "usage": self.usage,
        }

    @property
    def provenance(self):
        return {
            "provider": "openai_compatible",
            "model": self.model,
            "endpoint": self.endpoint,
        }
