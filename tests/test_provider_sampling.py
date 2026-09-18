import json
import unittest
from unittest.mock import patch

from providers.openai_compatible import OpenAICompatibleProvider


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()


class FakeStreamResponse(FakeResponse):
    def __iter__(self):
        chunks = [
            {"choices": [{"delta": {"content": "连"}}]},
            {"choices": [{"delta": {"content": "接正常"}}]},
        ]
        return iter([
            f"data: {json.dumps(item, ensure_ascii=False)}\n".encode()
            for item in chunks
        ] + [b"data: [DONE]\n"])


class ProviderSamplingTest(unittest.TestCase):
    @patch("providers.openai_compatible.build_opener")
    def test_seed_advances_per_call_and_reset_restores_base(self, mocked):
        mocked.return_value.open.return_value = FakeResponse()
        provider = OpenAICompatibleProvider(
            "http://localhost/v1/chat/completions",
            "model",
        )
        messages = [{"role": "user", "content": "test"}]
        provider.complete(messages, temperature=0.6, seed=7)
        provider.complete(messages, temperature=0.6, seed=7)
        provider.reset()
        provider.complete(messages, temperature=0.6, seed=7)
        seeds = [
            json.loads(call.args[0].data)["seed"]
            for call in mocked.return_value.open.call_args_list
        ]
        self.assertEqual(seeds, [7, 8, 7])

    @patch("providers.openai_compatible.build_opener")
    def test_streaming_chunks_are_aggregated(self, mocked):
        mocked.return_value.open.return_value = FakeStreamResponse()
        provider = OpenAICompatibleProvider(
            "https://example.invalid/v1/chat/completions",
            "model",
            use_proxy=False,
            stream=True,
        )
        result = provider.complete([{"role": "user", "content": "test"}])
        self.assertEqual(result, "连接正常")
        payload = json.loads(mocked.return_value.open.call_args.args[0].data)
        self.assertIs(payload["stream"], True)


if __name__ == "__main__":
    unittest.main()
