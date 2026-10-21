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

    @patch("evaluation.t4_multimodal.sleep")
    def test_transient_retries_keep_request_and_charge_each_attempt(self, sleep):
        with TemporaryDirectory() as directory:
            budget = RequestBudget(Path(directory) / "budget.json", 3)
            p = AuditedProvider({"provider": "openai_compatible", "endpoint": "http://localhost/api",
                                 "model": "fixture"}, Path(directory) / "calls", budget, max_attempts=3)
            with patch.object(p.provider, "complete", side_effect=[
                    RuntimeError("provider HTTP 503"), RuntimeError("The service is busy"), "ok"]):
                self.assertEqual(p.complete([{"role": "user", "content": "fixed"}], temperature=0.6), "ok")
            calls = [json.loads(p.read_text()) for p in sorted((Path(directory) / "calls").glob("*.json"))]
            self.assertEqual(budget.count, 3)
            self.assertEqual([c["status"] for c in calls], ["failed", "failed", "completed"])
            self.assertTrue(all(c["messages"] == calls[0]["messages"] and c["sampling"] == calls[0]["sampling"] for c in calls))

    @patch("evaluation.t4_multimodal.sleep")
    def test_truncation_and_parameter_errors_are_not_resampled(self, sleep):
        for error in ("provider stream was truncated: length", "parameter temperature is incompatible"):
            with TemporaryDirectory() as directory:
                budget = RequestBudget(Path(directory) / "budget.json", 3)
                p = AuditedProvider({"provider": "openai_compatible", "endpoint": "http://localhost/api",
                                     "model": "fixture"}, Path(directory) / "calls", budget, max_attempts=3)
                with patch.object(p.provider, "complete", side_effect=RuntimeError(error)):
                    with self.assertRaises(RuntimeError):
                        p.complete([{"role": "user", "content": "fixed"}])
                self.assertEqual(budget.count, 1)

    def test_exact_replay_preserves_invalid_output_and_rejects_changed_request(self):
        from scripts.resume_t4_transport import ExactReplayProvider
        with TemporaryDirectory() as directory:
            source, dest = Path(directory) / "source", Path(directory) / "dest"
            source.mkdir()
            messages = [{"role": "user", "content": "original"}]
            (source / "0001.json").write_text(json.dumps({"messages": messages,
                "sampling": {"temperature": 0.6}, "status": "completed", "raw_output": "invalid json retained"}))
            budget = RequestBudget(Path(directory) / "budget.json", 3)
            config = {"provider": "openai_compatible", "endpoint": "http://localhost/api", "model": "fixture"}
            p = ExactReplayProvider(config, source, dest, budget, dry_run=True)
            self.assertEqual(p.complete(messages, temperature=0.6), "invalid json retained")
            self.assertEqual(budget.count, 0)
            p = ExactReplayProvider(config, source, dest, budget, dry_run=True)
            with self.assertRaisesRegex(RuntimeError, "saved request mismatch"):
                p.complete(messages, temperature=1)
            self.assertEqual(budget.count, 0)

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
