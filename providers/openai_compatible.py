"""Dependency-free OpenAI-compatible chat-completions provider."""

import json
from urllib.request import Request, urlopen

from .base import ModelProvider


class OpenAICompatibleProvider(ModelProvider):
    def __init__(self, endpoint, model, api_key=None, timeout=60, **generation_defaults):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.generation_defaults = generation_defaults

    def complete(self, messages, **generation):
        options = {**self.generation_defaults, **generation}
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            **{key: value for key, value in options.items() if value is not None},
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(self.endpoint, data=payload, headers=headers, method="POST")
        with urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("provider response lacks choices[0].message.content") from exc

    @property
    def provenance(self):
        return {
            "provider": "openai_compatible",
            "model": self.model,
            "endpoint": self.endpoint,
        }
