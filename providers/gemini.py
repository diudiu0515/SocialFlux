"""Minimal Gemini generateContent provider."""

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .base import ModelProvider


class GeminiProvider(ModelProvider):
    def __init__(self, endpoint, model, api_key, timeout=60):
        self.endpoint, self.model, self.api_key, self.timeout = endpoint.rstrip("/"), model, api_key, timeout

    def complete(self, messages):
        text = "\n".join(str(item.get("content", "")) for item in messages)
        url = self.endpoint + "/models/" + self.model + ":generateContent?" + urlencode({"key": self.api_key})
        payload = json.dumps({"contents": [{"role": "user", "parts": [{"text": text}]}]}).encode("utf-8")
        request = Request(url, data=payload, method="POST", headers={"content-type": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("provider response lacks candidates content text") from exc
