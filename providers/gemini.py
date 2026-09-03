"""Minimal Gemini generateContent provider."""

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .base import ModelProvider


class GeminiProvider(ModelProvider):
    def __init__(self, endpoint, model, api_key, timeout=60, **generation_defaults):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.generation_defaults = generation_defaults

    def complete(self, messages, **generation):
        text = "\n".join(str(item.get("content", "")) for item in messages)
        url = self.endpoint + "/models/" + self.model + ":generateContent?" + urlencode({
            "key": self.api_key
        })
        options = {**self.generation_defaults, **generation}
        seed = options.pop("seed", None)
        if seed is not None:
            options["seed"] = seed
        payload = json.dumps({
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {key: value for key, value in options.items() if value is not None},
        }).encode("utf-8")
        request = Request(url, data=payload, method="POST", headers={"content-type": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("provider response lacks candidates content text") from exc

    @property
    def provenance(self):
        return {"provider": "gemini", "model": self.model, "endpoint": self.endpoint}
