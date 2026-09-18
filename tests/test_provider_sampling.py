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
        return json.dumps({
            "choices": [{
                "message": {"content": "ok"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        }).encode()


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

    @patch("providers.openai_compatible.build_opener")
    def test_metrics_record_requests_usage_and_finish_reason(self, mocked):
        mocked.return_value.open.return_value = FakeResponse()
        provider = OpenAICompatibleProvider(
            "https://example.invalid/v1/chat/completions",
            "model",
            use_proxy=False,
        )
        provider.complete([{"role": "user", "content": "test"}])
        self.assertEqual(provider.metrics["request_count"], 1)
        self.assertEqual(provider.metrics["failed_request_count"], 0)
        self.assertEqual(provider.metrics["usage"], {
            "prompt_tokens": 12,
            "completion_tokens": 3,
        })
        self.assertEqual(provider.metrics["finish_reasons"], {"stop": 1})
        self.assertGreaterEqual(provider.metrics["request_duration_seconds"], 0)

    @patch("providers.openai_compatible.build_opener")
    def test_metrics_record_failed_request_and_reset(self, mocked):
        mocked.return_value.open.side_effect = TimeoutError("timed out")
        provider = OpenAICompatibleProvider(
            "https://example.invalid/v1/chat/completions",
            "model",
            use_proxy=False,
        )
        with self.assertRaises(TimeoutError):
            provider.complete([{"role": "user", "content": "test"}])
        self.assertEqual(provider.metrics["request_count"], 1)
        self.assertEqual(provider.metrics["failed_request_count"], 1)
        provider.reset()
        self.assertEqual(provider.metrics["request_count"], 0)
        self.assertEqual(provider.metrics["failed_request_count"], 0)


if __name__ == "__main__":
    unittest.main()
