"""Minimal Anthropic Messages API provider."""

import json
from urllib.request import Request, urlopen
from .base import ModelProvider


class AnthropicProvider(ModelProvider):
    def __init__(self, endpoint, model, api_key, timeout=60):
        self.endpoint, self.model, self.api_key, self.timeout = endpoint, model, api_key, timeout

    def complete(self, messages):
        payload = json.dumps({
            "model": self.model, "max_tokens": 1024,
            "messages": messages,
        }).encode("utf-8")
        request = Request(self.endpoint, data=payload, method="POST", headers={
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        })
        with urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        try:
            return data["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("provider response lacks content[0].text") from exc
