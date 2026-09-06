import unittest

from environment.response_generator import ModelResponseGenerator
from policies.model_policy import ModelPolicy
from providers.text import (
    avoids_unsupported_offscreen_claim,
    complete_distinct_text,
    follows_dialogue_format,
    follows_policy_action_format,
    text_similarity,
)


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

    def test_policy_rejects_echo_of_latest_environment_response(self):
        provider = SequenceProvider(["环境上一句", "我的新行动"])
        policy = ModelPolicy("p", provider)
        result = policy.generate({
            "history": [
                {"role": "evaluated_agent", "text": "我的旧行动"},
                {"role": "environment_agent", "text": "环境上一句"},
            ]
        })
        self.assertEqual(result["text"], "我的新行动")
        self.assertEqual(provider.calls, 2)

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

    def test_response_rejects_echo_of_latest_action(self):
        provider = SequenceProvider(["请提交证据", "我会先核对记录"])
        generator = ModelResponseGenerator(provider)
        result = generator.generate({
            "history": [],
            "action": {"text": "请提交证据"},
        })
        self.assertEqual(result, "我会先核对记录")
        self.assertEqual(provider.calls, 2)

    def test_similarity_detects_small_rephrasing(self):
        self.assertGreater(text_similarity("我们现在按清单推进", "我们现在按清单继续推进"), 0.6)

    def test_dialogue_format_rejects_stage_directions_and_labels(self):
        self.assertFalse(follows_dialogue_format("（叹气）我们继续。"))
        self.assertFalse(follows_dialogue_format("顾岚：我们继续。"))
        self.assertTrue(follows_dialogue_format("我们继续核对下一项。"))

    def test_policy_retries_invented_completed_submission(self):
        provider = SequenceProvider([
            "我已提交申请，申请号为 HR-2024-01。",
            "我会先向人事确认可用的复核流程。",
        ])
        result = ModelPolicy("p", provider).generate({"history": []})
        self.assertEqual(result["text"], "我会先向人事确认可用的复核流程。")
        self.assertEqual(provider.calls, 2)

    def test_policy_retries_prompt_facing_analysis_and_long_action(self):
        provider = SequenceProvider([
            "根据最新的环境响应，我需要了解评级依据。因此，我将提出以下问题：经理，可以解释吗？",
            "我想先核对这次评级采用了哪些可公开的工作记录。",
        ])
        result = ModelPolicy("p", provider).generate({"history": []})
        self.assertEqual(result["text"], "我想先核对这次评级采用了哪些可公开的工作记录。")
        self.assertEqual(provider.calls, 2)
        self.assertFalse(follows_policy_action_format("先说明。\n1. 核对记录"))
        self.assertFalse(follows_policy_action_format("我" * 181))

    def test_response_retries_invented_third_party_system_action(self):
        provider = SequenceProvider([
            "HR 已登记申请，系统将自动锁定评级。",
            "我可以把你的请求转给人事，但无法预先承诺结果。",
        ])
        result = ModelResponseGenerator(provider).generate({"history": [], "action": {"text": "请复核"}})
        self.assertEqual(result, "我可以把你的请求转给人事，但无法预先承诺结果。")
        self.assertEqual(provider.calls, 2)

    def test_offscreen_claim_validator_rejects_specific_clause_and_ticket(self):
        self.assertFalse(avoids_unsupported_offscreen_claim("根据政策第7.2条，我有权复核。"))
        self.assertFalse(avoids_unsupported_offscreen_claim("申请号为 HR-123。"))
        self.assertFalse(avoids_unsupported_offscreen_claim("要求 HR 三日内答复。"))
        self.assertTrue(avoids_unsupported_offscreen_claim("我会先确认是否存在复核渠道。"))


if __name__ == "__main__":
    unittest.main()
