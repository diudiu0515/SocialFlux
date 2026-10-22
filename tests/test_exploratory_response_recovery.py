import unittest
from scripts.recover_exploratory_response_budget import ReplayPrefixProvider, BUDGET


class Stub:
    def __init__(self):
        self.calls = []
        self.audit_records = []

    def complete(self, messages, **generation):
        self.calls.append((messages, generation))
        return "fresh"


class RecoveryTests(unittest.TestCase):
    def test_prefix_is_replayed_not_resampled(self):
        stub = Stub()
        saved = {"messages": [{"role": "user", "content": "original"}], "generation": {"seed": 1},
                 "raw_output": "saved", "provider_audit_records": [{"complete": True}]}
        provider = ReplayPrefixProvider(stub, [saved], "source")
        self.assertEqual(provider.complete(saved["messages"], seed=1), "saved")
        self.assertEqual(stub.calls, [])
        self.assertTrue(provider.audit_records[0]["replayed_saved_call"])
        self.assertEqual(provider.complete([], seed=1), "fresh")

    def test_context_mismatch_never_falls_back_to_fresh_call(self):
        stub = Stub()
        saved = {"messages": [], "generation": {}, "raw_output": "saved"}
        provider = ReplayPrefixProvider(stub, [saved], "source")
        with self.assertRaises(ValueError):
            provider.complete([{"role": "user", "content": "different"}])
        self.assertEqual(stub.calls, [])

    def test_recovery_changes_only_budget_at_failed_response(self):
        stub = Stub()
        failed = {"messages": [], "generation": {"temperature": 0.35}}
        provider = ReplayPrefixProvider(stub, [], "source", response=True, failed=failed)
        with self.assertRaises(ValueError):
            provider.complete([], temperature=0.7, max_tokens=BUDGET)
        self.assertEqual(stub.calls, [])
        self.assertEqual(provider.complete([], temperature=0.35, max_tokens=BUDGET), "fresh")
        self.assertTrue(provider.failed_request_matched)


if __name__ == "__main__":
    unittest.main()
