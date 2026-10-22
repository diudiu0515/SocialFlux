from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from environment.appraisal_context import build_appraisal_context, semantic_context, refreshed_memory
from environment.calibration import DeterministicStateCalibrator, FEATURE_NAMES
from scripts.validate_state_context_samples import prepare_case, BASE
from scripts.run_state_appraiser_backbone_probe import build_cases
from rollout.configuration import load_rollout_config


class AppraisalContextBoundaryTest(unittest.TestCase):
    def test_chronology_excludes_current_and_future_and_normalizes_ids(self):
        history = [{"turn_id": n, "role": "evaluated_agent", "text": "same"}
                   for n in (1, 2, 10, 11, 12)]
        context = build_appraisal_context(history=history, turns=[], action={"text": "same"},
                                          current_turn_id="t11")
        self.assertEqual([r["turn_id"] for r in context["historical_turns"]], ["t1", "t2", "t10"])
        self.assertEqual([r["historical_turn_id"] for r in context["duplicate_evidence_matches"]],
                         ["t1", "t2", "t10"])

    def test_numeric_update_cannot_change_semantic_request(self):
        kwargs = dict(history=[{"turn_id": 1, "role": "evaluated_agent", "text": "same"}],
                      turns=[{"turn_id": "t1", "numeric_state_delta": {"trust": 0}}],
                      action={"text": "same"}, current_turn_id="t2")
        before = build_appraisal_context(**kwargs)
        kwargs["turns"][0]["numeric_state_delta"]["trust"] = 2
        after = build_appraisal_context(**kwargs)
        self.assertEqual(semantic_context(before, kwargs["action"]), semantic_context(after, kwargs["action"]))
        with self.assertRaisesRegex(ValueError, "stale"):
            semantic_context(before, {"text": "different"})

    def test_pending_question_follows_obligation_owner_and_thread(self):
        ledger = {"latest_obligation": {"owner": "evaluated_agent", "source_thread_id": "right"},
                  "unresolved_threads": [{"id": "right", "text": "pending?"},
                                         {"id": "wrong", "text": "not pending?"}]}
        kwargs = dict(history=[], turns=[], action={"text": "answer"}, current_turn_id=2,
                      interaction_ledger=ledger)
        self.assertEqual(build_appraisal_context(**kwargs)["latest_unanswered_question"], "pending?")
        ledger["latest_obligation"]["owner"] = "environment_agent"
        self.assertEqual(build_appraisal_context(**kwargs)["latest_unanswered_question"], "")

    def test_current_repeat_control_request_is_rebuilt_after_override(self):
        cases = build_cases(BASE / "human_confirmed_fixed_set.json", BASE / "negative_control_candidates.json")
        case = next(c for c in cases if c["case_id"] == "trust_gpt003_exact_restatement_control")
        config = Path(__file__).resolve().parents[1] / "configs/gpt50_experiment/rollout.state_observed_evidence_v6_candidate.json"
        environment = load_rollout_config(config)["environment"]
        # Exercise the current template; the helper's v5 default is historical.
        with patch("scripts.validate_state_context_samples.PROMPT", environment["state_appraisal_prompt_id"]):
            prepared = prepare_case(case, environment)
        payload = prepared["payload"]
        self.assertEqual(payload["memory"]["deterministic_surface_duplicate_ids"], ["t2"])
        self.assertTrue(payload["appraisal_context"]["latest_unanswered_question"])
        self.assertNotIn("later confirms", payload["background"])
        self.assertNotIn("two independent", payload["state_semantics"]["variables"]["relationship.trust"]["update_rule"])
        self.assertNotIn("prior_numeric_update", str(payload["appraisal_context"]))

    def test_all_new_dynamics_update_without_feature_gate(self):
        state = {"relationship": {"trust": 4}}
        scenario = {"environment_agent": {"persona": {}},
                    "selected_state_variables": {"relationship": ["trust"]},
                    "initial_state": state}
        candidates = [{
            "variable": path, "direction": "decrease", "evidence_feature": None,
            "evidence_span": "uncertainty removed", "evidence_strength": 1,
            "directness": "indirect", "new_evidence": True,
        } for path in ("deadline_pressure", "information_asymmetry")]
        result = DeterministicStateCalibrator(scenario, profile="state_judgment_primary_hysteretic_v7").calibrate(
            {"state_impacts": [], "dynamics_impacts": candidates,
             "event_features": {name: 0 for name in FEATURE_NAMES}},
            state, {"deadline_pressure": 5, "information_asymmetry": 5}, current_event_id="t1")
        self.assertEqual(result["interaction_dynamics_delta"],
                         {"deadline_pressure": "mild_decrease", "information_asymmetry": "mild_decrease"})


if __name__ == "__main__":
    unittest.main()
