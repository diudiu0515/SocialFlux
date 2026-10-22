import unittest

from scripts.run_r3_rule_length_ablation import (
    natural_closure, request_counts, semantic_natural_closure,
)


class Counter:
    def __init__(self, requests):
        self.requests = requests


class R3RuleLengthAblationTest(unittest.TestCase):
    def test_natural_closure_is_explicit_and_conservative(self):
        self.assertTrue(natural_closure(
            "我没有别的问题了。", "好，今天先谈到这里。", 6, 4
        ))
        self.assertTrue(natural_closure(
            "今天先谈到这里。", "好的，今天就到这里。我会记住这个安排。", 8, 4
        ))
        self.assertFalse(natural_closure(
            "我没有别的问题了。", "好，下周我们再谈。", 6, 4
        ))
        self.assertFalse(natural_closure(
            "今天先谈到这里。", "好，今天先谈到这里。", 3, 4
        ))

    def test_semantic_closure_only_applies_without_future_fragment(self):
        turn = {
            "appraisal": {"dialogue_diagnostics": {
                "continuation": {"status": "can_close", "evidence_span": ""}
            }},
            "observation_after": {"longitudinal_context": {}},
            "interaction_ledger_after_public_events": {"latest_obligation": None},
            "segment_transition_after": None,
        }
        self.assertTrue(semantic_natural_closure(turn, 6, 4))
        turn["observation_after"]["longitudinal_context"]["next_interaction"] = {
            "after": 30, "unit": "day"
        }
        self.assertFalse(semantic_natural_closure(turn, 6, 4))

    def test_request_counts_distinguish_stages_and_retries(self):
        counts = request_counts(Counter(7), Counter(5), Counter(6), 4, 5)
        self.assertEqual(counts["completed_turns"], 4)
        self.assertEqual(counts["attempted_turns"], 5)
        self.assertEqual(counts["environment_requests"], 11)
        self.assertEqual(counts["environment_retry_overhead"], 1)
        self.assertEqual(counts["all_stage_retry_overhead"], 3)
        self.assertEqual(counts["environment_llm_stage_count_per_turn"], 2)


if __name__ == "__main__":
    unittest.main()
