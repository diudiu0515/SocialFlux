"""Dependency-free OpenAI Responses API provider."""

from __future__ import annotations

import json
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from .base import IncompleteModelOutputError, ModelProvider


class OpenAIResponsesProvider(ModelProvider):
    def __init__(
        self,
        endpoint,
        model,
        api_key=None,
        timeout=60,
        use_proxy=True,
        **generation_defaults,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.use_proxy = bool(use_proxy)
        self.generation_defaults = generation_defaults
        self._call_index = 0
        self._request_count = 0
        self._failed_request_count = 0
        self._request_duration_seconds = 0.0
        self._usage = {}
        self._statuses = {}
        self._audit_records = []

    def reset(self):
        self._call_index = 0
        self._request_count = 0
        self._failed_request_count = 0
        self._request_duration_seconds = 0.0
        self._usage = {}
        self._statuses = {}

    def _record_usage(self, value):
        self._audit_records = []
        if not isinstance(value, dict):
            return
        for key, amount in value.items():
            if isinstance(amount, int) and not isinstance(amount, bool):
                self._usage[key] = self._usage.get(key, 0) + amount

    def _record_status(self, value):
        if isinstance(value, str) and value:
            self._statuses[value] = self._statuses.get(value, 0) + 1

    @staticmethod
    def _extract_text(data):
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        parts = []
        for item in data.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for block in item.get("content", []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "output_text" and isinstance(
                    block.get("text"), str
                ):
                    parts.append(block["text"])
                elif block.get("type") == "refusal":
                    refusal = block.get("refusal")
                    if isinstance(refusal, str) and refusal:
                        raise ValueError(f"provider refused request: {refusal}")
        if parts:
            return "".join(parts)
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            content = (choices[0].get("message") or {}).get("content")
            if isinstance(content, str) and content.strip():
                return content
        raise ValueError("Responses API result lacks output text")

    @staticmethod
    def _response_options(options):
        options = dict(options)
        if "max_tokens" in options and "max_output_tokens" not in options:
            options["max_output_tokens"] = options.pop("max_tokens")
        reasoning_effort = options.pop("reasoning_effort", None)
        if reasoning_effort is not None and "reasoning" not in options:
            options["reasoning"] = {"effort": reasoning_effort}
        options.pop("seed", None)
        return options

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
            raise RuntimeError(
                f"provider HTTP {exc.code}: {body or exc.reason}"
            ) from exc

    def complete(self, messages, **generation):
        options = {**self.generation_defaults, **generation}
        if isinstance(options.get("seed"), int):
            options["seed"] += self._call_index
        self._call_index += 1
        options = self._response_options(options)
        stream = bool(options.get("stream"))
        payload = {
            "model": self.model,
            "input": messages,
            **{key: value for key, value in options.items() if value is not None},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        self._request_count += 1
        started = monotonic()
        try:
            with self._open(request) as response:
                if stream:
                    return self._read_stream(response)
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            self._failed_request_count += 1
            raise
        finally:
            self._request_duration_seconds += monotonic() - started
        if data.get("error"):
            raise RuntimeError(f"provider response error: {data['error']}")
        self._record_usage(data.get("usage"))
        status = data.get("status")
        self._record_status(status)
        try:
            raw_output = self._extract_text(data)
        except ValueError:
            if status != "incomplete":
                raise
            raw_output = ""
        incomplete_reason = (data.get("incomplete_details") or {}).get("reason")
        self._audit_records.append({
            "request": payload,
            "raw_output": raw_output,
            "finish_reason": incomplete_reason or status,
            "usage": data.get("usage", {}),
            "complete": status != "incomplete",
        })
        if status == "incomplete":
            self._failed_request_count += 1
            raise IncompleteModelOutputError(
                f"provider response was incomplete: {incomplete_reason or status}",
                finish_reason=incomplete_reason or status,
                raw_output=raw_output,
                request=payload,
            )
        return raw_output
    def _read_stream(self, response):
        parts = []
        final_response = None
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            data = json.loads(payload)
            event_type = data.get("type")
            if event_type == "response.output_text.delta":
                delta = data.get("delta")
                if isinstance(delta, str):
                    parts.append(delta)
            elif event_type in {"response.completed", "response.incomplete"}:
                final_response = data.get("response")
            elif event_type in {"error", "response.failed"}:
                raise RuntimeError(f"provider streaming error: {data}")
        if isinstance(final_response, dict):
            self._record_usage(final_response.get("usage"))
            self._record_status(final_response.get("status"))
            if not parts:
                return self._extract_text(final_response)
        if not parts:
            raise ValueError("Responses API stream lacks output text")
        return "".join(parts)

    @property
    def usage(self):
        return dict(self._usage)

    @property
    def audit_records(self):
        return [dict(item) for item in self._audit_records]

    @property
    def metrics(self):
        return {
            "request_count": self._request_count,
            "failed_request_count": self._failed_request_count,
            "request_duration_seconds": round(
                self._request_duration_seconds, 3
            ),
            "statuses": dict(sorted(self._statuses.items())),
            "usage": self.usage,
        }

    @property
    def provenance(self):
        return {
            "provider": "openai_responses",
            "model": self.model,
            "endpoint": self.endpoint,
        }
