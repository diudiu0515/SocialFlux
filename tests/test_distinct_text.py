import unittest

from environment.response_generator import ModelResponseGenerator
from policies.model_policy import ModelPolicy
from providers.text import complete_distinct_text, follows_dialogue_format, text_similarity


class SequenceProvider:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = 0

    def complete(self, messages, **sampling):
        self.calls += 1
        return next(self.values)


class DistinctTextTest(unittest.TestCase):
    def test_retries_exact_and_near_duplicate(self):
        provider = SequenceProvider(["旧句", "旧句。", "真正推进的新句"])
        value = complete_distinct_text(
            provider,
            [{"role": "user", "content": "fixed"}],
            {},
            ["旧句"],
            context="test",
        )
        self.assertEqual(value, "真正推进的新句")
        self.assertEqual(provider.calls, 3)

    def test_policy_only_compares_evaluated_agent_history(self):
        provider = SequenceProvider(["环境上一句", "我的新行动"])
        policy = ModelPolicy("p", provider)
        result = policy.generate({
            "history": [
                {"role": "evaluated_agent", "text": "我的旧行动"},
                {"role": "environment_agent", "text": "环境上一句"},
            ]
        })
        self.assertEqual(result["text"], "环境上一句")
        self.assertEqual(provider.calls, 1)

    def test_response_retries_prior_environment_response(self):
        provider = SequenceProvider(["环境旧回应", "环境新回应"])
        generator = ModelResponseGenerator(provider)
        result = generator.generate({
            "history": [
                {"role": "evaluated_agent", "text": "行动"},
                {"role": "environment_agent", "text": "环境旧回应"},
            ]
        })
        self.assertEqual(result, "环境新回应")
        self.assertEqual(provider.calls, 2)

    def test_similarity_detects_small_rephrasing(self):
        self.assertGreater(text_similarity("我们现在按清单推进", "我们现在按清单继续推进"), 0.6)

    def test_dialogue_format_rejects_stage_directions_and_labels(self):
        self.assertFalse(follows_dialogue_format("（叹气）我们继续。"))
        self.assertFalse(follows_dialogue_format("顾岚：我们继续。"))
        self.assertTrue(follows_dialogue_format("我们继续核对下一项。"))


if __name__ == "__main__":
    unittest.main()
