"""Dependency-free OpenAI-compatible chat-completions provider."""

import json
from urllib.request import Request, urlopen

from .base import ModelProvider


class OpenAICompatibleProvider(ModelProvider):
    def __init__(self, endpoint, model, api_key=None, timeout=60):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, messages):
        payload = json.dumps({"model": self.model, "messages": messages}).encode("utf-8")
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
