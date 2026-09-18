import unittest

from providers.structured import complete_json


class SequenceProvider:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0
        self.samplings = []
        self.messages = []

    def complete(self, messages, **sampling):
        self.samplings.append(dict(sampling))
        self.messages.append([dict(item) for item in messages])
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

    def test_accepts_fenced_json_with_redundant_closers(self):
        provider = SequenceProvider(['```json\n{"ok": true}]}\n```'])
        result = complete_json(
            provider, [], {}, lambda value: value, context="test"
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(provider.calls, 1)

    def test_trailing_prose_is_not_silently_accepted(self):
        provider = SequenceProvider([
            '{"ok": true} trailing', '{"ok": true} trailing', '{"ok": true}'
        ])
        result = complete_json(provider, [], {}, lambda value: value, context="test")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(provider.calls, 3)


    def test_schema_retry_receives_validation_feedback(self):
        provider = SequenceProvider(['{"wrong": 1}', '{"ok": true}'])
        seen = provider
        value = complete_json(
            provider,
            [{"role": "user", "content": "return ok"}],
            {},
            lambda item: item if set(item) == {"ok"} else (_ for _ in ()).throw(ValueError("expected ok")),
            context="feedback",
            max_attempts=2,
        )
        self.assertEqual(value, {"ok": True})
        self.assertEqual(seen.calls, 2)

    def test_retry_raises_sampling_floor_for_a_new_candidate(self):
        provider = SequenceProvider(["{}", '{"ok": true}'])
        result = complete_json(
            provider, [], {"temperature": 0.2, "top_p": 0.5},
            lambda value: value if set(value) == {"ok"} else (_ for _ in ()).throw(ValueError("shape")),
            context="sampling", max_attempts=2,
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(provider.samplings[0]["temperature"], 0.2)
        self.assertEqual(provider.samplings[1]["temperature"], 0.7)
        self.assertEqual(provider.samplings[1]["top_p"], 0.9)

    def test_retry_receives_content_specific_guidance(self):
        provider = SequenceProvider(["{}", "{\"ok\": true}"])
        result = complete_json(
            provider, [{"role": "user", "content": "fixed"}], {},
            lambda value: value if set(value) == {"ok"} else (_ for _ in ()).throw(ValueError("semantic loop")),
            context="semantic", max_attempts=2,
            retry_guidance="Use a present-tense pause instead of repeating the plan.",
        )
        self.assertEqual(result, {"ok": True})
        retry_text = provider.messages[1][-1]["content"]
        self.assertIn("semantic loop", retry_text)
        self.assertIn("revision attempt 2", retry_text)
        self.assertIn("present-tense pause", retry_text)


    def test_fails_after_bounded_attempts(self):
        provider = SequenceProvider(["{}", "{}", "{}"] )
        with self.assertRaisesRegex(ValueError, "after 3 attempts") as caught:
            complete_json(provider, [], {}, lambda value: (_ for _ in ()).throw(ValueError("bad")), context="test")
        self.assertEqual(provider.calls, 3)
        self.assertEqual(len(caught.exception.diagnostics), 3)
        self.assertTrue(all(item["raw"] == "{}" for item in caught.exception.diagnostics))
        self.assertTrue(all(item["reason"] == "bad" for item in caught.exception.diagnostics))


if __name__ == "__main__":
    unittest.main()
