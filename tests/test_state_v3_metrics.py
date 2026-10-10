import unittest

from evaluation.state_v3_metrics import state_v3_trajectory_metrics


class StateV3MetricsTest(unittest.TestCase):
    def test_requires_four_family_fast_and_compliant_slow_coverage(self):
        initial = {
            "emotion": {"anxiety": 5},
            "behavioral_disposition": {"decision_readiness": 5},
            "relationship": {"trust": 5},
            "consequence_risk": {"decision_error_risk": 5},
        }
        turns = []
        changes = {
            1: ("emotion.anxiety", "turn_local", 1, False, 0),
            2: (
                "behavioral_disposition.decision_readiness",
                "turn_to_episode",
                1,
                False,
                0,
            ),
            3: ("relationship.trust", "cross_turn_slow", 1, False, 1),
            4: (
                "consequence_risk.decision_error_risk",
                "event_responsive",
                -1,
                False,
                0,
            ),
        }
        state = initial
        for turn_id in range(1, 11):
            delta = {
                family: {variable: 0 for variable in values}
                for family, values in initial.items()
            }
            diagnostics = []
            if turn_id in changes:
                path, timescale, amount, decisive, prior = changes[turn_id]
                family, variable = path.split(".", 1)
                delta[family][variable] = amount
                diagnostics.append({
                    "variable": path,
                    "selected": True,
                    "evidence_span": f"evidence {turn_id}",
                    "feature_compatible": True,
                    "timescale": timescale,
                    "decisive_evidence": decisive,
                    "prior_consistent_evidence": prior,
                })
            turns.append({
                "turn_id": turn_id,
                "numeric_state_delta": delta,
                "state_after": state,
                "calibration": {"state_impacts": diagnostics},
            })
        result = state_v3_trajectory_metrics({
            "trajectory_id": "t",
            "initial_state": initial,
            "turns": turns,
        })
        self.assertTrue(result["machine_passed"])
        self.assertTrue(
            result["requirements"][
                "turn_count_in_main_10_to_20_window"
            ]
        )
        self.assertEqual(result["turn_count"], 10)
        self.assertEqual(set(result["family_changes"]), set(initial))
        self.assertEqual(result["compliant_slow_changes"], 1)

    def test_shared_span_rule_is_profile_versioned(self):
        initial = {
            "emotion": {"hope": 5},
            "behavioral_disposition": {"cooperation_readiness": 5},
            "relationship": {"trust": 5},
            "consequence_risk": {"decision_error_risk": 5},
        }
        diagnostics = [
            {
                "variable": "emotion.hope",
                "selected": True,
                "evidence_span": "one event",
                "feature_compatible": True,
                "timescale": "turn_local",
                "decisive_evidence": True,
                "prior_consistent_evidence": 0,
            },
            {
                "variable": "behavioral_disposition.cooperation_readiness",
                "selected": True,
                "evidence_span": "one event",
                "feature_compatible": True,
                "timescale": "turn_to_episode",
                "decisive_evidence": True,
                "prior_consistent_evidence": 0,
            },
        ]
        def trajectory(profile):
            turns = []
            for turn_id in range(1, 11):
                turns.append({
                    "turn_id": f"t{turn_id}",
                    "numeric_state_delta": {
                        family: {variable: 0 for variable in values}
                        for family, values in initial.items()
                    },
                    "state_after": initial,
                    "calibration": {
                        "calibration_profile": profile,
                        "state_impacts": diagnostics if turn_id == 1 else [],
                    },
                })
            return {
                "trajectory_id": profile,
                "initial_state": initial,
                "turns": turns,
            }

        legacy = state_v3_trajectory_metrics(
            trajectory("evidence_independent_hysteretic_v3")
        )
        causal = state_v3_trajectory_metrics(
            trajectory("evidence_causal_hysteretic_v5")
        )
        self.assertFalse(
            legacy["requirements"]["no_duplicate_selected_evidence_span"]
        )
        self.assertTrue(
            causal["requirements"]["no_duplicate_selected_evidence_span"]
        )
        self.assertEqual(causal["duplicate_selected_spans"], ["t1"])
        self.assertTrue(
            causal["shared_evidence_across_distinct_variables_allowed"]
        )

    def test_reports_missing_family_and_slow_change_without_fabricating_delta(self):
        initial = {
            "emotion": {"anxiety": 5},
            "behavioral_disposition": {"decision_readiness": 5},
            "relationship": {"trust": 5},
            "consequence_risk": {"decision_error_risk": 5},
        }
        turns = []
        for turn_id in range(1, 21):
            delta = {
                family: {variable: 0 for variable in values}
                for family, values in initial.items()
            }
            diagnostics = []
            if turn_id == 1:
                delta["emotion"]["anxiety"] = 1
                diagnostics.append({
                    "variable": "emotion.anxiety",
                    "selected": True,
                    "evidence_span": "new direct evidence",
                    "feature_compatible": True,
                    "timescale": "turn_local",
                    "decisive_evidence": False,
                    "prior_consistent_evidence": 0,
                })
            turns.append({
                "turn_id": f"t{turn_id}",
                "numeric_state_delta": delta,
                "state_after": initial,
                "calibration": {"state_impacts": diagnostics},
            })
        result = state_v3_trajectory_metrics({
            "trajectory_id": "under-realized",
            "initial_state": initial,
            "turns": turns,
        })
        self.assertTrue(result["state_update_integrity_passed"])
        self.assertTrue(result["machine_passed"])
        self.assertFalse(result["coverage_sufficient"])
        self.assertFalse(result["coverage_targets"]["all_four_families_changed"])
        self.assertFalse(result["coverage_targets"]["has_compliant_slow_change"])
        self.assertEqual(result["selected_impacts"], 1)


if __name__ == "__main__":
    unittest.main()
