import json
import unittest
from unittest.mock import patch

from providers.openai_responses import OpenAIResponsesProvider


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.value).encode("utf-8")


class FakeStreamResponse(FakeResponse):
    def __iter__(self):
        events = [
            {"type": "response.output_text.delta", "delta": "连"},
            {"type": "response.output_text.delta", "delta": "接正常"},
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"input_tokens": 4, "output_tokens": 2},
                },
            },
        ]
        return iter([
            f"data: {json.dumps(event, ensure_ascii=False)}\n".encode("utf-8")
            for event in events
        ] + [b"data: [DONE]\n"])


class OpenAIResponsesProviderTest(unittest.TestCase):
    @patch("providers.openai_responses.build_opener")
    def test_translates_chat_options_and_extracts_output(self, mocked):
        mocked.return_value.open.return_value = FakeResponse({
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "ok"}],
            }],
            "usage": {"input_tokens": 8, "output_tokens": 3},
        })
        provider = OpenAIResponsesProvider(
            "https://example.invalid/v1/responses",
            "gpt-test",
            api_key="secret",
            use_proxy=False,
        )
        result = provider.complete(
            [{"role": "user", "content": "test"}],
            max_tokens=120,
            reasoning_effort="low",
            seed=7,
        )
        self.assertEqual(result, "ok")
        request = mocked.return_value.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["max_output_tokens"], 120)
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertNotIn("max_tokens", payload)
        self.assertNotIn("seed", payload)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")

    @patch("providers.openai_responses.build_opener")
    def test_streaming_deltas_are_aggregated(self, mocked):
        mocked.return_value.open.return_value = FakeStreamResponse({})
        provider = OpenAIResponsesProvider(
            "https://example.invalid/v1/responses",
            "gpt-test",
            use_proxy=False,
            stream=True,
        )
        result = provider.complete([{"role": "user", "content": "test"}])
        self.assertEqual(result, "连接正常")
        self.assertEqual(provider.metrics["statuses"], {"completed": 1})
        self.assertEqual(
            provider.metrics["usage"],
            {"input_tokens": 4, "output_tokens": 2},
        )


if __name__ == "__main__":
    unittest.main()
