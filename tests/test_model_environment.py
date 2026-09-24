import json
import unittest
from pathlib import Path
from unittest.mock import patch

from environment.appraisal import ModelAppraiser, _validate_appraisal
from environment.calibration import DeterministicStateCalibrator
from environment.env import StatefulEnvironment
from environment.factory import ModelEnvironmentFactory
from environment.response_generator import ModelResponseGenerator
from environment.state_updater import ModelStateUpdater, canonicalize_bounded_transition


SCENARIO = json.loads(
    Path("data/gpt50/experiment/scenario/scenarios/scenario_001/scenario_001.json").read_text(encoding="utf-8")
)


def _structured_appraisal(evidence=None):
    return {
        "appraisal": {
            "speaker_intent": "核对事实并推进讨论",
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
            "state_impacts": [{
                "variable": "relationship.trust",
                "direction": "increase",
                "evidence_feature": "cooperation_signal",
                "evidence_strength": 1,
                "directness": "direct",
                "new_evidence": True,
            }],
            "dynamics_impacts": [{
                "variable": "negotiation_open",
                "direction": "increase",
                "evidence_feature": "goal_alignment",
                "evidence_strength": 1,
                "directness": "direct",
                "new_evidence": True,
            }],
            "ledger_events": [],
            "ledger_resolutions": [],
        },
        "evidence_turn_ids": list(evidence or []),
    }


def _structured_response(response_text, ledger_events=None, *, reply_obligation=None, consequential_claims=None):
    events = []
    for item in ledger_events or []:
        event = dict(item)
        event.setdefault("assertion_mode", "asserted")
        events.append(event)
    if reply_obligation is None and any(
        item.get("event_type") == "request"
        and item.get("action_owner") == "evaluated_agent"
        and item.get("assertion_mode") == "asserted"
        for item in events
    ):
        reply_obligation = "evaluated_agent"
    return {
        "response_text": response_text,
        "expression_intent": "直接回应当前问题",
        "observable_behavior": {
            "facial_expression": "平静",
            "gaze": "看向对方",
            "speech_style": "直接",
            "prosody": "平稳",
            "behavioral_cues": [],
        },
        "ledger_events": events,
        "reply_obligation": reply_obligation,
        "consequential_claims": list(consequential_claims or []),
    }


class SequencedProvider:
    provenance = {"provider": "test-double", "model": "sequenced"}

    def __init__(self, include_response=False):
        self.calls = []
        self.include_response = include_response

    def complete(self, messages, **generation):
        self.calls.append(next(item["content"] for item in messages if item["role"] == "user"))
        if len(self.calls) == 1:
            value = _structured_appraisal()
            if "Structured Appraisal v11" in self.calls[0]:
                action = self.calls[0].rstrip().rsplit("\n\n", 1)[-1]
                value["appraisal"]["dialogue_diagnostics"] = {
                    "substantive_novelty": {
                        "label": "new_position", "evidence_span": action,
                    },
                    "consequential_claims": [],
                    "continuation": {
                        "status": "must_answer",
                        "evidence_span": action,
                        "after_direct_response": {
                            "status": "can_close", "evidence_span": action,
                            "resolved_live_questions": [],
                            "remaining_live_questions": [],
                        },
                    },
                }
            return json.dumps(value, ensure_ascii=False)
        if self.include_response:
            return json.dumps(_structured_response(
                "可以，我们先把双方记录中不一致的部分逐项核对。"
            ), ensure_ascii=False)
        raise AssertionError("deterministic calibration must not call the provider")


class ModelEnvironmentBoundaryTest(unittest.TestCase):
    def test_appraiser_honors_provider_route_output_budget(self):
        provider = SequencedProvider()
        provider.generation_defaults = {"max_tokens": 900}
        appraiser = ModelAppraiser(
            SCENARIO,
            provider,
            {"temperature": 0.2},
            "environment_appraisal_v11",
        )
        self.assertEqual(appraiser.sampling["max_tokens"], 900)

    def test_appraiser_uses_legacy_default_without_route_budget(self):
        appraiser = ModelAppraiser(
            SCENARIO,
            SequencedProvider(),
            {"temperature": 0.2},
        )
        self.assertEqual(appraiser.sampling["max_tokens"], 2800)

    def test_structured_response_preserves_semantic_request_without_question_marker(self):
        generator = ModelResponseGenerator(
            SequencedProvider(),
            prompt_id="environment_response_v25",
            validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        response = "你先列出清单后，我们再逐项确认。"
        normalized = generator._validate_structured_response(
            _structured_response(response, [{
                "event_type": "request",
                "owner": "environment_agent",
                "action_owner": "evaluated_agent",
                "evidence_span": "你先列出清单后",
                "status": "open",
            }]),
            {
                "scenario": SCENARIO,
                "action": {"text": "我愿意先整理自己的部分。"},
                "history": [],
                "interaction_ledger": {},
                "longitudinal_context": {},
                "turn_id": 1,
            },
        )
        self.assertEqual(len(normalized["ledger_events"]), 1)
        self.assertEqual(normalized["ledger_events"][0]["event_type"], "request")
        self.assertEqual(
            normalized["ledger_events"][0]["action_owner"], "evaluated_agent"
        )

    def test_structured_response_rejects_reply_obligation_without_request_event(self):
        generator = ModelResponseGenerator(
            SequencedProvider(),
            prompt_id="environment_response_v25",
            validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        response = (
            "我会配合确认数据调取权限，但需要你方同步提供协作流程的具体要求。"
        )
        with self.assertRaisesRegex(ValueError, "disagree"):
            generator._validate_structured_response(
                _structured_response(response, [{
                    "event_type": "commitment",
                    "owner": "environment_agent",
                    "action_owner": "environment_agent",
                    "evidence_span": "我会配合确认数据调取权限",
                    "status": "firm",
                }], reply_obligation="evaluated_agent"),
                {
                    "scenario": SCENARIO,
                    "action": {"text": "三日内可以启动，但需先确认权限。"},
                    "history": [],
                    "interaction_ledger": {},
                    "longitudinal_context": {},
                    "turn_id": 3,
                },
            )

    def test_structured_response_drops_claim_and_boundary_ledger_noise(self):
        generator = ModelResponseGenerator(
            SequencedProvider(),
            prompt_id="environment_response_v25",
            validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        response = "我接受继续做普通朋友，但日常交往不再围绕这笔债展开。"
        normalized = generator._validate_structured_response(
            _structured_response(response, [{
                "event_type": "claim",
                "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": "我接受继续做普通朋友",
                "status": "reported",
            }, {
                "event_type": "boundary",
                "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": "日常交往不再围绕这笔债展开",
                "status": "explicit",
            }]),
            {
                "scenario": SCENARIO,
                "action": {"text": "我们继续做普通朋友，但把债务单独处理。"},
                "history": [],
                "interaction_ledger": {},
                "longitudinal_context": {},
                "turn_id": 8,
            },
        )
        self.assertEqual(
            [item["event_type"] for item in normalized["ledger_events"]], ["claim"]
        )
        self.assertEqual(
            [item["operation"] for item in normalized["ledger_event_normalizations"]],
            ["drop_unsupported_ledger_event"],
        )

    def test_top_level_dialogue_diagnostics_schema_variation_is_normalized(self):
        action = "我现在只确认这个安排。"
        value = _structured_appraisal()
        value["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_decision", "evidence_span": action,
            },
            "consequential_claims": [],
            "continuation": {"status": "continue", "evidence_span": action},
        }
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
        )
        self.assertNotIn("dialogue_diagnostics", normalized)
        self.assertEqual(
            normalized["appraisal"]["dialogue_diagnostics"]
            ["substantive_novelty"]["label"],
            "new_decision",
        )

    def test_new_proposal_novelty_alias_is_schema_normalized(self):
        action = "我们可以根据贡献度讨论一个双方认可的署名方案。"
        value = _structured_appraisal()
        value["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_proposal", "evidence_span": action,
            },
            "consequential_claims": [],
            "continuation": {"status": "continue", "evidence_span": action},
        }
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
        )
        self.assertEqual(
            normalized["appraisal"]["dialogue_diagnostics"]
            ["substantive_novelty"]["label"],
            "new_position",
        )

    def test_consequential_claim_span_alias_is_schema_normalized(self):
        action = "旧账责任不变。"
        value = _structured_appraisal()
        value["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "necessary_confirmation", "evidence_span": action,
            },
            "consequential_claims": [{
                "span": "旧账责任不变",
                "impact_domains": ["responsibility"],
                "grounding": "observable_fact",
            }],
            "continuation": {"status": "continue", "evidence_span": action},
        }
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
        )
        claim = normalized["appraisal"]["dialogue_diagnostics"]["consequential_claims"][0]
        self.assertEqual(claim["claim_span"], "旧账责任不变")
        self.assertNotIn("span", claim)

        evidence_alias = _structured_appraisal()
        evidence_alias["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "necessary_confirmation", "evidence_span": action,
            },
            "consequential_claims": [{
                "evidence_span": "旧账责任不变",
                "impact_domains": ["responsibility"],
                "grounding": "observable_fact",
            }],
            "continuation": {"status": "continue", "evidence_span": action},
        }
        evidence_claim = _validate_appraisal(
            evidence_alias, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
        )["appraisal"]["dialogue_diagnostics"]["consequential_claims"][0]
        self.assertEqual(evidence_claim["claim_span"], "旧账责任不变")
        self.assertNotIn("evidence_span", evidence_claim)

        list_grounding = _structured_appraisal()
        list_grounding["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_tradeoff", "evidence_span": action,
            },
            "consequential_claims": [{
                "claim_span": "旧账责任不变",
                "impact_domains": ["responsibility"],
                "grounding": ["observable_fact"],
            }],
            "continuation": {"status": "continue", "evidence_span": action},
        }
        list_claim = _validate_appraisal(
            list_grounding, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
        )["appraisal"]["dialogue_diagnostics"]["consequential_claims"][0]
        self.assertEqual(list_claim["grounding"], "observable_fact")

    def test_appraisal_accepts_unverified_first_person_speaker_report(self):
        action = "我昨天发过文件。"
        value = _structured_appraisal()
        value["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_evidence", "evidence_span": action,
            },
            "consequential_claims": [{
                "claim_span": "我昨天发过文件",
                "impact_domains": ["action_feasibility"],
                "grounding": "speaker_report",
            }],
            "continuation": {"status": "continue", "evidence_span": action},
        }
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
        )
        claim = normalized["appraisal"]["dialogue_diagnostics"][
            "consequential_claims"
        ][0]
        self.assertEqual(claim["grounding"], "speaker_report")

    def test_appraisal_resolution_binds_an_active_counterparty_proposal_id(self):
        action = "我接受第一个方案。"
        value = _structured_appraisal()
        value["appraisal"]["ledger_resolutions"] = [{
            "target_id": "proposal:1",
            "resolution": "accepted",
            "evidence_span": "我接受第一个方案",
        }]
        active = [{
            "id": "proposal:1", "speaker": "environment_agent",
            "status": "open", "text": "第一个方案",
        }]
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, active_proposals=active,
        )
        self.assertEqual(
            normalized["appraisal"]["ledger_resolutions"][0]["target_id"],
            "proposal:1",
        )
        value["appraisal"]["ledger_resolutions"][0]["target_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "not an active proposal"):
            _validate_appraisal(
                value, [], {"relationship.trust"}, {"negotiation_open"},
                action_text=action, active_proposals=active,
            )

    def test_internally_inconsistent_firm_commitment_is_not_entered_in_ledger(self):
        action = "今天先谈到这里，旧账责任不变。"
        value = _structured_appraisal()
        value["appraisal"]["social_act"] = "pause"
        value["appraisal"]["event_features"]["commitment_signal"] = 0
        value["appraisal"]["ledger_events"] = [
            {"event_type": "pause", "owner": "evaluated_agent", "action_owner": "evaluated_agent",
             "evidence_span": "今天先谈到这里", "status": "explicit"},
            {"event_type": "commitment", "owner": "evaluated_agent", "action_owner": "evaluated_agent",
             "evidence_span": "旧账责任不变", "status": "firm"},
        ]
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_ledger_events=True,
        )["appraisal"]
        self.assertEqual(
            [event["event_type"] for event in normalized["ledger_events"]],
            ["pause"],
        )
        self.assertEqual(
            normalized["ledger_event_normalizations"][0]["operation"],
            "drop_internally_inconsistent_commitment",
        )

    def test_appraisal_requires_grounded_evaluated_agent_ledger_events(self):
        action = "你能在14天内还多少？"
        value = _structured_appraisal()
        value["appraisal"]["ledger_events"] = [{
            "event_type": "request", "owner": "evaluated_agent", "action_owner": "environment_agent",
            "evidence_span": action, "status": "open",
        }]
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_ledger_events=True,
        )
        self.assertEqual(
            normalized["appraisal"]["ledger_events"][0]["owner"],
            "evaluated_agent",
        )
        value["appraisal"]["ledger_events"][0]["owner"] = "environment_agent"
        with self.assertRaisesRegex(ValueError, "owner"):
            _validate_appraisal(
                value, [], {"relationship.trust"}, {"negotiation_open"},
                action_text=action, require_ledger_events=True,
            )

    def test_v11_and_v25_make_two_separate_calls(self):
        class StructuredTwoStageProvider:
            provenance = {"provider": "test-double", "model": "structured-two-stage"}

            def __init__(self):
                self.calls = []

            def complete(self, messages, **generation):
                prompt = next(item["content"] for item in messages if item["role"] == "user")
                self.calls.append(prompt)
                if "Structured Appraisal v11" in prompt:
                    action = "你能在14天内还多少？"
                    value = _structured_appraisal()
                    value["appraisal"]["ledger_events"] = [{
                        "event_type": "request", "owner": "evaluated_agent", "action_owner": "environment_agent",
                        "evidence_span": action, "status": "open",
                        "assertion_mode": "asserted",
                    }]
                    value["appraisal"]["dialogue_diagnostics"] = {
                        "substantive_novelty": {
                            "label": "new_position", "evidence_span": action,
                        },
                        "consequential_claims": [],
                        "continuation": {
                            "status": "must_answer", "evidence_span": action,
                            "after_direct_response": {
                                "status": "can_close", "evidence_span": action,
                                "resolved_live_questions": [],
                                "remaining_live_questions": [],
                            },
                        },
                    }
                    return json.dumps(value, ensure_ascii=False)
                return json.dumps(_structured_response(
                    "我会在14天内还800元。",
                    [{
                        "event_type": "commitment", "owner": "environment_agent", "action_owner": "environment_agent",
                        "evidence_span": "我会在14天内还800元。", "status": "firm",
                    }],
                    consequential_claims=[{
                        "claim_span": "800元",
                        "impact_domains": ["action_feasibility"],
                        "grounding": "proposal_or_hypothetical",
                    }],
                ), ensure_ascii=False)

        provider = StructuredTwoStageProvider()
        environment = StatefulEnvironment(
            SCENARIO,
            state_updater=ModelStateUpdater(
                SCENARIO, provider, {"temperature": 0},
                appraiser=__import__("environment.appraisal", fromlist=["ModelAppraiser"])
                .ModelAppraiser(SCENARIO, provider, {"temperature": 0}, "environment_appraisal_v11"),
            ),
            response_generator=ModelResponseGenerator(
                provider, {"temperature": 0}, "environment_response_v25",
                validation_profile="hard_only", horizon_mode="natural_max_20",
            ),
            minimum_natural_turns=10,
        )
        environment.reset("semantic-two-call")
        _, turn = environment.step({"text": "你能在14天内还多少？"})
        self.assertEqual(len(provider.calls), 2)
        self.assertIn("Structured Appraisal v11", provider.calls[0])
        self.assertIn("State-Conditioned Response v25", provider.calls[1])
        self.assertEqual(turn["environment_response"], "我会在14天内还800元。")
        self.assertEqual(environment.session["turn_id"], 1)
        self.assertEqual(environment.session["status"], "active")
        self.assertEqual(
            turn["interaction_ledger_after"]["commitments"][0]["amounts"],
            [800.0],
        )
    def test_semantic_delta_matches_bounded_numeric_effect(self):
        transition = {
            "appraisal": {},
            "evidence_turn_ids": [],
            "state_delta": {
                "at_ceiling": "strong_increase",
                "near_floor": "strong_decrease",
                "fractional_ceiling": "strong_increase",
            },
            "interaction_dynamics_delta": {
                "near_ceiling": "moderate_increase",
                "fractional_step": "mild_increase",
            },
        }
        normalized = canonicalize_bounded_transition(
            transition,
            {"at_ceiling": 10, "near_floor": 1, "fractional_ceiling": 8.5},
            {"near_ceiling": 9, "fractional_step": 9.5},
        )
        self.assertEqual(normalized["state_delta"]["at_ceiling"], "similar")
        self.assertEqual(normalized["state_delta"]["near_floor"], "mild_decrease")
        self.assertEqual(
            normalized["interaction_dynamics_delta"]["near_ceiling"],
            "mild_increase",
        )
        self.assertEqual(
            normalized["state_delta"]["fractional_ceiling"],
            "moderate_increase",
        )
        self.assertEqual(
            normalized["interaction_dynamics_delta"]["fractional_step"],
            "mild_increase",
        )

    def test_semantic_none_deterministically_suppresses_numeric_update(self):
        appraisal = _structured_appraisal()["appraisal"]
        appraisal["dialogue_diagnostics"] = {
            "substantive_novelty": {"label": "none", "evidence_span": ""},
            "consequential_claims": [],
            "continuation": {"status": "can_close", "evidence_span": ""},
        }
        result = DeterministicStateCalibrator(SCENARIO).calibrate(
            appraisal, SCENARIO["initial_state"], SCENARIO["initial_dynamics"]
        )
        self.assertTrue(result["calibration"]["semantic_no_change_enforced"])
        self.assertTrue(all(
            value == "similar"
            for group in result["state_delta"].values()
            for value in group.values()
        ))
        self.assertTrue(all(
            value == "similar"
            for value in result["interaction_dynamics_delta"].values()
        ))

    def test_exact_same_speaker_duplicate_overrides_false_model_novelty(self):
        appraisal = _structured_appraisal()["appraisal"]
        appraisal["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_position", "evidence_span": "我确认现有安排。"
            },
            "consequential_claims": [],
            "continuation": {
                "status": "continue", "evidence_span": "我确认现有安排。"
            },
        }
        result = DeterministicStateCalibrator(SCENARIO).calibrate(
            appraisal, SCENARIO["initial_state"], SCENARIO["initial_dynamics"],
            surface_duplicate_evidence_ids=["t3"],
        )
        self.assertTrue(result["calibration"]["semantic_no_change_enforced"])
        self.assertEqual(
            result["calibration"]["surface_duplicate_evidence_ids"], ["t3"]
        )
        self.assertEqual(result["state_delta"]["relationship"]["trust"], "similar")
        self.assertEqual(
            next(iter(result["interaction_dynamics_delta"].values())), "similar"
        )

    def test_state_update_uses_one_appraisal_call_then_deterministic_calibration(self):
        provider = SequencedProvider()
        updater = ModelStateUpdater(SCENARIO, provider, {"temperature": 0})
        transition = updater.update(
            action={"text": "我想先核对双方记录。"},
            previous_state=SCENARIO["initial_state"],
            previous_dynamics=SCENARIO["initial_dynamics"],
            memory={"relevant_turn_ids": [], "events": []},
        )
        self.assertEqual(len(provider.calls), 1)
        self.assertIn("environment LLM call 1", provider.calls[0])
        self.assertIn(
            SCENARIO["narrative_design"]["relevant_history"][0],
            provider.calls[0],
        )
        self.assertEqual(transition["state_delta"]["relationship"]["trust"], "mild_increase")
        self.assertEqual(transition["state_delta"]["emotion"]["anxiety"], "similar")
        self.assertEqual(
            transition["calibration"]["implementation"], "deterministic_python"
        )

    def test_complete_step_has_exactly_two_separate_model_calls(self):
        provider = SequencedProvider(include_response=True)
        environment = StatefulEnvironment(
            SCENARIO,
            state_updater=ModelStateUpdater(SCENARIO, provider, {"temperature": 0}),
            response_generator=ModelResponseGenerator(provider, {"temperature": 0}),
        )
        environment.reset("two-call-test")
        _, turn = environment.step({"text": "我想先核对双方记录。"})
        self.assertEqual(len(provider.calls), 2)
        self.assertIn("Structured Appraisal v11", provider.calls[0])
        self.assertNotIn("State-Conditioned Response v25", provider.calls[0])
        self.assertIn("State-Conditioned Response v25", provider.calls[1])
        self.assertIn('"interaction_ledger"', provider.calls[1])
        self.assertEqual(turn["numeric_state_delta"]["relationship"]["trust"], 1)
        self.assertEqual(turn["environment_response"], "可以，我们先把双方记录中不一致的部分逐项核对。")

    def test_factory_can_use_distinct_appraisal_and_response_providers(self):
        appraisal_provider = SequencedProvider()

        class ResponseOnlyProvider:
            provenance = {"provider": "test-double", "model": "response-only"}

            def __init__(self):
                self.calls = []

            def complete(self, messages, **generation):
                self.calls.append(next(item["content"] for item in messages if item["role"] == "user"))
                return json.dumps(_structured_response(
                    "可以，我们现在只回答最新的问题。"
                ), ensure_ascii=False)

        response_provider = ResponseOnlyProvider()
        with patch(
            "environment.factory.build_provider",
            side_effect=[appraisal_provider, response_provider],
        ):
            factory = ModelEnvironmentFactory(
                SCENARIO,
                {"provider": "local_vllm", "model": "appraisal"},
                {"temperature": 0},
                response_provider_config={
                    "provider": "local_vllm", "model": "response"
                },
                response_sampling={"temperature": 0.4},
                minimum_natural_turns=10,
            )
            environment = factory()
            environment.reset("split-provider-test")
            environment.step({"text": "我想先核对双方记录。"})
        self.assertEqual(len(appraisal_provider.calls), 1)
        self.assertEqual(len(response_provider.calls), 1)
        self.assertIn("Structured Appraisal v11", appraisal_provider.calls[0])
        self.assertIn("State-Conditioned Response v25", response_provider.calls[0])
        self.assertTrue(factory.provenance["calls_are_separate"])
        self.assertEqual(factory.provenance["llm_calls_per_step"], 2)
        self.assertEqual(factory.provenance["llm_stage_count_per_step"], 2)
        self.assertEqual(
            factory.provenance["nominal_llm_calls_per_step_without_retries"], 2
        )
        self.assertTrue(factory.provenance["actual_requests_may_exceed_nominal"])
        self.assertEqual(factory.provenance["appraisal_provider"]["model"], "appraisal")
        self.assertEqual(factory.provenance["response_provider"]["model"], "response")
        self.assertEqual(factory.provenance["minimum_natural_turns"], 10)
        self.assertEqual(environment.minimum_natural_turns, 10)
        self.assertEqual(
            environment.response_generator.minimum_natural_turns, 10
        )

    def test_appraisal_requires_and_validates_after_direct_response(self):
        action = "这个联系频率你是否接受？"
        value = _structured_appraisal()
        value["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_position", "evidence_span": action,
            },
            "consequential_claims": [],
            "continuation": {
                "status": "must_answer", "evidence_span": action,
                "after_direct_response": {
                    "status": "can_close", "evidence_span": action,
                },
            },
        }
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
            require_after_direct_response=True,
        )
        self.assertEqual(
            normalized["appraisal"]["dialogue_diagnostics"]["continuation"]
            ["after_direct_response"]["status"],
            "can_close",
        )
        del value["appraisal"]["dialogue_diagnostics"]["continuation"][
            "after_direct_response"
        ]
        with self.assertRaisesRegex(ValueError, "continuation"):
            _validate_appraisal(
                value, [], {"relationship.trust"}, {"negotiation_open"},
                action_text=action, require_dialogue_diagnostics=True,
                require_after_direct_response=True,
            )

    def test_appraisal_validates_live_question_partition(self):
        action = "这个联系频率你是否接受？"
        live_questions = ["是否接受联系频率", "如何处理分歧"]
        value = _structured_appraisal()
        value["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_position", "evidence_span": action,
            },
            "consequential_claims": [],
            "continuation": {
                "status": "must_answer", "evidence_span": action,
                "after_direct_response": {
                    "status": "continue", "evidence_span": action,
                    "resolved_live_questions": ["是否接受联系频率"],
                    "remaining_live_questions": ["如何处理分歧"],
                },
            },
        }
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
            require_after_direct_response=True,
            live_questions=live_questions,
            require_live_question_partition=True,
        )
        after_direct = normalized["appraisal"]["dialogue_diagnostics"][
            "continuation"
        ]["after_direct_response"]
        self.assertEqual(after_direct["remaining_live_questions"], ["如何处理分歧"])
        source_after_direct = value["appraisal"]["dialogue_diagnostics"][
            "continuation"
        ]["after_direct_response"]

        source_after_direct["status"] = "can_close"
        normalized_status = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
            require_after_direct_response=True,
            live_questions=live_questions,
            require_live_question_partition=True,
        )["appraisal"]["dialogue_diagnostics"]["continuation"][
            "after_direct_response"
        ]["status"]
        self.assertEqual(normalized_status, "can_close")

        source_after_direct["status"] = "continue"
        source_after_direct["remaining_live_questions"] = ["未经提供的问题"]
        conservative = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
            require_after_direct_response=True,
            live_questions=live_questions,
            require_live_question_partition=True,
        )["appraisal"]["dialogue_diagnostics"]["continuation"][
            "after_direct_response"
        ]
        self.assertEqual(
            conservative["resolved_live_questions"], ["是否接受联系频率"]
        )
        self.assertEqual(
            conservative["remaining_live_questions"], ["如何处理分歧"]
        )

    def test_appraisal_normalizes_after_direct_must_answer(self):
        action = "这个联系频率你是否接受？"
        live_questions = ["是否接受联系频率", "如何处理分歧"]
        value = _structured_appraisal()
        value["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_position", "evidence_span": action,
            },
            "consequential_claims": [],
            "continuation": {
                "status": "must_answer", "evidence_span": action,
                "after_direct_response": {
                    "status": "must_answer", "evidence_span": action,
                    "resolved_live_questions": ["是否接受联系频率"],
                    "remaining_live_questions": ["如何处理分歧"],
                },
            },
        }
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
            require_after_direct_response=True,
            live_questions=live_questions,
            require_live_question_partition=True,
        )
        after_direct = normalized["appraisal"]["dialogue_diagnostics"][
            "continuation"
        ]["after_direct_response"]
        self.assertEqual(after_direct["status"], "continue")
        self.assertEqual(
            after_direct["remaining_live_questions"], ["如何处理分歧"]
        )

    def test_appraisal_canonicalizes_singular_claim_domain_alias(self):
        action = "我建议把金额定下来。"
        value = _structured_appraisal()
        value["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_position", "evidence_span": action,
            },
            "consequential_claims": [{
                "claim_span": "把金额定下来",
                "impact_domain": "action_feasibility",
                "grounding": "proposal_or_hypothetical",
            }],
            "continuation": {
                "status": "must_answer", "evidence_span": action,
                "after_direct_response": {
                    "status": "can_close", "evidence_span": action,
                    "resolved_live_questions": ["金额是否确定"],
                    "remaining_live_questions": [],
                },
            },
        }
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
            require_after_direct_response=True,
            live_questions=["金额是否确定"],
            require_live_question_partition=True,
        )
        claim = normalized["appraisal"]["dialogue_diagnostics"][
            "consequential_claims"
        ][0]
        self.assertEqual(claim["impact_domains"], ["action_feasibility"])
        self.assertNotIn("impact_domain", claim)

    def test_appraisal_canonicalizes_narrow_diagnostic_aliases(self):
        action = "我确认这项沟通责任。"
        value = _structured_appraisal()
        value["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_confirmation", "evidence_span": action
            },
            "consequential_claims": [{
                "claim_span": "沟通责任",
                "impact_domains": ["communication_boundary"],
                "grounding": "observable_fact",
            }],
            "continuation": {"status": "continue", "evidence_span": action},
        }
        normalized = _validate_appraisal(
            value, [],
            state_variables={"relationship.trust"},
            dynamics_variables={"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
        )
        diagnostics = normalized["appraisal"]["dialogue_diagnostics"]
        self.assertEqual(
            diagnostics["substantive_novelty"]["label"],
            "necessary_confirmation",
        )
        self.assertEqual(
            diagnostics["consequential_claims"][0]["impact_domains"],
            ["responsibility"],
        )

    def test_appraisal_diagnostics_require_exact_action_evidence(self):
        action = "我建议把首期金额定为三千元，你是否接受？"
        value = _structured_appraisal()
        value["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_position",
                "evidence_span": "首期金额定为三千元",
            },
            "consequential_claims": [{
                "claim_span": "把首期金额定为三千元",
                "impact_domains": ["action_feasibility", "task_answer"],
                "grounding": "proposal_or_hypothetical",
            }],
            "continuation": {
                "status": "must_answer",
                "evidence_span": "你是否接受",
            },
        }
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
        )
        self.assertEqual(
            normalized["appraisal"]["dialogue_diagnostics"][
                "consequential_claims"
            ][0]["grounding"],
            "proposal_or_hypothetical",
        )
        bad = _structured_appraisal()
        bad["appraisal"]["dialogue_diagnostics"] = value["appraisal"][
            "dialogue_diagnostics"
        ].copy()
        bad["appraisal"]["dialogue_diagnostics"]["substantive_novelty"] = {
            "label": "new_position", "evidence_span": "paraphrased novelty"
        }
        bad["appraisal"]["dialogue_diagnostics"]["continuation"] = {
            "status": "must_answer", "evidence_span": "paraphrased evidence"
        }
        normalized_bad = _validate_appraisal(
            bad, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
        )
        self.assertEqual(
            normalized_bad["appraisal"]["dialogue_diagnostics"][
                "continuation"
            ]["evidence_span"],
            action,
        )
        self.assertEqual(
            normalized_bad["appraisal"]["dialogue_diagnostics"][
                "substantive_novelty"
            ]["evidence_span"],
            action,
        )

    def test_appraisal_drops_non_exact_optional_claim_annotation(self):
        action = "我们确认500元的节点，再讨论信任边界。"
        value = _structured_appraisal()
        value["appraisal"]["dialogue_diagnostics"] = {
            "substantive_novelty": {
                "label": "new_position", "evidence_span": action
            },
            "consequential_claims": [
                {"claim_span": "500元的节点",
                 "impact_domains": ["action_feasibility"],
                 "grounding": "observable_fact"},
                {"claim_span": "讨论后续还款安排",
                 "impact_domains": ["action_feasibility"],
                 "grounding": "proposal_or_hypothetical"},
            ],
            "continuation": {"status": "continue", "evidence_span": action},
        }
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_dialogue_diagnostics=True,
        )
        claims = normalized["appraisal"]["dialogue_diagnostics"][
            "consequential_claims"
        ]
        self.assertEqual([item["claim_span"] for item in claims], ["500元的节点"])

    def test_nested_appraisal_evidence_is_canonicalized(self):
        nested = _structured_appraisal(["t2"])
        nested["appraisal"]["evidence_turn_ids"] = nested.pop("evidence_turn_ids")
        normalized = _validate_appraisal(nested, ["t2"])
        self.assertEqual(normalized["evidence_turn_ids"], ["t2"])
        self.assertNotIn("evidence_turn_ids", normalized["appraisal"])

    def test_appraisal_evidence_must_come_from_retrieved_memory(self):
        appraisal = _structured_appraisal(["t2"])
        self.assertEqual(_validate_appraisal(appraisal, ["t2", "t3"]), appraisal)
        normalized = _validate_appraisal(appraisal, ["t3"])
        self.assertEqual(normalized["evidence_turn_ids"], [])
        repeated = _structured_appraisal(["t2", "t2", "t3", "t4", "t5", "t6"])
        self.assertEqual(
            _validate_appraisal(repeated, ["t2", "t3", "t4", "t5"])[
                "evidence_turn_ids"
            ],
            ["t2", "t3", "t4", "t5"],
        )

    def test_appraisal_cannot_assign_evaluated_action_to_environment_character(self):
        value = _structured_appraisal()
        value["appraisal"]["speaker_intent"] = "程野试图澄清治理安排"
        with self.assertRaisesRegex(ValueError, "assigned the evaluated action"):
            _validate_appraisal(
                value,
                [],
                {"relationship.trust"},
                {"negotiation_open"},
                environment_speaker={"name": "程野"},
            )
        value["appraisal"]["speaker_intent"] = "被评估参与者试图澄清治理安排"
        normalized = _validate_appraisal(
            value,
            [],
            {"relationship.trust"},
            {"negotiation_open"},
            environment_speaker={"name": "程野"},
        )
        self.assertEqual(normalized["appraisal"]["social_act"], "request")

    def test_structured_appraisal_suppresses_unknown_impact_variable(self):
        appraisal = _structured_appraisal()
        appraisal["appraisal"]["state_impacts"][0]["variable"] = "not_a_state"
        normalized = _validate_appraisal(
            appraisal,
            [],
            {"emotion.anger"},
            {"negotiation_open"},
        )
        self.assertEqual(normalized["appraisal"]["state_impacts"], [])

    def test_structured_response_hard_only_keeps_evasion_for_semantic_review(self):
        outputs = [
            json.dumps(_structured_response(
                "我还需要再算一下。"
            ), ensure_ascii=False),
            json.dumps(_structured_response(
                "我目前能先还500元。",
                [{
                    "event_type": "commitment",
                    "owner": "environment_agent",
                    "action_owner": "environment_agent",
                    "evidence_span": "我目前能先还500元。",
                    "status": "firm",
                }],
            ), ensure_ascii=False),
        ]

        class ResponseProvider:
            provenance = {"provider": "test-double", "model": "response-sequence"}

            def __init__(self):
                self.calls = []

            def complete(self, messages, **sampling):
                self.calls.append({"messages": messages, "sampling": sampling})
                return outputs[len(self.calls) - 1]

        scenario = json.loads(Path(
            "data/gpt50/experiment/scenario/scenarios/scenario_003/scenario_003.json"
        ).read_text(encoding="utf-8"))
        provider = ResponseProvider()
        generator = ModelResponseGenerator(
            provider, {"temperature": 0.2, "top_p": 0.8},
            "environment_response_v25", validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        result = generator.generate({
            "scenario": scenario, "history": [], "turn_id": 1,
            "action": {"text": "那14天内你预计能还多少？可以先说个具体数字。"},
            "interaction_ledger": {},
            "longitudinal_context": {
                "segment": {"segment_turn_id": 0}, "public_timeline": [],
            },
        })
        self.assertEqual(result["response_text"], "我还需要再算一下。")
        self.assertEqual(result["ledger_events"], [])
        self.assertEqual(result["ledger_event_normalizations"], [])
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0]["sampling"]["temperature"], 0.2)



    def test_owned_request_exception_is_bound_to_requested_action(self):
        context = {
            "turn_id": 3,
            "action": {
                "text": (
                    "我先整理分析结构，你同步原型进度时标出和展示稿对齐的模块。"
                ),
            },
            "interaction_ledger": {
                "latest_obligation": {
                    "owner": "environment_agent",
                    "source_thread_id": "t3:evaluated_agent:thread",
                },
            },
            "appraisal": {
                "ledger_events": [
                    {
                        "event_type": "proposal",
                        "owner": "evaluated_agent",
                        "action_owner": "evaluated_agent",
                        "evidence_span": "我先整理分析结构",
                        "status": "open",
                    },
                    {
                        "event_type": "request",
                        "owner": "evaluated_agent",
                        "action_owner": "environment_agent",
                        "evidence_span": (
                            "你同步原型进度时标出和展示稿对齐的模块"
                        ),
                        "status": "open",
                    },
                ],
            },
            "scenario": {},
            "history": [],
            "longitudinal_context": {
                "segment": {},
                "public_timeline": [],
            },
        }
        generator = ModelResponseGenerator(
            None, validation_profile="hard_only", horizon_mode="natural_max_20"
        )
        taken_over = generator._validate_candidate_for_profile(
            "我先整理分析结构，完成后同步进展。", context
        )
        requested = generator._validate_candidate_for_profile(
            "我会同步原型进度，并标出和展示稿对齐的模块。", context
        )
        self.assertEqual(
            taken_over,
            (False, "latest evaluated-agent action was taken over by environment_agent"),
        )
        self.assertEqual(requested, (True, ""))

    def test_natural_profile_keeps_exact_self_loop_for_semantic_review(self):
        repeated = (
            "我尽量在20天后给出一个大致金额范围，如果届时仍无法确定，"
            "我们可以重新讨论沟通方式和关系边界。"
        )
        outputs = [
            json.dumps(_structured_response(repeated), ensure_ascii=False),
            json.dumps(_structured_response(
                "好，这次先谈到这里。",
                [{
                    "event_type": "pause", "owner": "environment_agent",
                    "action_owner": "environment_agent",
                    "evidence_span": "这次先谈到这里", "status": "explicit",
                }],
            ), ensure_ascii=False),
        ]

        class ResponseProvider:
            provenance = {"provider": "test-double", "model": "saved-loop"}

            def __init__(self):
                self.calls = []

            def complete(self, messages, **sampling):
                self.calls.append({"messages": messages, "sampling": sampling})
                return outputs[len(self.calls) - 1]

        scenario = json.loads(Path(
            "data/gpt50/experiment/scenario/scenarios/scenario_003/scenario_003.json"
        ).read_text(encoding="utf-8"))
        provider = ResponseProvider()
        generator = ModelResponseGenerator(
            provider, {"temperature": 0.2, "top_p": 0.8},
            "environment_response_v25", validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        result = generator.generate({
            "scenario": scenario, "turn_id": 9,
            "history": [{
                "turn_id": 8, "role": "environment_agent", "text": repeated,
            }],
            "action": {
                "text": "那20天后如果能给出一个具体范围，我们可以先记录下来，再看后续如何推进。"
            },
            "interaction_ledger": {"latest_obligation": None},
            "longitudinal_context": {
                "segment": {"segment_turn_id": 2}, "public_timeline": [],
            },
        })
        self.assertEqual(result["response_text"], repeated)
        self.assertEqual(result["ledger_events"], [])
        self.assertEqual(len(provider.calls), 1)


    def test_appraisal_drops_pure_acceptance_mislabeled_as_owned_commitment(self):
        action = "我接受你14天内先还500元的提议。如果届时无法完成，希望你能提前沟通。"
        value = _structured_appraisal()
        value["appraisal"]["social_act"] = "commitment"
        value["appraisal"]["ledger_events"] = [
            {
                "event_type": "commitment", "owner": "evaluated_agent",
                "action_owner": "evaluated_agent",
                "evidence_span": "我接受你14天内先还500元的提议",
                "status": "firm",
            },
            {
                "event_type": "request", "owner": "evaluated_agent",
                "action_owner": "environment_agent",
                "evidence_span": "希望你能提前沟通", "status": "open",
            },
        ]
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_ledger_events=True,
            normalize_ledger_noise=True,
        )["appraisal"]
        self.assertEqual(
            [event["event_type"] for event in normalized["ledger_events"]],
            ["request"],
        )
        self.assertIn(
            "drop_acceptance_mislabeled_as_commitment",
            [item["operation"] for item in normalized["ledger_event_normalizations"]],
        )


    def test_appraisal_drops_copied_environment_event_and_normalizes_pending(self):
        action = "我接受这个模式，就按你说的方式保持联系。"
        value = _structured_appraisal()
        value["appraisal"]["social_act"] = "commitment"
        value["appraisal"]["event_features"]["commitment_signal"] = 2
        value["appraisal"]["ledger_events"] = [
            {
                "event_type": "commitment", "owner": "evaluated_agent",
                "action_owner": "evaluated_agent",
                "evidence_span": "我接受这个模式，就按你说的方式保持联系",
                "status": "pending",
            },
            {
                "event_type": "commitment", "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": "那我就按这个模式来", "status": "pending",
            },
        ]
        normalized = _validate_appraisal(
            value, [], {"relationship.trust"}, {"negotiation_open"},
            action_text=action, require_ledger_events=True,
            normalize_ledger_noise=True,
        )["appraisal"]
        self.assertEqual(len(normalized["ledger_events"]), 1)
        self.assertEqual(normalized["ledger_events"][0]["status"], "firm")
        self.assertEqual(
            [item["operation"] for item in normalized["ledger_event_normalizations"]],
            [
                "normalize_pending_commitment_status",
                "drop_irrelevant_speaker_or_history_event",
            ],
        )


if __name__ == "__main__":
    unittest.main()
