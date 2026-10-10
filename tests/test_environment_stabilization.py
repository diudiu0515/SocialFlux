import unittest

from environment.calibration import DeterministicStateCalibrator
from environment.interaction_ledger import (
    dialogue_focus,
    initial_ledger,
    record_environment_response,
    record_evaluated_action,
)
from evaluation.paraphrase_equivalence import strict_paraphrase_precheck
from evaluation.transition_metrics import compare_transition_outputs


def appraisal(state_impacts=None, dynamics_impacts=None):
    return {
        "speaker_intent": "推进核对",
        "social_act": "request",
        "event_features": {
            "goal_alignment": 1,
            "cooperation_signal": 1,
            "repair_signal": 0,
            "pressure": 0,
            "face_threat": 0,
            "commitment_signal": 0,
            "uncertainty_reduction": 1,
            "boundary_violation": 0,
            "respect_signal": 0,
            "withdrawal_signal": 0,
        },
        "state_impacts": list(state_impacts or []),
        "dynamics_impacts": list(dynamics_impacts or []),
    }


def impact(
    variable, *, feature="cooperation_signal", strength=1, direct="direct",
    new=True, span=None, direction="increase",
):
    value = {
        "variable": variable,
        "direction": direction,
        "evidence_feature": feature,
        "evidence_strength": strength,
        "directness": direct,
        "new_evidence": new,
    }
    if span is not None:
        value["evidence_span"] = span
    return value


class EnvironmentStabilizationTest(unittest.TestCase):
    def setUp(self):
        self.scenario = {
            "background": "双方正在核对记录。",
            "environment_agent": {
                "persona": {"empathy": 0.5, "patience": 0.5},
            },
        }
        self.state = {"relationship": {"trust": 5}, "emotion": {"hope": 4}}
        self.dynamics = {"negotiation_open": 5}

    def test_calibration_is_repeatable_and_suppresses_old_or_indirect_weak_evidence(self):
        value = appraisal([
            impact("relationship.trust"),
            impact("emotion.hope", direct="indirect"),
        ], [impact("negotiation_open", new=False)])
        calibrator = DeterministicStateCalibrator(self.scenario)
        first = calibrator.calibrate(value, self.state, self.dynamics)
        second = calibrator.calibrate(value, self.state, self.dynamics)
        self.assertEqual(first, second)
        self.assertEqual(first["state_delta"]["relationship"]["trust"], "mild_increase")
        self.assertEqual(first["state_delta"]["emotion"]["hope"], "similar")
        self.assertEqual(first["interaction_dynamics_delta"]["negotiation_open"], "similar")

    def test_ordinary_impacts_share_one_state_change_budget(self):
        state = {"emotion": {"a": 5, "b": 5, "c": 5, "d": 5}}
        impacts = [impact(f"emotion.{name}") for name in ("a", "b", "c", "d")]
        result = DeterministicStateCalibrator(self.scenario).calibrate(
            appraisal(impacts), state, {}
        )
        changed = [value for value in result["state_delta"]["emotion"].values() if value != "similar"]
        self.assertEqual(len(changed), 1)

    def test_bounded_noop_does_not_consume_change_budget(self):
        state = {"behavioral_disposition": {"cooperation": 10, "resolve": 5}}
        result = DeterministicStateCalibrator(self.scenario).calibrate(
            appraisal([
                impact("behavioral_disposition.cooperation", strength=2),
                impact("behavioral_disposition.resolve", strength=1),
            ]),
            state,
            {},
        )
        self.assertEqual(
            result["state_delta"]["behavioral_disposition"]["cooperation"],
            "similar",
        )
        self.assertEqual(
            result["state_delta"]["behavioral_disposition"]["resolve"],
            "mild_increase",
        )
        diagnostics = {
            item["variable"]: item.get("suppressed_by")
            for item in result["calibration"]["state_impacts"]
        }
        self.assertEqual(
            diagnostics["behavioral_disposition.cooperation"],
            "state_boundary_noop",
        )

    def test_v2_ordinary_event_updates_at_most_two_independently_supported_variables(self):
        state = {
            "emotion": {"anxiety": 5, "hope": 5},
            "behavioral_disposition": {"resolve": 5},
            "relationship": {"trust": 5},
            "consequence_risk": {"goal_failure_risk": 5},
        }
        scenario = {
            **self.scenario,
            "initial_state": state,
        }
        result = DeterministicStateCalibrator(
            scenario, profile="evidence_balanced_v2"
        ).calibrate(
            appraisal([
                impact("emotion.anxiety", span="解释了原因"),
                impact("behavioral_disposition.resolve", span="提出了方案"),
                impact("emotion.hope", span="确认了时间"),
            ]),
            state,
            {},
        )
        changed = [
            path
            for family, values in result["state_delta"].items()
            for path, value in values.items()
            if value != "similar"
        ]
        self.assertEqual(len(changed), 2)
        self.assertEqual(
            result["calibration"]["ordinary_change_budget"]["state"], 2
        )

    def test_evidence_bound_sparse_preserves_one_change_ordinary_budget(self):
        state = {
            "emotion": {"anxiety": 5},
            "behavioral_disposition": {"resolve": 5},
        }
        scenario = {**self.scenario, "initial_state": state}
        result = DeterministicStateCalibrator(
            scenario, profile="evidence_bound_sparse_v2"
        ).calibrate(
            appraisal([
                impact("emotion.anxiety", span="新增不确定性"),
                impact("behavioral_disposition.resolve", span="作出决定"),
            ]),
            state,
            {},
        )
        changed = sum(
            value != "similar"
            for family in result["state_delta"].values()
            for value in family.values()
        )
        self.assertEqual(changed, 1)
        self.assertEqual(
            result["calibration"]["ordinary_change_budget"]["state"], 1
        )

    def test_v3_applies_two_independent_cross_family_impacts(self):
        state = {
            "emotion": {"anxiety": 5},
            "behavioral_disposition": {"decision_readiness": 5},
        }
        scenario = {**self.scenario, "initial_state": state}
        value = appraisal([
            impact(
                "emotion.anxiety",
                feature="pressure",
                span="期限提前了",
            ),
            impact(
                "behavioral_disposition.decision_readiness",
                feature="goal_alignment",
                span="我现在选择第二个方案",
            ),
        ])
        value["event_features"]["pressure"] = 1
        result = DeterministicStateCalibrator(
            scenario, profile="evidence_independent_hysteretic_v3"
        ).calibrate(value, state, {})
        changed = sum(
            item != "similar"
            for family in result["state_delta"].values()
            for item in family.values()
        )
        self.assertEqual(changed, 2)

    def test_v3_rejects_feature_variable_mismatch(self):
        state = {"relationship": {"trust": 5}}
        scenario = {**self.scenario, "initial_state": state}
        result = DeterministicStateCalibrator(
            scenario, profile="evidence_independent_hysteretic_v3"
        ).calibrate(
            appraisal([
                impact(
                    "relationship.trust",
                    feature="cooperation_signal",
                    strength=2,
                    span="我愿意一起讨论",
                )
            ]),
            state,
            {},
        )
        self.assertEqual(
            result["state_delta"]["relationship"]["trust"], "similar"
        )
        self.assertEqual(
            result["calibration"]["state_impacts"][0]["suppressed_by"],
            "feature_variable_mismatch",
        )

    def test_v4_rejects_disclosure_feature_direction_mismatch(self):
        state = {"behavioral_disposition": {"disclosure_willingness": 5}}
        scenario = {**self.scenario, "initial_state": state}
        calibrator = DeterministicStateCalibrator(
            scenario,
            profile="evidence_independent_directional_hysteretic_v4",
        )
        pressure_increase = appraisal([
            impact(
                "behavioral_disposition.disclosure_willingness",
                feature="pressure",
                strength=2,
                span="你也得告诉我你的说法",
                direction="increase",
            )
        ])
        pressure_increase["event_features"]["pressure"] = 1
        result = calibrator.calibrate(pressure_increase, state, {})
        self.assertEqual(
            result["state_delta"]["behavioral_disposition"][
                "disclosure_willingness"
            ],
            "similar",
        )
        self.assertEqual(
            result["calibration"]["state_impacts"][0]["suppressed_by"],
            "feature_direction_mismatch",
        )

        commitment_decrease = appraisal([
            impact(
                "behavioral_disposition.disclosure_willingness",
                feature="commitment_signal",
                strength=2,
                span="我不替你写说明",
                direction="decrease",
            )
        ])
        commitment_decrease["event_features"]["commitment_signal"] = 2
        result = calibrator.calibrate(commitment_decrease, state, {})
        self.assertEqual(
            result["calibration"]["state_impacts"][0]["suppressed_by"],
            "feature_direction_mismatch",
        )

    def test_v4_keeps_subject_aligned_disclosure_commitment(self):
        state = {"behavioral_disposition": {"disclosure_willingness": 5}}
        scenario = {**self.scenario, "initial_state": state}
        value = appraisal([
            impact(
                "behavioral_disposition.disclosure_willingness",
                feature="commitment_signal",
                strength=2,
                span="我会主动写明文件在我手上",
                direction="increase",
            )
        ])
        value["event_features"]["commitment_signal"] = 2
        result = DeterministicStateCalibrator(
            scenario,
            profile="evidence_independent_directional_hysteretic_v4",
        ).calibrate(value, state, {})
        self.assertEqual(
            result["state_delta"]["behavioral_disposition"][
                "disclosure_willingness"
            ],
            "moderate_increase",
        )
        self.assertTrue(
            result["calibration"]["feature_direction_compatibility_enforced"]
        )

    def test_v3_requires_decisive_evidence_beyond_reinforcement_plateau(self):
        initial = {
            "behavioral_disposition": {"cooperation_readiness": 6}
        }
        current = {
            "behavioral_disposition": {"cooperation_readiness": 8}
        }
        scenario = {**self.scenario, "initial_state": initial}
        value = appraisal([
            impact(
                "behavioral_disposition.cooperation_readiness",
                feature="cooperation_signal",
                strength=2,
                span="我继续配合",
            )
        ])
        value["dialogue_diagnostics"] = {
            "substantive_novelty": {"label": "new_position"}
        }
        calibrator = DeterministicStateCalibrator(
            scenario, profile="evidence_independent_hysteretic_v3"
        )
        routine = calibrator.calibrate(value, current, {})
        self.assertEqual(
            routine["state_delta"]["behavioral_disposition"][
                "cooperation_readiness"
            ],
            "similar",
        )
        self.assertEqual(
            routine["calibration"]["state_impacts"][0]["suppressed_by"],
            "reinforcement_plateau_requires_decisive_evidence",
        )
        value["event_features"]["cooperation_signal"] = 2
        decisive = calibrator.calibrate(value, current, {})
        self.assertNotEqual(
            decisive["state_delta"]["behavioral_disposition"][
                "cooperation_readiness"
            ],
            "similar",
        )

    def test_v3_slow_state_accepts_second_independent_consistent_event(self):
        state = {"relationship": {"trust": 5}}
        scenario = {**self.scenario, "initial_state": state}
        calibrator = DeterministicStateCalibrator(
            scenario, profile="evidence_independent_hysteretic_v3"
        )
        first_value = appraisal([
            impact(
                "relationship.trust",
                feature="commitment_signal",
                span="第一项独立履约证据",
            )
        ])
        first_value["event_features"]["commitment_signal"] = 1
        first_value["dialogue_diagnostics"] = {
            "substantive_novelty": {"label": "new_evidence"}
        }
        first = calibrator.calibrate(first_value, state, {})
        self.assertEqual(
            first["state_delta"]["relationship"]["trust"], "similar"
        )
        self.assertEqual(
            first["calibration"]["state_impacts"][0]["suppressed_by"],
            "slow_variable_requires_decisive_or_two_independent_events",
        )

        second_value = appraisal([
            impact(
                "relationship.trust",
                feature="commitment_signal",
                span="第二项独立履约证据",
            )
        ])
        second_value["event_features"]["commitment_signal"] = 1
        second_value["dialogue_diagnostics"] = {
            "substantive_novelty": {"label": "new_evidence"}
        }
        second = calibrator.calibrate(second_value, state, {})
        self.assertEqual(
            second["state_delta"]["relationship"]["trust"], "mild_increase"
        )
        self.assertEqual(
            second["calibration"]["state_impacts"][0][
                "prior_consistent_evidence"
            ],
            1,
        )

    def test_v2_strong_event_allows_three_with_emotion_capped_at_two(self):
        state = {
            "emotion": {"a": 5, "b": 5, "c": 5},
            "relationship": {"trust": 5},
        }
        scenario = {**self.scenario, "initial_state": state}
        value = appraisal([
            impact("emotion.a", strength=2, span="第一项证据"),
            impact("emotion.b", strength=2, span="第二项证据"),
            impact("emotion.c", strength=2, span="第三项证据"),
            impact("relationship.trust", strength=2, span="第四项证据"),
        ])
        value["event_features"]["cooperation_signal"] = 2
        result = DeterministicStateCalibrator(
            scenario, profile="evidence_balanced_v2"
        ).calibrate(value, state, {})
        changed = [
            value
            for family in result["state_delta"].values()
            for value in family.values()
            if value != "similar"
        ]
        self.assertEqual(len(changed), 3)
        self.assertEqual(
            sum(
                value != "similar"
                for value in result["state_delta"]["emotion"].values()
            ),
            2,
        )
        suppressed = {
            item["variable"]: item.get("suppressed_by")
            for item in result["calibration"]["state_impacts"]
        }
        self.assertEqual(
            suppressed["emotion.c"], "dimension_change_budget"
        )

    def test_v2_reuses_neither_evidence_span_nor_correlated_state(self):
        state = {
            "emotion": {"hope": 5},
            "behavioral_disposition": {"resolve": 5},
        }
        scenario = {**self.scenario, "initial_state": state}
        result = DeterministicStateCalibrator(
            scenario, profile="evidence_balanced_v2"
        ).calibrate(
            appraisal([
                impact("emotion.hope", span="同一条证据"),
                impact("behavioral_disposition.resolve", span="同一条证据"),
            ]),
            state,
            {},
        )
        changed = sum(
            value != "similar"
            for family in result["state_delta"].values()
            for value in family.values()
        )
        self.assertEqual(changed, 1)
        self.assertIn(
            "evidence_already_supports_another_change",
            {
                item.get("suppressed_by")
                for item in result["calibration"]["state_impacts"]
            },
        )

    def test_v5_allows_one_event_to_have_distinct_cross_family_effects(self):
        state = {
            "emotion": {"hope": 5},
            "behavioral_disposition": {"cooperation_readiness": 5},
        }
        scenario = {**self.scenario, "initial_state": state}
        result = DeterministicStateCalibrator(
            scenario, profile="evidence_causal_hysteretic_v5"
        ).calibrate(
            appraisal([
                impact("emotion.hope", strength=2, span="同一条可执行新方案"),
                impact(
                    "behavioral_disposition.cooperation_readiness",
                    strength=2,
                    span="同一条可执行新方案",
                ),
            ]),
            state,
            {},
        )
        changed = sum(
            value != "similar"
            for family in result["state_delta"].values()
            for value in family.values()
        )
        self.assertEqual(changed, 2)
        self.assertTrue(
            result["calibration"][
                "shared_evidence_across_distinct_variables_allowed"
            ]
        )

    def test_v6_prefers_equally_strong_decisive_slow_candidate_before_lexical_tie_break(self):
        state = {
            "emotion": {"frustration": 5},
            "behavioral_disposition": {"decision_readiness": 5},
            "relationship": {"trust": 5},
            "consequence_risk": {"goal_failure_risk": 5},
        }
        scenario = {**self.scenario, "initial_state": state}
        value = appraisal([
            impact(
                "behavioral_disposition.decision_readiness",
                feature="commitment_signal", strength=2,
                span="采用当前安排",
            ),
            impact(
                "consequence_risk.goal_failure_risk",
                feature="goal_alignment", strength=2,
                span="采用当前安排", direction="decrease",
            ),
            impact(
                "emotion.frustration",
                feature="cooperation_signal", strength=2,
                span="采用当前安排", direction="decrease",
            ),
            impact(
                "relationship.trust",
                feature="commitment_signal", strength=2,
                span="采用当前安排",
            ),
        ])
        value["event_features"].update({
            "commitment_signal": 2,
            "goal_alignment": 2,
            "cooperation_signal": 2,
        })
        value["dialogue_diagnostics"] = {
            "substantive_novelty": {"label": "new_decision"}
        }
        result = DeterministicStateCalibrator(
            scenario, profile="evidence_causal_slow_priority_hysteretic_v6"
        ).calibrate(value, state, {})
        self.assertEqual(
            result["state_delta"]["relationship"]["trust"],
            "moderate_increase",
        )
        self.assertEqual(
            result["state_delta"]["emotion"]["frustration"], "similar"
        )
        diagnostics = {
            item["variable"]: item for item in result["calibration"]["state_impacts"]
        }
        self.assertEqual(
            diagnostics["emotion.frustration"]["suppressed_by"],
            "event_change_budget",
        )
        self.assertTrue(result["calibration"]["decisive_slow_tie_break"])

    def test_v2_slow_dimension_requires_strong_or_cumulative_evidence(self):
        state = {"relationship": {"trust": 5}}
        scenario = {**self.scenario, "initial_state": state}
        calibrator = DeterministicStateCalibrator(
            scenario, profile="evidence_balanced_v2"
        )
        weak = appraisal([
            impact("relationship.trust", span="新增合作信号")
        ])
        first = calibrator.calibrate(weak, state, {})
        cumulative = calibrator.calibrate(
            weak, {"relationship": {"trust": 6}}, {}
        )
        self.assertEqual(
            first["state_delta"]["relationship"]["trust"], "similar"
        )
        self.assertEqual(
            cumulative["state_delta"]["relationship"]["trust"], "mild_increase"
        )

    def test_fractional_boundary_calibrates_without_key_error(self):
        state = {"relationship": {"trust": 9.5}}
        result = DeterministicStateCalibrator(self.scenario).calibrate(
            appraisal([impact("relationship.trust")]), state, {}
        )
        self.assertEqual(
            result["state_delta"]["relationship"]["trust"],
            "mild_increase",
        )

    def test_strong_persona_sensitive_event_can_expand_state_budget(self):
        scenario = {
            "environment_agent": {
                "persona": {"empathy": 0.9, "patience": 0.9},
            },
        }
        state = {"emotion": {"a": 5, "b": 5, "c": 5}}
        value = appraisal([
            impact(f"emotion.{name}", strength=2)
            for name in ("a", "b", "c")
        ])
        value["event_features"]["cooperation_signal"] = 2
        result = DeterministicStateCalibrator(scenario).calibrate(value, state, {})
        changed = [
            item for item in result["state_delta"]["emotion"].values()
            if item != "similar"
        ]
        self.assertEqual(len(changed), 2)
        self.assertFalse(
            result["calibration"]["state_impacts"][0]["feature_inferred"]
        )

    def test_missing_impact_feature_uses_dominant_feature_for_persona_calibration(self):
        scenario = {
            "environment_agent": {"persona": {"practicality": 0.9}},
        }
        candidate = impact("relationship.trust", strength=2)
        candidate.pop("evidence_feature")
        value = appraisal([candidate])
        value["event_features"]["goal_alignment"] = 2
        result = DeterministicStateCalibrator(scenario).calibrate(
            value, self.state, self.dynamics
        )
        diagnostic = result["calibration"]["state_impacts"][0]
        self.assertEqual(diagnostic["evidence_feature"], "goal_alignment")
        self.assertTrue(diagnostic["feature_inferred"])
        self.assertEqual(diagnostic["persona_sensitivity"], 0.9)
        self.assertEqual(diagnostic["calibrated_level"], 3)

    def test_ledger_keeps_exact_observable_commitments_and_resolves_latest_request(self):
        ledger = initial_ledger("已知背景")
        request_appraisal = appraisal()
        ledger = record_evaluated_action(
            ledger,
            turn_id=1,
            action={"text": "请确认哪一项记录有分歧。"},
            appraisal=request_appraisal,
        )
        self.assertEqual(len(ledger["unresolved_threads"]), 1)
        ledger = record_environment_response(
            ledger,
            turn_id=1,
            response="第三项记录的时间存在分歧，我会先核对原始版本。",
            latest_social_act="request",
        )
        self.assertEqual(ledger["unresolved_threads"], [])
        self.assertEqual(len(ledger["commitments"]), 1)

    def test_discussion_space_is_not_promoted_to_goal_obligation(self):
        ledger = initial_ledger("", "查明稀释过程", ["核对会议通知"])
        self.assertEqual(ledger["discussion_space"], ["核对会议通知"])
        self.assertEqual(
            [item["text"] for item in ledger["goal_threads"]],
            ["查明稀释过程"],
        )

    def test_ledger_keeps_vaguely_deferred_request_open(self):
        ledger = initial_ledger("已知背景", "获得明确答复，并处理责任边界。")
        ledger = record_evaluated_action(
            ledger,
            turn_id=1,
            action={"text": "请现在说明责任边界。"},
            appraisal=appraisal(),
        )
        ledger = record_environment_response(
            ledger,
            turn_id=1,
            response="这件事等下周再谈。",
            latest_social_act="request",
        )
        self.assertEqual(len(ledger["unresolved_threads"]), 1)
        self.assertEqual(
            ledger["unresolved_threads"][0]["response_disposition"], "deferred"
        )
        self.assertEqual(ledger["commitments"], [])

    def test_embedded_whether_clause_is_not_a_reply_obligation(self):
        ledger = record_evaluated_action(
            initial_ledger(),
            turn_id=1,
            action={"text": "接下来60天，我会观察履约是否稳定。"},
            appraisal={**appraisal(), "social_act": "commitment"},
        )
        self.assertEqual(ledger["unresolved_threads"], [])
        ledger = record_environment_response(
            ledger,
            turn_id=1,
            response="我会用行动说明有限信任能否逐步恢复。",
            latest_social_act="commitment",
        )
        self.assertEqual(ledger["unresolved_threads"], [])
        self.assertIsNone(ledger["latest_obligation"])

    def test_direct_whether_question_still_requires_a_reply(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=1,
            response="你是否愿意暂停新的经济往来？",
            latest_social_act="request",
        )
        self.assertEqual(len(ledger["unresolved_threads"]), 1)
        self.assertEqual(ledger["latest_obligation"]["owner"], "evaluated_agent")

    def test_ledger_keeps_promise_pending_until_same_owner_reports_completion(self):
        ledger = initial_ledger("", "形成明确安排")
        ledger = record_environment_response(
            ledger,
            turn_id=1,
            response="我会核对原始记录。",
            latest_social_act="other",
        )
        self.assertEqual(ledger["commitments"][0]["status"], "pending")
        ledger = record_evaluated_action(
            ledger,
            turn_id=2,
            action={"text": "请核对后直接说明分歧。"},
            appraisal=appraisal(),
        )
        self.assertEqual(ledger["commitments"][0]["status"], "pending")
        ledger = record_environment_response(
            ledger,
            turn_id=2,
            response="我已经核对原始记录，第三项时间不同。",
            latest_social_act="request",
        )
        self.assertEqual(
            ledger["commitments"][0]["status"], "reported_complete"
        )

    def test_ledger_tracks_consecutive_practical_focus_deterministically(self):
        ledger = initial_ledger("", "明确还款安排，同时厘清关系边界")
        for turn_id in (1, 2):
            ledger = record_evaluated_action(
                ledger,
                turn_id=turn_id,
                action={"text": "请明确下周还款时间。"},
                appraisal=appraisal(),
            )
            ledger = record_environment_response(
                ledger,
                turn_id=turn_id,
                response="下周工资到账后我会转账。",
                latest_social_act="request",
            )
        self.assertEqual(
            ledger["progress"]["current_focus"], "practical_execution"
        )
        self.assertEqual(
            ledger["progress"]["consecutive_focus_utterances"], 4
        )

    def test_acceptance_is_not_misrecorded_as_owned_execution_commitment(self):
        ledger = record_evaluated_action(
            initial_ledger(),
            turn_id=1,
            action={"text": "这样的安排我接受，25号请你按时转账。"},
            appraisal={**appraisal(), "social_act": "commitment"},
        )
        self.assertEqual(ledger["commitments"], [])

    def test_record_medium_does_not_override_authorization_subject_focus(self):
        self.assertEqual(
            dialogue_focus(
                "系统记录与会议纪要尚未显示任何未经确认的授权环节。"
            ),
            "authorization",
        )
        self.assertEqual(
            dialogue_focus("请调取并发送会议纪要副本。"),
            "artifact_workflow",
        )

    def test_focus_uses_dominant_evidence_not_one_secondary_keyword(self):
        self.assertEqual(
            dialogue_focus(
                "25号转账到账后再谈具体金额，之后我们继续沟通。"
            ),
            "practical_execution",
        )
        self.assertEqual(
            dialogue_focus("反复延期已经伤害信任，也影响我们的朋友关系。"),
            "trust_repair",
        )

    def test_goal_threads_record_touch_by_shared_practical_focus(self):
        ledger = initial_ledger("", "促成明确可执行的还款安排")
        ledger = record_evaluated_action(
            ledger,
            turn_id=1,
            action={"text": "请给一个具体日期和金额。"},
            appraisal=appraisal(),
        )
        self.assertEqual(ledger["goal_threads"][0]["last_mentioned_turn"], "t1")
        self.assertIsNone(ledger["goal_threads"][0]["last_touched_turn"])
        self.assertEqual(ledger["goal_threads"][0]["discussion_rounds"], 0)
        ledger = record_environment_response(
            ledger, turn_id=1, response="首期金额是三千元。", latest_social_act="request"
        )
        for turn_id in range(2, 5):
            ledger = record_evaluated_action(
                ledger,
                turn_id=turn_id,
                action={"text": "还款日期和金额仍是当前议题。"},
                appraisal=appraisal(),
            )
            ledger = record_environment_response(
                ledger,
                turn_id=turn_id,
                response="具体金额仍是三千元。",
                latest_social_act="request",
            )
        self.assertEqual(ledger["goal_threads"][0]["status"], "saturated")
        self.assertEqual(ledger["goal_threads"][0]["discussion_rounds"], 4)

    def test_choice_space_does_not_create_progress_counters(self):
        ledger = initial_ledger("", "", ["经济补偿的多种组合"])
        self.assertEqual(ledger["goal_threads"], [])
        self.assertEqual(ledger["discussion_space"], ["经济补偿的多种组合"])

    def test_multiple_choice_spaces_remain_authored_context(self):
        ledger = initial_ledger(
            "", "", ["逐条解释稀释决策及授权链", "提出治理角色"]
        )
        self.assertEqual(
            ledger["discussion_space"],
            ["逐条解释稀释决策及授权链", "提出治理角色"],
        )

    def test_explicit_goal_is_preserved_and_choice_space_is_not_split(self):
        ledger = initial_ledger(
            "",
            "明确还款安排，同时厘清关系边界。",
            ["核对还款安排和现实困难", "重谈期限与边界"],
        )
        labels = [item["text"] for item in ledger["goal_threads"]]
        self.assertEqual(labels, ["明确还款安排，同时厘清关系边界"])
        self.assertEqual(
            ledger["discussion_space"],
            ["核对还款安排和现实困难", "重谈期限与边界"],
        )

    def test_choice_space_never_receives_goal_progress_counters(self):
        ledger = initial_ledger(
            "", "明确还款安排", ["核对首期金额", "了解现实困难"]
        )
        ledger = record_evaluated_action(
            ledger,
            turn_id=1,
            action={"text": "请说明第一期能还多少金额。"},
            appraisal=appraisal(),
        )
        self.assertEqual(
            [item["text"] for item in ledger["goal_threads"]],
            ["明确还款安排"],
        )
        self.assertEqual(
            ledger["discussion_space"], ["核对首期金额", "了解现实困难"]
        )
        ledger = record_environment_response(
            ledger,
            turn_id=1,
            response="首期金额是三千元。",
            latest_social_act="request",
        )
        self.assertEqual(
            ledger["discussion_space"], ["核对首期金额", "了解现实困难"]
        )

    def test_authored_goal_keeps_full_semantic_scope(self):
        ledger = initial_ledger(
            "",
            "查明稀释过程、争取合理权益，并决定合作关系是否仍可重建",
            ["区分过去伤害、法律权益与未来合作"],
        )
        labels = [item["text"] for item in ledger["goal_threads"]]
        self.assertEqual(
            labels,
            ["查明稀释过程、争取合理权益，并决定合作关系是否仍可重建"],
        )
        self.assertEqual(
            ledger["discussion_space"], ["区分过去伤害、法律权益与未来合作"]
        )

    def test_future_commitment_keeps_latest_request_as_object_context(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=1,
            response="我需要时间整理这些数据，明天会议前我会准备好。",
            latest_social_act="request",
            latest_action="请整理融资授权记录和条款演变。",
        )
        commitment = ledger["commitments"][0]
        self.assertEqual(
            commitment["context"], "请整理融资授权记录和条款演变。"
        )
        self.assertIn("整理这些数据", commitment["object"])

    def test_compound_repayment_and_notice_are_separate_commitments(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=3,
            response=(
                "28天后我预计能还800元，如果情况有变，"
                "我会通过发信息提前一周说明。"
            ),
            latest_social_act="request",
            latest_action="请明确下一笔还款金额和沟通方式。",
        )
        pending = [
            item for item in ledger["commitments"] if item["status"] == "pending"
        ]
        self.assertEqual(len(pending), 2)
        by_focus = {item["focus"]: item for item in pending}
        self.assertIn("800元", by_focus["practical_execution"]["object"])
        self.assertIn("28天后", by_focus["practical_execution"]["terms"])
        self.assertIn("提前一周说明", by_focus["communication_boundary"]["object"])

    def test_current_capacity_statement_is_a_repayment_commitment(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=1,
            response=(
                "我这14天内先还500元，这个数额目前能确定；如果有变，"
                "我会提前3天说明。"
            ),
            latest_social_act="request",
        )
        by_focus = {item["focus"]: item for item in ledger["commitments"]}
        self.assertIn("500元", by_focus["practical_execution"]["object"])
        self.assertIn("14天内", by_focus["practical_execution"]["terms"])
        self.assertIn("提前3天说明", by_focus["communication_boundary"]["object"])

    def test_maximum_capacity_statement_keeps_preceding_deadline(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=3,
            response=(
                "接下来28天内，我最多能确定还500元，"
                "并会提前说明任何可能的变化。"
            ),
            latest_social_act="request",
        )
        repayment = next(
            item for item in ledger["commitments"]
            if item["focus"] == "practical_execution"
        )
        self.assertIn("500元", repayment["object"])
        self.assertIn("28天内", repayment["terms"])

    def test_firm_transfer_out_language_is_a_practical_repayment_commitment(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=2,
            response=(
                "14天内我会确保500元能按时转出，如果有任何阻碍，"
                "我一定会提前和你沟通。"
            ),
            latest_social_act="request",
        )
        practical = [
            item for item in ledger["commitments"]
            if item["focus"] == "practical_execution"
        ]
        self.assertEqual(len(practical), 1)
        self.assertIn("500元", practical[0]["object"])

    def test_conditional_confirmation_does_not_perform_pending_commitment(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=6,
            response="我会确认其他合伙人的权益情况。",
            latest_social_act="request",
        )
        ledger = record_environment_response(
            ledger,
            turn_id=7,
            response="如果条款没有保障，我们可以先确认其他合伙人的意见，再评估下一步。",
            latest_social_act="request",
        )
        self.assertEqual(ledger["commitments"][0]["status"], "pending")

    def test_immediate_can_confirm_is_not_a_future_commitment(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=1,
            response="我可以确认：目前你只能表达意见。",
            latest_social_act="request",
        )
        self.assertEqual(ledger["commitments"], [])
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=1,
            response="我可以提供文件副本。",
            latest_social_act="request",
        )
        self.assertEqual(len(ledger["commitments"]), 1)

    def test_same_focus_commitment_restatement_is_folded_into_pending_entry(self):
        ledger = initial_ledger("", "明确还款安排")
        ledger = record_environment_response(
            ledger,
            turn_id=1,
            response="我会在下个月底先还两成。",
            latest_social_act="other",
        )
        ledger = record_environment_response(
            ledger,
            turn_id=2,
            response="我会按计划在下个月底先还两成。",
            latest_social_act="other",
        )
        pending = [item for item in ledger["commitments"] if item["status"] == "pending"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(len(pending[0]["restatements"]), 1)

    def test_same_focus_commitment_with_new_term_becomes_refinement(self):
        ledger = initial_ledger("", "明确还款安排")
        ledger = record_environment_response(
            ledger,
            turn_id=1,
            response="我会在下个月底先还两成。",
            latest_social_act="other",
        )
        ledger = record_environment_response(
            ledger,
            turn_id=2,
            response="我会在下个月底先还两成，之后每月分期。",
            latest_social_act="other",
        )
        self.assertEqual(
            [item["status"] for item in ledger["commitments"]],
            ["refined", "pending"],
        )

    def test_distinct_same_focus_commitments_remain_separate(self):
        ledger = initial_ledger("", "争取合理权益")
        ledger = record_evaluated_action(
            ledger,
            turn_id=1,
            action={"text": "我将要求暂停本轮稀释方案。"},
            appraisal={**appraisal(), "social_act": "commitment"},
        )
        ledger = record_evaluated_action(
            ledger,
            turn_id=2,
            action={"text": "如果席位无法保障，我将不再参与后续融资谈判。"},
            appraisal={**appraisal(), "social_act": "commitment"},
        )
        self.assertEqual(
            [item["status"] for item in ledger["commitments"]],
            ["pending", "pending"],
        )

    def test_repromising_artifact_is_not_marked_performed(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=1,
            response="我会整理授权记录，稍后提供。",
            latest_social_act="request",
        )
        ledger = record_environment_response(
            ledger,
            turn_id=2,
            response="好的，我今天会先梳理授权记录，再联系你。",
            latest_social_act="other",
        )
        self.assertEqual(ledger["commitments"][0]["status"], "pending")

    def test_artifact_promise_is_not_completed_by_later_question(self):
        ledger = record_evaluated_action(
            initial_ledger(),
            turn_id=1,
            action={"text": "我先整理书面记录，再一起核对关键条款。"},
            appraisal={**appraisal(), "social_act": "commitment"},
        )
        ledger = record_evaluated_action(
            ledger,
            turn_id=2,
            action={"text": "过去几次融资为什么没有邀请我参加？"},
            appraisal={**appraisal(), "social_act": "question"},
        )
        self.assertEqual(ledger["commitments"][0]["status"], "pending")

    def test_conditional_acceptance_is_disposition_not_pending_action(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=1,
            response="我可以接受你保留否决权，但需绑定季度审核。",
            latest_social_act="proposal",
            latest_action="我接受你提出的治理方案。",
        )
        self.assertFalse(ledger["commitments"])
        ledger = record_environment_response(
            ledger,
            turn_id=2,
            response="方案今天会发给你。",
            latest_social_act="other",
        )
        self.assertFalse(ledger["commitments"])

    def test_secondary_surface_request_creates_obligation_despite_primary_label(self):
        ledger = record_evaluated_action(
            initial_ledger(),
            turn_id=1,
            action={"text": "我接受这些条款。请立即发送草案。"},
            appraisal={**appraisal(), "social_act": "commitment"},
        )
        self.assertEqual(len(ledger["unresolved_threads"]), 1)
        self.assertEqual(ledger["latest_obligation"]["owner"], "environment_agent")
        ledger = record_environment_response(
            ledger,
            turn_id=1,
            response="草案目前不能提供，因为内容还没有形成。",
            latest_social_act="commitment",
        )
        self.assertEqual(ledger["unresolved_threads"], [])

    def test_plain_request_is_not_added_as_active_proposal(self):
        ledger = record_evaluated_action(
            initial_ledger(),
            turn_id=1,
            action={"text": "请说明草案何时能提供。"},
            appraisal={**appraisal(), "social_act": "request"},
        )
        self.assertEqual(ledger["active_proposals"], [])
        self.assertEqual(len(ledger["unresolved_threads"]), 1)

    def test_spoken_proposal_fulfills_owned_promise_to_propose(self):
        ledger = initial_ledger("", "争取合理权益")
        ledger = record_evaluated_action(
            ledger,
            turn_id=1,
            action={"text": "我将基于早期贡献提出治理和权益方案。"},
            appraisal={**appraisal(), "social_act": "commitment"},
        )
        ledger = record_evaluated_action(
            ledger,
            turn_id=2,
            action={"text": "我建议设置一个创始贡献席位，并讨论股权补偿。"},
            appraisal={**appraisal(), "social_act": "proposal"},
        )
        self.assertEqual(
            ledger["commitments"][0]["status"], "performed_in_dialogue"
        )

    def test_repeating_communication_rule_does_not_fulfill_it(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=1,
            response="如果情况有变，我会在三天内说明。",
            latest_social_act="request",
            latest_action="有变化时请及时说明。",
        )
        self.assertEqual(ledger["commitments"][0]["status"], "pending")
        ledger = record_environment_response(
            ledger,
            turn_id=2,
            response="我们仍按三天内说明的规则沟通。",
            latest_social_act="other",
            latest_action="这个沟通规则不变。",
        )
        self.assertEqual(ledger["commitments"][0]["status"], "pending")

    def test_embedded_whether_proposition_does_not_create_reply_obligation(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=1,
            response=(
                "我们把‘友谊是否意味着必须承担经济责任’这个分歧暂时保留，"
                "作为相处中需要留意的边界。"
            ),
            latest_social_act="statement",
            latest_action="这个分歧先保留。",
        )
        self.assertIsNone(ledger["latest_obligation"])
        direct = record_environment_response(
            initial_ledger(),
            turn_id=1,
            response="我想知道你是否接受这个边界。",
            latest_social_act="question",
            latest_action="请说你的意见。",
        )
        self.assertEqual(
            direct["latest_obligation"]["owner"], "evaluated_agent"
        )

    def test_environment_directly_resolves_current_proposal_thread(self):
        ledger = initial_ledger()
        ledger = record_evaluated_action(
            ledger,
            turn_id=1,
            action={"text": "我提议保留客观的早期角色描述。"},
            appraisal={**appraisal(), "social_act": "proposal"},
        )
        self.assertEqual(len(ledger["unresolved_threads"]), 1)
        ledger = record_environment_response(
            ledger,
            turn_id=1,
            response="我同意保留客观描述，不附加象征性头衔。",
            latest_social_act="proposal",
        )
        self.assertEqual(ledger["unresolved_threads"], [])

    def test_rights_answer_is_classified_as_direct_not_deferred(self):
        ledger = initial_ledger()
        ledger = record_evaluated_action(
            ledger,
            turn_id=1,
            action={"text": "该份额是否具备反稀释保护？"},
            appraisal={**appraisal(), "social_act": "question"},
        )
        ledger = record_environment_response(
            ledger,
            turn_id=1,
            response="该份额不具备反稀释保护。",
            latest_social_act="question",
        )
        self.assertEqual(ledger["unresolved_threads"], [])

    def test_new_same_focus_request_supersedes_stale_variant(self):
        ledger = initial_ledger()
        for turn_id, text in enumerate((
            "什么时候可以还款？",
            "请明确还款日期。",
        ), start=1):
            ledger = record_evaluated_action(
                ledger,
                turn_id=turn_id,
                action={"text": text},
                appraisal=appraisal(),
            )
        waiting = [
            item for item in ledger["unresolved_threads"]
            if item.get("speaker") == "evaluated_agent"
        ]
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0]["turn_id"], "t2")

    def test_environment_explicit_request_without_question_mark_creates_obligation(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=5,
            response="请列出具体内容，我将同步提供对应融资阶段的股权分配记录。",
            latest_social_act="response",
        )
        self.assertEqual(
            ledger["latest_obligation"]["owner"], "evaluated_agent"
        )

    def test_counterparty_reply_clears_stale_question_and_proposal(self):
        ledger = initial_ledger()
        ledger = record_environment_response(
            ledger,
            turn_id=1,
            response="要不要先暂停新的经济往来？",
            latest_social_act="other",
        )
        self.assertEqual(ledger["latest_obligation"]["owner"], "evaluated_agent")
        self.assertTrue(ledger["active_proposals"])
        ledger = record_evaluated_action(
            ledger,
            turn_id=2,
            action={"text": "可以，我同意暂停新的经济往来。"},
            appraisal={**appraisal(), "social_act": "concession"},
        )
        self.assertEqual(ledger["unresolved_threads"], [])
        self.assertEqual(ledger["active_proposals"], [])
        self.assertIsNone(ledger["latest_obligation"])

    def test_paraphrase_precheck_rejects_added_urgency(self):
        result = strict_paraphrase_precheck("把记录发我确认。", "赶紧把记录发我核对。")
        self.assertFalse(result["passed"])
        self.assertIn("urgency_strength_changed", result["reasons"])

    def test_paraphrase_precheck_ignores_ordered_list_labels_only(self):
        original = "1. 明确目标\n2. 公平分工"
        paraphrase = "一是明确目标，二是公平分工"
        self.assertTrue(strict_paraphrase_precheck(original, paraphrase)["passed"])
        changed_fact = strict_paraphrase_precheck(
            "误差必须低于5%。", "误差必须低于10%。"
        )
        self.assertFalse(changed_fact["passed"])
        self.assertIn("numeric_content_changed", changed_fact["reasons"])

    def test_transition_metrics_distinguish_zero_mismatch_from_reversal(self):
        left = {
            "numeric_state_delta": {"emotion": {"anger": 0, "hope": 1}},
            "numeric_dynamics_delta": {"negotiation_open": 1},
        }
        right = {
            "numeric_state_delta": {"emotion": {"anger": -1, "hope": -1}},
            "numeric_dynamics_delta": {"negotiation_open": 0},
        }
        metrics = compare_transition_outputs(left, right)["overall"]
        self.assertEqual(metrics["exact_direction_agreement"], 0.0)
        self.assertAlmostEqual(metrics["change_no_change_agreement"], 1 / 3, places=4)
        self.assertAlmostEqual(metrics["true_sign_reversal_rate"], 1 / 3, places=4)
        self.assertAlmostEqual(metrics["mean_ordinal_delta_distance"], 4 / 3, places=4)


if __name__ == "__main__":
    unittest.main()
