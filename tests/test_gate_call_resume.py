from pathlib import Path
import tempfile
import unittest

from offline.choice_builder import save
from scripts.resume_gate_machine_calls import ReuseCompletedCalls
from web.live_rollouts import ROOT


class NetworkForbidden:
    timeout = 100
    def complete(self, messages, **kwargs):
        raise AssertionError("cached request must not call network")


class _UnifiedStateProvider:
    def __init__(self):
        self.provider = NetworkForbidden()
        self.actual_requests = []
    def complete(self, messages, **generation):
        self.actual_requests.append({"messages": messages, "generation": generation})
        return self.provider.complete(messages, **generation)


class GateCallResumeTests(unittest.TestCase):
    def test_cached_state_call_preserves_actor_request_audit_without_network(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            messages = [{"role": "user", "content": "exact frozen request"}]
            save(Path(directory) / "original.json", {"status": "completed", "started_at_unix": 1,
                 "messages": messages, "generation": {"temperature": 0}, "raw_output": '{"state":"frozen"}'})
            bound = _UnifiedStateProvider()
            provider = ReuseCompletedCalls(bound, directory)
            self.assertEqual(provider.complete(messages, temperature=0), '{"state":"frozen"}')
            self.assertEqual(len(bound.actual_requests), 1)
            self.assertIsInstance(bound.provider, NetworkForbidden)
            self.assertEqual(len(list((Path(directory) / "reuse").glob("*.json"))), 1)

    def test_failure_output_cannot_be_reused_as_success(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            messages = [{"role": "user", "content": "exact frozen request"}]
            save(Path(directory) / "failed.json", {"status": "failed", "started_at_unix": 1,
                 "messages": messages, "generation": {}, "raw_output": "not a successful response"})
            provider = ReuseCompletedCalls(NetworkForbidden(), directory)
            with self.assertRaisesRegex(AssertionError, "network"):
                provider.complete(messages)


if __name__ == "__main__":
    unittest.main()
