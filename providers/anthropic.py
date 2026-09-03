"""Minimal Anthropic Messages API provider."""

import json
from urllib.request import Request, urlopen

from .base import ModelProvider


class AnthropicProvider(ModelProvider):
    def __init__(self, endpoint, model, api_key, timeout=60, max_tokens=1024, **generation_defaults):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.generation_defaults = generation_defaults

    def complete(self, messages, **generation):
        options = {**self.generation_defaults, **generation}
        options.pop("seed", None)
        payload = json.dumps({
            "model": self.model,
            "max_tokens": options.pop("max_tokens", self.max_tokens),
            "messages": messages,
            **{key: value for key, value in options.items() if value is not None},
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

    @property
    def provenance(self):
        return {"provider": "anthropic", "model": self.model, "endpoint": self.endpoint}
