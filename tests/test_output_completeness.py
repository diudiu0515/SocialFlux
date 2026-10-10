import json
import unittest
from unittest.mock import patch

from providers.anthropic import AnthropicProvider
from providers.base import IncompleteModelOutputError
from providers.openai_compatible import OpenAICompatibleProvider


class JSONResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class OutputCompletenessTest(unittest.TestCase):
    @patch("providers.anthropic.build_opener")
    def test_anthropic_max_tokens_is_failure_with_raw_audit(self, opener):
        opener.return_value.open.return_value = JSONResponse({
            "content": [{"type": "text", "text": '{"partial": true}'}],
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        })
        provider = AnthropicProvider(
            "https://example.invalid/messages", "model", "token", use_proxy=False
        )
        with self.assertRaises(IncompleteModelOutputError) as raised:
            provider.complete([{"role": "user", "content": "request"}])
        self.assertEqual(raised.exception.finish_reason, "max_tokens")
        self.assertEqual(provider.audit_records[0]["raw_output"], '{"partial": true}')
        self.assertFalse(provider.audit_records[0]["complete"])

    @patch("providers.openai_compatible.build_opener")
    def test_openai_length_is_failure_with_actual_request_and_raw_audit(self, opener):
        opener.return_value.open.return_value = JSONResponse({
            "choices": [{
                "message": {"content": '{"partial": true}'},
                "finish_reason": "length",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        })
        provider = OpenAICompatibleProvider(
            "https://example.invalid/chat/completions", "model", use_proxy=False
        )
        with self.assertRaises(IncompleteModelOutputError):
            provider.complete(
                [{"role": "user", "content": "request"}], max_tokens=20
            )
        audit = provider.audit_records[0]
        self.assertEqual(audit["finish_reason"], "length")
        self.assertEqual(audit["request"]["max_tokens"], 20)
        self.assertEqual(audit["raw_output"], '{"partial": true}')
        self.assertFalse(audit["complete"])


if __name__ == "__main__":
    unittest.main()
