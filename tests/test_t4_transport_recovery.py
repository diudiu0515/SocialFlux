import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from evaluation.t4_multimodal import AuditedProvider, RequestBudget, assess_run_health
from providers.base import IncompleteModelOutputError
from providers.openai_compatible import OpenAICompatibleProvider
from tests.test_provider_sampling import FakeStreamResponse


def events(*values):
    return [("data: " + json.dumps(value) + "\n").encode() for value in values]


class TransportRecoveryTest(unittest.TestCase):
    def provider(self):
        return OpenAICompatibleProvider("http://localhost/v1/chat/completions", "fixture", stream=True)

    def test_stream_truncation_retains_partial_output_and_never_becomes_success(self):
        for reason in ["length", None]:
            provider = self.provider()
            with self.assertRaises(IncompleteModelOutputError):
                provider._read_stream(events({"choices": [{"delta": {"content": '{"x":'},
                                                           "finish_reason": reason}]}))
            audit = provider.audit_records[-1]
            self.assertFalse(audit["complete"])
            self.assertEqual(audit["raw_output"], '{"x":')

    def test_upstream_error_is_retained_instead_of_becoming_generic_empty_content(self):
        provider = self.provider()
        with self.assertRaisesRegex(RuntimeError, "overloaded"):
            provider._read_stream(events({"error": {"message": "overloaded"}}))
        self.assertEqual(provider.audit_records[-1]["stream_events"][0]["error"]["message"], "overloaded")

    def test_usage_snapshots_are_not_summed_and_reasoning_is_not_answer(self):
        provider = self.provider()
        result = provider._read_stream(events(
            {"choices": [{"delta": {"reasoning_content": "private"}}], "usage": {"completion_tokens": 2}},
            {"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}],
             "usage": {"completion_tokens": 5}},
        ))
        self.assertEqual(result, "ok")
        self.assertEqual(provider.usage["completion_tokens"], 5)

    @patch("providers.openai_compatible.monotonic", side_effect=[0, 2, 2, 12])
    @patch("providers.openai_compatible.build_opener")
    def test_duration_includes_response_body(self, opener, clock):
        opener.return_value.open.return_value = FakeStreamResponse()
        provider = self.provider()
        provider.complete([{"role": "user", "content": "test"}])
        self.assertEqual(provider.metrics["request_duration_seconds"], 12)

    @patch("providers.openai_compatible.build_opener")
    def test_failed_stream_audit_is_saved_to_disk(self, opener):
        class ErrorResponse(FakeStreamResponse):
            def __iter__(self):
                return iter(events({"error": {"message": "upstream failure"}}))
        opener.return_value.open.return_value = ErrorResponse()
        with TemporaryDirectory() as directory:
            provider = AuditedProvider({"provider": "openai_compatible", "endpoint": "http://localhost/api",
                                        "model": "fixture", "stream": True}, Path(directory) / "calls",
                                       RequestBudget(Path(directory) / "budget.json", 1))
            with self.assertRaises(RuntimeError):
                provider.complete([{"role": "user", "content": "test"}])
            saved = json.loads((Path(directory) / "calls/0001.json").read_text())
            self.assertEqual(saved["status"], "failed")
            self.assertIn("wall_seconds", saved)
            self.assertEqual(saved["response_audits"][0]["stream_events"][0]["error"]["message"], "upstream failure")

    def test_one_video_success_cannot_unlock_high_failure_pilot(self):
        rows = [{"scenario_id": "A", "model_id": "gpt", "condition": c, "status": "completed",
                 "video_delivery_count": int(c == "text_video")} for c in ["text_only", "text_video"]]
        rows += [{"scenario_id": "B", "model_id": "gpt", "condition": c, "status": "failed"}
                 for c in ["text_only", "text_video"]]
        self.assertFalse(assess_run_health(rows, ["gpt"])["passed"])

    def test_each_supported_video_model_needs_a_real_matched_pair(self):
        rows = [{"scenario_id": "A", "model_id": "gpt", "condition": c, "status": "completed",
                 "video_delivery_count": int(c == "text_video")} for c in ["text_only", "text_video"]]
        self.assertTrue(assess_run_health(rows, ["gpt"])["passed"])
        self.assertFalse(assess_run_health(rows, ["gpt", "claude"])["passed"])
        rows[-1]["video_delivery_count"] = 0
        self.assertFalse(assess_run_health(rows, ["gpt"])["passed"])


if __name__ == "__main__":
    unittest.main()
