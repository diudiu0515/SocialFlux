import unittest

from providers.structured import complete_json


class SequenceProvider:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0

    def complete(self, messages, **sampling):
        self.calls += 1
        return next(self.outputs)


class StructuredRetryTest(unittest.TestCase):
    def test_retries_json_and_schema_failures(self):
        provider = SequenceProvider(["not-json", "{}", '{"ok": true}'])

        def validate(value):
            if set(value) != {"ok"}:
                raise ValueError("shape")
            return value

        result = complete_json(provider, [{"role": "user", "content": "fixed"}], {}, validate, context="test")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(provider.calls, 3)

    def test_fails_after_bounded_attempts(self):
        provider = SequenceProvider(["{}", "{}", "{}"] )
        with self.assertRaisesRegex(ValueError, "after 3 attempts"):
            complete_json(provider, [], {}, lambda value: (_ for _ in ()).throw(ValueError("bad")), context="test")
        self.assertEqual(provider.calls, 3)


if __name__ == "__main__":
    unittest.main()
