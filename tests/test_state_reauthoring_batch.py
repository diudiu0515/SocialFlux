import unittest

from providers.openai_compatible import ProviderHTTPError
from scripts.reauthor_state_layers import is_provider_overload


class StateReauthoringBatchTest(unittest.TestCase):
    def test_detects_structured_http_429(self):
        self.assertTrue(is_provider_overload(
            ProviderHTTPError(429, "temporarily unavailable")
        ))

    def test_detects_wrapped_overload_message(self):
        try:
            try:
                raise RuntimeError("provider is overloaded")
            except RuntimeError as inner:
                raise ValueError("state authoring failed") from inner
        except ValueError as outer:
            self.assertTrue(is_provider_overload(outer))

    def test_schema_failure_is_not_provider_overload(self):
        self.assertFalse(is_provider_overload(
            ValueError("selected state family is invalid")
        ))


if __name__ == "__main__":
    unittest.main()
