import unittest
from unittest.mock import patch

from providers.base import ModelProvider
from providers.failover import FailoverProvider


class FakeProvider(ModelProvider):
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def complete(self, messages, **generation):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result

    def reset(self):
        self.calls = 0

    @property
    def usage(self):
        return {}

    @property
    def metrics(self):
        return {"request_duration_seconds": 0.0}

    @property
    def provenance(self):
        return {"provider": "fake"}


class FailoverProviderTest(unittest.TestCase):
    @patch("providers.failover._next_candidate_slot", return_value=0)
    def test_moves_to_next_interface_after_error(self, _slot):
        first = FakeProvider(error=TimeoutError("overloaded"))
        second = FakeProvider(result="ok")
        provider = FailoverProvider([first, second], model="model")
        self.assertEqual(
            provider.complete([{"role": "user", "content": "test"}]),
            "ok",
        )
        self.assertEqual((first.calls, second.calls), (1, 1))
        self.assertEqual(provider.metrics["failed_request_count"], 1)
        self.assertEqual(provider.metrics["candidate_successes"], {1: 1})

    @patch("providers.failover._next_candidate_slot", return_value=0)
    def test_exhausts_all_interfaces_before_raising(self, _slot):
        first = FakeProvider(error=TimeoutError("first"))
        second = FakeProvider(error=RuntimeError("second"))
        provider = FailoverProvider([first, second], model="model")
        with self.assertRaisesRegex(RuntimeError, "second"):
            provider.complete([{"role": "user", "content": "test"}])
        self.assertEqual((first.calls, second.calls), (1, 1))
        self.assertEqual(provider.metrics["failed_request_count"], 2)


    @patch("providers.failover._next_candidate_slot", return_value=0)
    def test_opens_circuit_and_skips_repeatedly_failing_route(self, _slot):
        first = FakeProvider(error=TimeoutError("overloaded"))
        second = FakeProvider(result="ok")
        provider = FailoverProvider(
            [first, second],
            model="model",
            circuit_failure_threshold=1,
            circuit_cooldown_seconds=300,
        )
        self.assertEqual(
            provider.complete([{"role": "user", "content": "first"}]),
            "ok",
        )
        self.assertEqual(
            provider.complete([{"role": "user", "content": "second"}]),
            "ok",
        )
        self.assertEqual(first.calls, 1)
        self.assertEqual(second.calls, 2)
        self.assertEqual(provider.metrics["candidate_circuit_skips"], {0: 1})
        self.assertEqual(provider.metrics["circuit_open_events"], 1)

    @patch("providers.failover._next_candidate_slot", return_value=0)
    def test_empty_content_switches_route_without_opening_circuit(self, _slot):
        empty = FakeProvider(result="")
        healthy = FakeProvider(result="ok")
        provider = FailoverProvider(
            [empty, healthy],
            model="model",
            circuit_failure_threshold=1,
            circuit_cooldown_seconds=300,
        )
        for _ in range(2):
            self.assertEqual(
                provider.complete([{"role": "user", "content": "test"}]),
                "ok",
            )
        self.assertEqual((empty.calls, healthy.calls), (2, 2))
        self.assertEqual(provider.metrics["circuit_open_events"], 0)
        self.assertEqual(provider.metrics["candidate_circuit_skips"], {})

    @patch("providers.failover._next_candidate_slot", return_value=0)
    def test_circuit_state_is_isolated_between_jobs(self, _slot):
        failed = FakeProvider(error=TimeoutError("overloaded"))
        failed.endpoint = "https://same.invalid/v1"
        backup = FakeProvider(result="backup")
        backup.endpoint = "https://backup.invalid/v1"
        first_job = FailoverProvider(
            [failed, backup],
            circuit_failure_threshold=1,
        )
        self.assertEqual(
            first_job.complete([{"role": "user", "content": "test"}]),
            "backup",
        )

        recovered = FakeProvider(result="fresh job")
        recovered.endpoint = "https://same.invalid/v1"
        second_job = FailoverProvider(
            [recovered],
            circuit_failure_threshold=1,
        )
        self.assertEqual(
            second_job.complete([{"role": "user", "content": "test"}]),
            "fresh job",
        )
        self.assertEqual(recovered.calls, 1)

    @patch("providers.failover._next_candidate_slot", return_value=0)
    def test_bounds_candidates_per_logical_request(self, _slot):
        first = FakeProvider(error=TimeoutError("first"))
        second = FakeProvider(error=TimeoutError("second"))
        third = FakeProvider(result="too late")
        provider = FailoverProvider(
            [first, second, third],
            model="model",
            max_candidates_per_request=2,
        )
        with self.assertRaisesRegex(TimeoutError, "second"):
            provider.complete([{"role": "user", "content": "test"}])
        self.assertEqual((first.calls, second.calls, third.calls), (1, 1, 0))
        self.assertEqual(provider.metrics["max_candidates_per_request"], 2)

    @patch("providers.failover.sleep")
    @patch("providers.failover.uniform", return_value=0.25)
    @patch("providers.failover._next_candidate_slot", return_value=0)
    def test_exponential_backoff_has_jitter(
        self, _slot, _uniform, mocked_sleep
    ):
        first = FakeProvider(error=TimeoutError("overloaded"))
        second = FakeProvider(result="ok")
        provider = FailoverProvider(
            [first, second],
            model="model",
            failover_backoff_base_seconds=2,
            failover_backoff_max_seconds=15,
            failover_backoff_jitter_seconds=1,
        )
        self.assertEqual(
            provider.complete([{"role": "user", "content": "test"}]),
            "ok",
        )
        mocked_sleep.assert_called_once_with(2.25)
        self.assertEqual(provider.metrics["failover_backoff_seconds"], 2.25)


if __name__ == "__main__":
    unittest.main()
