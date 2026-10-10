import unittest

from scripts.run_state_v3_shadow_replay import (
    FixedTranscriptResponseGenerator,
    filter_unsupported_claim_impacts,
    shadow_replay_minimum_natural_turns,
    transition_summary,
)


class StateV3ShadowReplayTest(unittest.TestCase):
    def test_fixed_response_generator_preserves_recorded_text(self):
        generator = FixedTranscriptResponseGenerator([{
            "environment_response": "fixed response",
            "environment_response_ledger_events": [],
        }], prompt_id="environment_response_v27")
        result = generator.generate({"turn_id": 1})
        self.assertEqual(result["response_text"], "fixed response")
        self.assertEqual(generator.provenance["response_model_calls"], 0)

    def test_shadow_replay_keeps_the_complete_source_transcript_active(self):
        self.assertEqual(shadow_replay_minimum_natural_turns(10, 16), 16)
        self.assertEqual(shadow_replay_minimum_natural_turns(10, 10), 10)
        with self.assertRaisesRegex(ValueError, "1-20 turns"):
            shadow_replay_minimum_natural_turns(10, 21)

    def test_unsupported_claim_span_cannot_supply_shadow_state_evidence(self):
        appraisal = {
            "state_impacts": [
                {"variable": "relationship.trust", "evidence_span": "确定会被处分"},
                {"variable": "behavioral_disposition.resolve", "evidence_span": "我会提交记录"},
            ],
            "dynamics_impacts": [],
        }
        filtered, removed = filter_unsupported_claim_impacts(
            appraisal,
            [{"claim_span": "确定会被处分"}],
        )
        self.assertEqual(len(filtered["state_impacts"]), 1)
        self.assertEqual(
            filtered["state_impacts"][0]["evidence_span"], "我会提交记录"
        )
        self.assertEqual(len(removed), 1)
        self.assertEqual(len(appraisal["state_impacts"]), 2)

    def test_transition_summary_counts_family_activity(self):
        summary = transition_summary([{
            "numeric_state_delta": {
                "emotion": {"anxiety": -1},
                "relationship": {"trust": 0},
            },
            "trigger_events": [{"trigger_id": "one"}],
        }])
        self.assertEqual(summary["turns_with_any_state_change"], 1)
        self.assertEqual(summary["online_multimodal_trigger_count"], 1)
        self.assertEqual(
            summary["state_family_activity"]["emotion"]
            ["changed_variable_turn_count"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
