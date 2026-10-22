import json
import unittest
from unittest.mock import patch

from providers.anthropic import AnthropicProvider, ProviderHTTPError
from rollout.runner import _provider_request_count


class FakeResponse:
    def __init__(self, text="ok"):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({
            "content": [{"type": "text", "text": self.text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 12, "output_tokens": 3},
        }).encode("utf-8")


class AnthropicProviderTest(unittest.TestCase):
    @patch("providers.anthropic.build_opener")
    def test_bearer_auth_system_projection_seed_and_usage(self, mocked):
        mocked.return_value.open.return_value = FakeResponse()
        provider = AnthropicProvider(
            "https://example.invalid/v1/messages",
            "claude-fable-5",
            "private-token",
            use_proxy=False,
            auth_scheme="bearer",
            max_tokens=80,
        )
        messages = [
            {"role": "system", "content": "system rule"},
            {"role": "user", "content": "request"},
        ]
        self.assertEqual(
            provider.complete(messages, temperature=0.2, seed=7), "ok"
        )
        provider.complete(messages, temperature=0.2, seed=7)
        calls = mocked.return_value.open.call_args_list
        payloads = [json.loads(call.args[0].data) for call in calls]
        self.assertEqual([item["seed"] for item in payloads], [7, 8])
        self.assertEqual(payloads[0]["system"], "system rule")
        self.assertEqual(payloads[0]["messages"], [
            {"role": "user", "content": "request"},
        ])
        self.assertEqual(payloads[0]["max_tokens"], 80)
        self.assertEqual(calls[0].args[0].get_header("Authorization"), "Bearer private-token")
        self.assertEqual(
            provider.usage, {"input_tokens": 24, "output_tokens": 6}
        )
        self.assertEqual(provider.metrics["request_count"], 2)
        self.assertEqual(provider.metrics["failed_request_count"], 0)
        self.assertGreaterEqual(provider.metrics["request_duration_seconds"], 0)
        self.assertEqual(provider.metrics["stop_reasons"], {"end_turn": 2})
        self.assertEqual(provider.metrics["usage"], provider.usage)
        provider.reset()
        self.assertEqual(provider.usage, {})
        self.assertEqual(provider.metrics["request_count"], 0)
        self.assertEqual(provider.metrics["stop_reasons"], {})
        provider.complete(messages, seed=7)
        payload = json.loads(mocked.return_value.open.call_args_list[-1].args[0].data)
        self.assertEqual(payload["seed"], 7)

    def test_streaming_is_never_silently_ignored(self):
        provider = AnthropicProvider(
            "https://example.invalid/v1/messages", "model", "token"
        )
        with self.assertRaisesRegex(ValueError, "streaming"):
            provider.complete(
                [{"role": "user", "content": "request"}], stream=True
            )

    @patch("providers.anthropic.sleep")
    def test_transient_http_failure_retries_and_counts_actual_requests(self, mocked_sleep):
        provider = AnthropicProvider(
            "https://example.invalid/v1/messages", "model", "token",
            max_transport_attempts=3, retry_backoff_seconds=0.25,
        )
        provider._open = unittest.mock.Mock(side_effect=[
            ProviderHTTPError(429, "overloaded"), FakeResponse("recovered"),
        ])
        result = provider.complete(
            [{"role": "user", "content": "request"}], seed=4
        )
        self.assertEqual(result, "recovered")
        self.assertEqual(provider.metrics["request_count"], 2)
        self.assertEqual(provider.metrics["failed_request_count"], 1)
        self.assertEqual(_provider_request_count(provider), 2)
        mocked_sleep.assert_called_once_with(0.25)

    @patch("providers.anthropic.sleep")
    def test_nontransient_http_failure_is_not_retried(self, mocked_sleep):
        provider = AnthropicProvider(
            "https://example.invalid/v1/messages", "model", "token",
            max_transport_attempts=3,
        )
        provider._open = unittest.mock.Mock(
            side_effect=ProviderHTTPError(400, "invalid request")
        )
        with self.assertRaisesRegex(ProviderHTTPError, "400"):
            provider.complete([{"role": "user", "content": "request"}])
        self.assertEqual(provider.metrics["request_count"], 1)
        self.assertEqual(provider.metrics["failed_request_count"], 1)
        mocked_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
