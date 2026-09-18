import unittest

from environment.response_completion import complete_environment_response
from environment.response_generator import ModelResponseGenerator
from environment.interaction_ledger import (
    compact_generation_ledger,
    initial_ledger,
    record_environment_response,
    record_evaluated_action,
    validate_semantic_ledger_events,
)
from policies.model_policy import ModelPolicy
from providers.text import (
    asserts_ungrounded_institutional_procedure,
    asserts_ungrounded_performance_amount,
    asserts_ungrounded_remaining_amount,
    addresses_speaker_as_other,
    avoids_unsupported_offscreen_claim,
    bounces_latest_stance_request,
    claims_other_speaker_commitment,
    claims_pending_commitment_completed,
    commitment_evidence_status,
    current_repayment_commitment_status,
    collapses_multiple_facets_early,
    complete_distinct_text,
    confirms_ungrounded_numeric_detail,
    contradicts_explicit_installment_total,
    confirms_unobserved_completion,
    contradicts_pending_own_commitment,
    copies_goal_thread_label,
    copies_latest_other_utterance,
    dialogue_template_signatures,
    directly_answers_latest_proposal,
    follows_dialogue_format,
    follows_policy_action_format,
    follows_latest_invited_scope,
    goal_thread_constraints,
    introduces_unprompted_coordination_actor,
    introduces_unprompted_legal_escalation,
    introduces_unrequested_artifact,
    evades_latest_obligation,
    evades_latest_open_proposal,
    evades_latest_disposition_request,
    evades_explicit_amount_question,
    lacks_natural_final_closure,
    overloads_consequential_terms,
    opens_followup_on_saturated_focus,
    opens_new_repayment_commitment,
    mirrors_latest_speaker_move,
    opens_future_cycle_on_final_turn,
    prematurely_reports_future_commitment_completion,
    premature_closure_with_untouched_goals,
    renews_pending_commitment_without_change,
    repeats_future_meeting_deferral,
    repeats_exactly_without_substantive_public_event,
    repeats_own_utterance_without_new_challenge,
    repeats_saturated_goal_focus,
    repeats_stalled_focus,
    rewrites_absent_commitment_as_nonperformance,
    reused_dialogue_template_signatures,
    strip_outer_dialogue_quotes,
    suspends_existing_obligation,
    template_loop_signatures,
    template_escape_instructions,
    TextValidationError,
    upgrades_tentative_to_agreement,
    text_similarity,
    violates_environment_counterparty_role,
    violates_role_specific_action,
)


class SequenceProvider:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = 0
        self.messages = []

    def complete(self, messages, **sampling):
        self.calls += 1
        self.messages.append(messages)
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

    def test_retry_receives_runtime_rejection_feedback(self):
        class MessageProvider:
            def __init__(self):
                self.messages = []

            def complete(self, messages, **sampling):
                self.messages.append(messages)
                return "旧句" if len(self.messages) == 1 else "换一个议题继续推进"

        provider = MessageProvider()
        value = complete_distinct_text(
            provider,
            [{"role": "user", "content": "fixed"}],
            {},
            ["旧句"],
            context="test",
        )
        self.assertEqual(value, "换一个议题继续推进")
        self.assertIn("semantic repetition", provider.messages[1][-1]["content"])
        self.assertIn("closest earlier utterance", provider.messages[1][-1]["content"])
        self.assertIn("speech act", provider.messages[1][-1]["content"])

    def test_policy_prompt_contains_prior_move_ledger_without_forced_phase(self):
        class CapturingProvider:
            def __init__(self):
                self.messages = None

            def complete(self, messages, **sampling):
                self.messages = messages
                return "那我改为确认哪些部分现在可以直接决定。"

        provider = CapturingProvider()
        policy = ModelPolicy("p", provider)
        policy.generate({"history": [
            {"role": "evaluated_agent", "text": "请再解释一次流程。"},
            {"role": "environment_agent", "text": "流程已经说明。"},
        ]})
        prompt = next(item["content"] for item in provider.messages if item["role"] == "user")
        self.assertIn('"own_prior_utterances"', prompt)
        self.assertIn("请再解释一次流程", prompt)
        self.assertNotIn('"progression_phase"', prompt)
        self.assertIn('"instruction"', prompt)
        self.assertEqual(provider.messages[0]["role"], "system")
        self.assertIn("evaluated_agent", provider.messages[0]["content"])

    def test_environment_prompt_contains_its_own_prior_response_ledger(self):
        class CapturingProvider:
            def __init__(self):
                self.messages = None

            def complete(self, messages, **sampling):
                self.messages = messages
                return "目前我能直接确认的是记录范围，结果仍不能承诺。"

        provider = CapturingProvider()
        generator = ModelResponseGenerator(provider)
        generator.generate({
            "history": [
                {"role": "evaluated_agent", "text": "请给结论。"},
                {"role": "environment_agent", "text": "需要等待流程。"},
            ],
            "action": {"text": "那现在能确认什么？"},
        })
        prompt = next(item["content"] for item in provider.messages if item["role"] == "user")
        self.assertIn("需要等待流程", prompt)
        self.assertIn('"instruction"', prompt)
        self.assertEqual(provider.messages[0]["role"], "system")
        self.assertIn("environment_agent", provider.messages[0]["content"])

    def test_pending_commitment_retry_guidance_forbids_recap(self):
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "月底前还五百",
        }]}
        guidance = ModelResponseGenerator._retry_guidance({
            "interaction_ledger": ledger
        })
        self.assertIn("已有承诺不需要重述", guidance)
        self.assertIn("金额、日期", guidance)

    def test_environment_prompt_preserves_private_motive_without_keyword_rules(self):
        class CapturingProvider:
            def __init__(self):
                self.messages = None

            def complete(self, messages, **sampling):
                self.messages = messages
                return "我可以先说明能确认的部分，其他地方我现在仍有顾虑。"

        provider = CapturingProvider()
        ModelResponseGenerator(provider).generate({
            "history": [],
            "turn_id": 1,
            "action": {"text": "请把情况都说清楚。"},
            "scenario": {
                "environment_agent": {
                    "persona": {"name": "朋友", "role": "朋友"},
                    "hidden_intention": "保护自身声誉并避免直接承认失误",
                }
            },
        })
        prompt = next(item["content"] for item in provider.messages if item["role"] == "user")
        self.assertIn("保护自身声誉并避免直接承认失误", prompt)
        self.assertIn('"role_lock"', prompt)
        self.assertNotIn('"persona_strategy_constraints"', prompt)

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

    def test_validation_error_retains_every_rejected_candidate(self):
        provider = SequenceProvider(["旧句", "旧句", "旧句"])
        with self.assertRaises(TextValidationError) as caught:
            complete_distinct_text(
                provider,
                [{"role": "user", "content": "fixed"}],
                {},
                ["旧句"],
                context="test",
                max_attempts=3,
            )
        self.assertEqual(len(caught.exception.diagnostics), 3)
        self.assertTrue(all(
            item["reason"] == "semantic repetition of an earlier turn"
            for item in caught.exception.diagnostics
        ))

    def test_pending_commitment_owner_and_public_role_are_enforced(self):
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "我会核对原始记录。",
        }]}
        self.assertTrue(claims_other_speaker_commitment(
            "我会核对原始记录。", ledger, "evaluated_agent"
        ))
        role = {
            "role": "要求落实还款安排的出借朋友",
            "explicit_goal": "促成明确可执行的还款安排",
        }
        self.assertTrue(violates_role_specific_action("那我今天把钱转给你。", role))
        self.assertTrue(violates_role_specific_action(
            "我14天内能先还500元，这个金额你看是否可行？", role
        ))
        self.assertFalse(violates_role_specific_action("请你明确还款时间。", role))
        self.assertFalse(violates_role_specific_action(
            "那28天节点还500元我记下来。这笔若如期完成，"
            "我们再看是否继续商定后续还款节奏。",
            role,
        ))
        self.assertFalse(violates_role_specific_action(
            "届时我会等你提供转账记录，再确认是否覆盖部分本金。",
            role,
        ))
        self.assertFalse(violates_role_specific_action(
            "我们再讨论下一步的还款周期。", role
        ))
        self.assertTrue(violates_role_specific_action(
            "那我们先放下还款时间，等你安心再说。", role
        ))
        self.assertTrue(violates_role_specific_action(
            "你希望我怎么做才能让你安心？", role
        ))
        self.assertFalse(violates_environment_counterparty_role(
            "除了按时还款，我们也该谈谈信任。", role
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "剩下的部分等你那边资金到位后再说。", role
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "有限信任取决于你能按节奏持续还款。", role
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "我接受你提出的600元还款，希望你在28天内完成。", role
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "我会等你那边发薪后再确认。", role
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "等你那边消息确切，我们再继续。", role
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "等你那边宽裕些我再联系。", role
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "等你那边情况明朗了再商量。", role
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "五百块我收到了。", role
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "我会继续观察实际履约，再决定是否恢复经济信任。", role
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "未来经济请求我会要求可核验的还款计划。", role
        ))

        self.assertTrue(violates_environment_counterparty_role(
            "14天还500元这个节点我觉得可以尝试，但希望你能确保按时履行。", role
        ))


    def test_tentative_governance_statement_is_not_upgraded_by_bare_word_commitment(self):
        latest = "补上当初承诺的部分，需要看董事会是否愿意讨论。"
        self.assertFalse(upgrades_tentative_to_agreement(
            "口头承诺仍然悬着，不能算解决。", latest
        ))
        self.assertTrue(upgrades_tentative_to_agreement(
            "我们已经确认按这个安排执行。", latest
        ))


    def test_similarity_detects_small_rephrasing(self):
        self.assertGreater(text_similarity("我们现在按清单推进", "我们现在按清单继续推进"), 0.6)

    def test_template_loop_detects_repeated_conditional_frames(self):
        values = [
            "我接受这个安排，但若时间变化需要重排。",
            "我同意先执行，不过如果冲突要再确认。",
            "我理解你的要求，但若信息不全就暂停。",
        ]
        self.assertIn("acceptance_then_condition", template_loop_signatures(values))
        self.assertIn("given_then_condition", dialogue_template_signatures("既然已确认，那就执行。"))

    def test_template_loop_detects_serial_artifacts_and_repeated_deferral(self):
        artifacts = [
            "我再整理一份数据报告。",
            "我会补充一份分工清单。",
            "那我附上另一份索引目录。",
        ]
        deferrals = [
            "下周见面时再确认署名。",
            "下周三我们届时讨论最终顺序。",
            "到时候再敲定具体安排。",
        ]
        confirmations = [
            "表格确认无误后按此执行。",
            "这个安排已确认，就按计划执行。",
            "方案确认无误后便定下来。",
        ]
        self.assertIn("serial_artifact_offer", template_loop_signatures(artifacts))
        self.assertIn("future_review_deferral", template_loop_signatures(deferrals))
        self.assertIn("reconfirmation_loop", template_loop_signatures(confirmations))
        plan_churn = [
            "我先把分工表发给你。",
            "你看看分工表是否需要调整。",
            "确认分工表后我们按计划执行。",
        ]
        self.assertIn("artifact_or_plan_churn", template_loop_signatures(plan_churn))

    def test_template_loop_detects_repeated_closure_and_future_meeting(self):
        closures = [
            "钱的事翻篇了，以后有事直说。",
            "这件事已经说定，咱们往前看。",
            "旧事不再提，就按今天说的办。",
        ]
        future_meetings = [
            "下周组会再讨论署名。",
            "实验数据下周组会集中对齐。",
            "下周组会直接过一遍答辩安排。",
        ]
        self.assertIn("resolved_topic_reopening", template_loop_signatures(closures))
        self.assertIn("future_review_deferral", template_loop_signatures(future_meetings))

    def test_template_loop_detects_serial_external_errands(self):
        actions = [
            "那我先联系答辩秘书确认流程。",
            "那我先对接财务部门确认报销。",
            "明白了，那我先协调委员会成员日程。",
        ]
        responses = [
            "你直接去处理毕业流程即可。",
            "不用特意汇报，专心把手续办妥。",
            "你只需按节点推进，把流程走完。",
        ]
        self.assertIn("serial_task_churn", template_loop_signatures(actions))
        self.assertIn("serial_external_coordination", template_loop_signatures(actions))
        self.assertIn("generic_process_push", template_loop_signatures(responses))

    def test_early_closure_is_rejected_only_when_public_goal_is_untouched(self):
        ledger = {"goal_threads": [
            {"text": "了解延期背后的现实困难", "status": "open", "discussion_rounds": 0},
            {"text": "暂停新的经济往来", "status": "open", "discussion_rounds": 0},
        ]}
        self.assertTrue(premature_closure_with_untouched_goals(
            "那我们先各自处理自己的事。", ledger, 7
        ))
        self.assertFalse(premature_closure_with_untouched_goals(
            "在还清之前，我们暂停新的经济往来。", ledger, 7
        ))
        self.assertFalse(premature_closure_with_untouched_goals(
            "那我们先各自处理自己的事。", ledger, 18
        ))

    def test_repayment_followup_rephrase_is_single_use(self):
        self.assertIn(
            "repayment_followup_refrain",
            reused_dialogue_template_signatures(
                "月底我会再确认五千到账。",
                ["我按25号前收到五千来跟进。"],
            ),
        )

    def test_final_turn_cannot_open_another_future_cycle(self):
        self.assertTrue(opens_future_cycle_on_final_turn(
            "月底落实后我再联系你讨论后续安排。", 20
        ))
        self.assertFalse(opens_future_cycle_on_final_turn(
            "我明白，今天先谈到这里。", 20
        ))
        self.assertFalse(opens_future_cycle_on_final_turn(
            "月底落实后我再联系你。", 19
        ))
        self.assertFalse(opens_future_cycle_on_final_turn(
            "未来若再有经济请求，我会直接拒绝，但普通联系不受影响。", 20
        ))
        self.assertTrue(opens_future_cycle_on_final_turn(
            "那就先这样，等你有空时发个消息，我再回应。", 20
        ))
        self.assertTrue(opens_future_cycle_on_final_turn(
            "那就先这样，下次你主动打招呼时，我就回应。", 20
        ))

    def test_borrower_cannot_claim_receiving_bare_chinese_amount(self):
        self.assertTrue(violates_environment_counterparty_role(
            "我会在25号前收到五千。",
            {"role": "要求落实还款安排的出借朋友"},
        ))

    def test_economic_boundary_and_consensus_rephrases_are_single_use(self):
        prior = ["在还清之前，我们不再涉及新的借款。"]
        self.assertIn(
            "economic_boundary_refrain",
            reused_dialogue_template_signatures(
                "之后只谈还款，不再涉及其他经济往来。", prior
            ),
        )
        self.assertIn(
            "consensus_execution_refrain",
            reused_dialogue_template_signatures(
                "那就按今天的共识执行。", ["我们按这个共识推进。"]
            ),
        )

    def test_borrower_cannot_assign_its_financial_difficulty_to_lender(self):
        self.assertTrue(violates_environment_counterparty_role(
            "我理解你目前的处境和资金压力。",
            {"role": "要求落实还款安排的出借朋友"},
        ))

    def test_third_future_meeting_deferral_is_rejected_per_speaker(self):
        history = [
            {"role": "evaluated_agent", "text": "下周见面时先谈金额。"},
            {"role": "environment_agent", "text": "好。"},
            {"role": "evaluated_agent", "text": "下周见面时再谈分期。"},
        ]
        self.assertTrue(repeats_future_meeting_deferral(
            "那下周见面时也谈谈信任。", history, "evaluated_agent"
        ))
        self.assertFalse(repeats_future_meeting_deferral(
            "这次延期已经影响了我的信任。", history, "evaluated_agent"
        ))

    def test_borrower_cannot_assign_first_installment_capacity_to_lender(self):
        self.assertTrue(violates_environment_counterparty_role(
            "下周我们确认一下你首期能承担的金额。",
            {"role": "要求落实还款安排的出借朋友"},
        ))

    def test_unrequested_communication_template_is_artifact_churn(self):
        self.assertTrue(introduces_unrequested_artifact(
            "下周我们草拟一个沟通模板。",
            "双方只讨论了信任和经济往来。",
        ))

    def test_stalled_artifact_focus_allows_cross_domain_governance_switch(self):
        ledger = {
            "progress": {
                "current_focus": "artifact_workflow",
                "consecutive_focus_utterances": 4,
            },
            "goal_threads": [
                {"text": "要求逐条解释稀释决策及授权链", "status": "discussed"},
                {"text": "提出治理角色", "status": "open"},
                {"text": "决定未来合作是否重建", "status": "open"},
            ],
        }
        self.assertFalse(repeats_stalled_focus(
            "我们可以先讨论未来合作中的治理角色和决策权。", ledger
        ))

    def test_stalled_broad_focus_allows_new_atomic_goal_thread(self):
        ledger = {
            "progress": {
                "current_focus": "communication_boundary",
                "consecutive_focus_utterances": 4,
            },
            "goal_threads": [
                {"text": "约定安排有变时如何沟通", "status": "saturated"},
                {"text": "厘清双方关系边界", "status": "open"},
            ],
        }
        self.assertFalse(repeats_stalled_focus(
            "我想听听你对我们关系边界的真实看法。", ledger
        ))
        self.assertTrue(repeats_stalled_focus(
            "如果安排有变，希望你提前告诉我。", ledger
        ))

    def test_redundant_same_owner_pending_commitment_is_rejected(self):
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "我会在下个月底先还两成。",
            "focus": "practical_execution",
            "terms": ["下个月", "月底", "两成"],
        }]}
        self.assertTrue(renews_pending_commitment_without_change(
            "我会按计划在下个月底先还两成。", ledger, "environment_agent"
        ))
        self.assertTrue(renews_pending_commitment_without_change(
            "我会在下个月底先还两成，之后每月分期。", ledger, "environment_agent"
        ))
        self.assertFalse(renews_pending_commitment_without_change(
            "我会在下个月底先还两成，之后每月分期。",
            ledger,
            "environment_agent",
            "如果有余力，之后能否改为每月分期？",
        ))
        self.assertFalse(renews_pending_commitment_without_change(
            "我理解你的失望，之前的延期确实伤害了信任。", ledger, "environment_agent"
        ))

    def test_pending_repayment_cannot_be_declared_settled(self):
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "我会在半个月后还款。",
            "object": "半个月后还款",
        }]}
        self.assertTrue(claims_pending_commitment_completed(
            "那这笔借款就算两清了。", ledger
        ))
        self.assertTrue(claims_pending_commitment_completed(
            "五百块我收到了。", ledger
        ))
        self.assertTrue(claims_pending_commitment_completed(
            "咱们把这段经济往来彻底翻篇。", ledger
        ))
        self.assertFalse(claims_pending_commitment_completed(
            "还款安排先按这个期限保留。", ledger
        ))

    def test_future_intention_cannot_be_confirmed_as_completed(self):
        self.assertTrue(confirms_unobserved_completion(
            "行，那笔钱我收到了。",
            "那我今天就转给你。",
        ))
        self.assertFalse(confirms_unobserved_completion(
            "转账后告诉我一声。",
            "那我今天就转给你。",
        ))
        self.assertFalse(confirms_unobserved_completion(
            "行，那笔钱我收到了。",
            "我刚刚已经转给你了。",
        ))
        self.assertFalse(confirms_unobserved_completion(
            "资金到位后我会还款，若未收到款项就先说明。",
            "请确认资金到位后你会还款。",
        ))
        self.assertFalse(confirms_unobserved_completion(
            "收到，旧账不影响以后正常联系。",
            "我不会再主动提这笔钱，之后按约定处理。",
        ))
        self.assertFalse(confirms_unobserved_completion(
            "收到你的意思，我们到这里为止。",
            "那我接受这个边界。",
        ))
        self.assertTrue(confirms_unobserved_completion(
            "我已确认收到工作日志和版本记录，署名异议继续保留。",
            "我先把工作日志和版本记录作为客观证据提交。",
        ))
        self.assertTrue(confirms_unobserved_completion(
            "署名顺序的保留意见，我已经在贡献说明中注明。",
            "我会把署名顺序的保留意见作为附件提交。",
        ))

    def test_repayment_wait_and_plan_reassurance_loops_are_detected(self):
        values = [
            "下周五第一期还款按计划执行。",
            "我期待你下周五按约定完成第一期。",
            "第一期就照这个节奏走，等你行动。",
            "下周五到账后再说第二期。",
        ]
        loops = template_loop_signatures(values)
        self.assertIn("repayment_schedule_churn", loops)
        self.assertIn("plan_reassurance_loop", loops)
        self.assertIn("future_action_wait", dialogue_template_signatures(
            "我会等待你的行动后再议。"
        ))

    def test_full_settled_issue_refrain_is_rejected(self):
        rejected_ia003_actions = [
            "那这笔钱的事就这么定了，15号前我这边不会打扰你。",
            "那这笔钱的事就按15号执行，期间不主动联系。",
            "15号按计划处理，有特殊情况你直接说。",
            "那就好，15号准时执行，之后不提这笔账。",
        ]
        self.assertIn(
            "settled_issue_refrain",
            template_loop_signatures(rejected_ia003_actions),
        )
        self.assertIn(
            "settled_issue_refrain",
            dialogue_template_signatures(rejected_ia003_actions[0]),
        )

    def test_goal_label_prefix_and_false_ownership_echo_are_distinguished(self):
        ledger = {"goal_threads": [{"text": "厘清双方关系边界"}]}
        self.assertTrue(copies_goal_thread_label(
            "厘清双方关系边界。我不愿继续谈私人财务。", ledger
        ))
        self.assertFalse(copies_goal_thread_label(
            "我不愿继续谈私人财务，这就是我的边界。", ledger
        ))
        self.assertFalse(mirrors_latest_speaker_move(
            "我理解你希望明确边界，但我不接受反复追问隐私。",
            "我理解你希望讨论边界。哪部分要求让你难以接受？",
        ))

    def test_repeated_future_repayment_with_huanni_is_detected(self):
        values = [
            "下周我先还你两千元。",
            "下周两千元我会准时还你。",
            "我下周会按时还你两千元。",
        ]
        self.assertIn("same_future_transfer", template_loop_signatures(values))

    def test_goal_constraints_rank_open_facets_before_discussed(self):
        constraints = goal_thread_constraints({"goal_threads": [
            {"id": "goal:1", "text": "还款安排", "status": "saturated", "discussion_rounds": 4},
            {"id": "goal:2", "text": "信任受损", "status": "discussed", "discussion_rounds": 2},
            {"id": "goal:3", "text": "新的经济往来", "status": "open", "discussion_rounds": 0},
        ]})
        self.assertEqual(
            constraints["available_existing_facets"],
            ["新的经济往来", "信任受损"],
        )
        self.assertEqual(constraints["saturated_facets"], ["还款安排"])

    def test_saturated_goal_focus_blocks_revisit_but_keeps_open_facet(self):
        ledger = {"goal_threads": [
            {"text": "明确可执行的还款安排", "status": "saturated"},
            {"text": "核对还款安排和现实困难", "status": "saturated"},
            {"text": "厘清双方关系边界", "status": "open"},
            {"text": "暂停新的经济往来", "status": "open"},
        ]}
        self.assertTrue(repeats_saturated_goal_focus(
            "半个月后请务必按时还款。", ledger
        ))
        self.assertTrue(repeats_saturated_goal_focus(
            "我确认你这几天能转的只有五百块，但请明确具体哪天操作。",
            ledger,
        ))
        self.assertFalse(repeats_saturated_goal_focus(
            "在信任恢复前暂停新的经济往来。", ledger
        ))
        self.assertFalse(repeats_saturated_goal_focus(
            "具体还款暂时定不下来，先谈谈这对相处边界的影响。", ledger
        ))
        self.assertFalse(repeats_saturated_goal_focus(
            "钱的事先放一边，咱们把聊天氛围调回来，见面轻松点。",
            ledger,
        ))

    def test_unrequested_artifact_workflow_is_rejected(self):
        self.assertTrue(introduces_unrequested_artifact(
            "你先写个明确的还款计划，明天发给我。",
            "目前只能接受半个月宽限。",
        ))
        self.assertFalse(introduces_unrequested_artifact(
            "好，我明天把计划发给你。",
            "请把计划写清楚后发给我。",
        ))
        self.assertFalse(introduces_unrequested_artifact(
            "请直接说清楚你能还多少。",
            "目前只能接受半个月宽限。",
        ))

    def test_artifact_refusal_does_not_reverse_repayment_commitment(self):
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "我会半个月后转账。",
        }]}
        self.assertFalse(contradicts_pending_own_commitment(
            "书面确认暂时无法配合，但口头还款约定不变。",
            ledger,
            "environment_agent",
        ))
        self.assertFalse(contradicts_pending_own_commitment(
            "目前没法给出方案，先谈清楚相处边界。",
            ledger,
            "environment_agent",
        ))

    def test_runtime_rejects_fifth_utterance_on_same_practical_focus(self):
        ledger = {
            "progress": {
                "current_focus": "practical_execution",
                "consecutive_focus_utterances": 4,
            }
        }
        self.assertTrue(repeats_stalled_focus(
            "等工资到账后我就转账。", ledger
        ))
        self.assertFalse(repeats_stalled_focus(
            "反复延期已经影响了我们的信任边界。", ledger
        ))

    def test_setting_a_number_is_not_misread_as_reopening_closed_topic(self):
        signatures = dialogue_template_signatures(
            "能，我们把具体的还款数字定下来，也是给友谊一个交代。"
        )
        self.assertNotIn("resolved_topic_reopening", signatures)

    def test_unsupported_pending_commitment_reversal_is_rejected(self):
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "月底我会按约定转账。",
        }]}
        self.assertTrue(contradicts_pending_own_commitment(
            "月底转账还得看资金是否到位，我暂时无法确定。",
            ledger,
            "environment_agent",
        ))
        self.assertFalse(contradicts_pending_own_commitment(
            "月底我会按约定转账，同时提前通知你。",
            ledger,
            "environment_agent",
        ))

    def test_boundary_refusal_does_not_cross_punctuation_into_contact_reversal(self):
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "这期间我会认真考虑如何更好地履行承诺。",
        }]}
        self.assertFalse(contradicts_pending_own_commitment(
            "我确认你的立场，未来经济请求直接拒绝，普通朋友联系保持不变。",
            ledger,
            "environment_agent",
        ))

    def test_numeric_confirmation_requires_observable_grounding(self):
        history = "周五先还五千，剩下的一半月底结清。"
        self.assertFalse(confirms_ungrounded_numeric_detail(
            "我确认周五先还五千。", history
        ))
        self.assertTrue(confirms_ungrounded_numeric_detail(
            "我确认下周三先还八千。", history
        ))
        self.assertFalse(confirms_ungrounded_numeric_detail(
            "我建议下周三先还八千。", history
        ))
        self.assertFalse(confirms_ungrounded_numeric_detail(
            "我确认25号先还五千。", "此前约定 25 号先还五千。"
        ))

    def test_ordinary_boundary_language_is_not_an_ultimatum(self):
        self.assertNotIn(
            "repeated_ultimatum",
            dialogue_template_signatures(
                "以后保持朋友间的坦诚，不再试探彼此底线。"
            ),
        )
        self.assertIn(
            "repeated_ultimatum",
            dialogue_template_signatures("我不会再给你任何机会。"),
        )

    def test_early_multi_facet_settlement_is_rejected(self):
        value = (
            "既然新钱不再借，那就把旧账定死：三千块马上转，"
            "剩下的下周补齐，之后只谈情义不谈钱。"
        )
        self.assertTrue(collapses_multiple_facets_early(value, 3))
        self.assertFalse(collapses_multiple_facets_early(value, 6))
        self.assertFalse(collapses_multiple_facets_early(
            "这几天我先转三千块。", 3
        ))

    def test_repeated_relationship_closure_and_acknowledgement_are_loops(self):
        closures = [
            "25号以后咱们两清，各自忙各自的事。",
            "之后各自过好自己的生活，有需要再联系。",
            "从此只谈是非，不谈条件。",
        ]
        acknowledgements = [
            "那好，我接受你的态度。",
            "好的，我理解你的想法。",
            "明白，我确认这个安排。",
        ]
        self.assertIn(
            "relationship_closure_refrain", template_loop_signatures(closures)
        )
        self.assertIn(
            "acknowledgement_refrain",
            template_loop_signatures(acknowledgements),
        )

    def test_template_escape_feedback_is_specific_and_chinese(self):
        feedback = template_escape_instructions([
            "future_review_deferral",
            "resolved_topic_reopening",
        ])
        self.assertIn("不要再提下周", feedback)
        self.assertIn("不要再说翻篇", feedback)

    def test_cross_speaker_first_person_move_mirroring_is_rejected(self):
        self.assertTrue(mirrors_latest_speaker_move(
            "周计划已启动，我会按此节奏推进实验。",
            "明白，我会立刻按周计划推进实验。",
        ))
        self.assertTrue(mirrors_latest_speaker_move(
            "那我先按这个顺序汇报核心实验结果。",
            "那我先汇报一下核心实验结果。",
        ))
        self.assertFalse(mirrors_latest_speaker_move(
            "我先修改结论表述。",
            "我会核实跨学期学分规则。",
        ))

    def test_runtime_retries_third_use_of_same_template(self):
        provider = SequenceProvider([
            "我理解你的要求，但若有变化就再讨论。",
            "我们先核对周三复诊的交通安排。",
        ])
        value = complete_distinct_text(
            provider,
            [{"role": "user", "content": "fixed"}],
            {},
            [
                "我接受这个安排，但若时间变化需要重排。",
                "我同意先执行，不过如果冲突要再确认。",
            ],
            context="test",
        )
        self.assertEqual(value, "我们先核对周三复诊的交通安排。")
        self.assertEqual(provider.calls, 2)

    def test_duplicate_observation_text_does_not_double_count_template(self):
        provider = SequenceProvider([
            "既然你愿意沟通，那就谈清楚今后的关系边界。"
        ])
        value = complete_distinct_text(
            provider,
            [{"role": "user", "content": "fixed"}],
            {},
            ["既然你愿意还款，那就定日期。"] * 2,
            context="test",
        )
        self.assertIn("关系边界", value)

    def test_unrelated_candidate_is_not_rejected_for_prior_template_loop(self):
        self.assertEqual(
            reused_dialogue_template_signatures(
                "我们改为核对交通安排。",
                ["既然如此，那就暂停。"] * 3,
            ),
            [],
        )

    def test_environment_retry_names_template_and_offers_closure(self):
        provider = SequenceProvider([
            "我会再确认一次安排。",
            "这件事已经确定，先到这里。",
        ])
        value = complete_environment_response(
            provider,
            [{"role": "user", "content": "fixed"}],
            {},
            ["我会补充记录。", "我会核对安排。"],
        )
        self.assertEqual(value, "这件事已经确定，先到这里。")
        retry = provider.messages[1][-1]["content"]
        self.assertIn("future_commitment", retry)
        self.assertIn("natural closure", retry)

    def test_dialogue_format_rejects_stage_directions_and_labels(self):
        self.assertFalse(follows_dialogue_format("（叹气）我们继续。"))
        self.assertFalse(follows_dialogue_format("顾岚：我们继续。"))
        self.assertFalse(follows_dialogue_format("“我们继续核对。”"))
        self.assertFalse(follows_dialogue_format("导师眉头微皱，随后要求补材料。"))
        self.assertTrue(follows_dialogue_format("我们继续核对下一项。"))

    def test_environment_retries_self_address_role_swap(self):
        provider = SequenceProvider([
            "导师，既然您已经决定，我会提交材料。",
            "我不同意你绕过组内复核，但可以先核对原始记录。",
        ])
        generator = ModelResponseGenerator(provider)
        result = generator.generate({
            "history": [],
            "action": {"text": "请明确决定。"},
            "scenario": {"environment_agent": {"name": "导师", "role": "导师"}},
        })
        self.assertEqual(result, "我不同意你绕过组内复核，但可以先核对原始记录。")
        self.assertTrue(addresses_speaker_as_other("导师，您先确认。", {"name": "导师"}))

    def test_environment_rejects_invented_third_party_outcome(self):
        self.assertFalse(avoids_unsupported_offscreen_claim(
            "你的申请将触发学术委员会直接冻结实验权限。",
            environment=True,
        ))

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
            "我可以先说明当前能确认的复核范围，但无法预先承诺结果。",
        ])
        result = ModelResponseGenerator(provider).generate({"history": [], "action": {"text": "请复核"}})
        self.assertEqual(result, "我可以先说明当前能确认的复核范围，但无法预先承诺结果。")
        self.assertEqual(provider.calls, 2)

    def test_offscreen_claim_validator_rejects_specific_clause_and_ticket(self):
        self.assertFalse(avoids_unsupported_offscreen_claim("根据政策第7.2条，我有权复核。"))
        self.assertFalse(avoids_unsupported_offscreen_claim("申请号为 HR-123。"))
        self.assertTrue(avoids_unsupported_offscreen_claim("要求 HR 三日内答复。"))
        self.assertFalse(avoids_unsupported_offscreen_claim("行政助理会在两小时内发送。", environment=True))
        self.assertTrue(avoids_unsupported_offscreen_claim("我会在14天内先还一部分。", environment=True))
        self.assertFalse(avoids_unsupported_offscreen_claim("学院已完成备案。", environment=True))
        self.assertFalse(avoids_unsupported_offscreen_claim(
            "融资文件的授权记录正在整理中。", environment=True
        ))
        self.assertTrue(avoids_unsupported_offscreen_claim("我会先确认是否存在复核渠道。"))


    def test_environment_rejects_reverse_order_institutional_outcome(self):
        self.assertFalse(avoids_unsupported_offscreen_claim(
            "即刻启动学院调查程序并暂停你所有实验权限。", environment=True
        ))
        self.assertFalse(avoids_unsupported_offscreen_claim(
            "听证会已经锁定结论，你无权再提出异议。", environment=True
        ))

    def test_recipient_pronoun_is_not_first_person_action_ownership(self):
        latest = (
            "我建议28天内再还800元，我会提前一天通知你确认账户信息。"
        )
        self.assertFalse(mirrors_latest_speaker_move(
            "我接受这个安排，请你提前一天通知我确认账户信息。", latest
        ))

    def test_confirming_other_speakers_statement_is_not_action_takeover(self):
        latest = (
            "今天我可以明确：21天时会通过信息确认进展，"
            "并提出下一步可行安排。"
        )
        self.assertFalse(mirrors_latest_speaker_move(
            "我确认你今天明确了21天时的信息安排，但它还不是履约记录。",
            latest,
        ))
        self.assertTrue(mirrors_latest_speaker_move(
            "我会确认21天时的信息安排，并提出下一步方案。",
            latest,
        ))

    def test_question_or_acceptance_does_not_take_over_other_speaker_move(self):
        latest = "我会在明天会议前确认治理条款，并说明投票权安排。"
        self.assertFalse(mirrors_latest_speaker_move(
            "我要求查看过去的书面确认，口头约定转为条款的责任由谁承担？",
            latest,
        ))
        self.assertFalse(mirrors_latest_speaker_move(
            "我接受你确认治理安排的承诺，但经济补偿仍有分歧。",
            latest,
        ))
        self.assertTrue(mirrors_latest_speaker_move(
            "创始团队意见需在明天确认，否则我要求暂停稀释方案。",
            "如果明天无法确认创始团队意见，我将要求暂停稀释方案。",
        ))

    def test_environment_may_answer_current_obligation_that_saturates_thread(self):
        context = {
            "turn_id": 5,
            "action": {"text": "是否能用知情机制提高提名透明度？"},
            "history": [],
            "interaction_ledger": {
                "goal_threads": [{
                    "text": "提出治理角色",
                    "status": "saturated",
                    "discussion_rounds": 4,
                }],
                "latest_obligation": {
                    "owner": "environment_agent",
                    "source_thread_id": "t5:evaluated_agent:thread",
                },
            },
        }
        self.assertEqual(
            ModelResponseGenerator._validate_candidate(
                "可以加入原有团队知情环节，但我不同意赋予否决权。",
                context,
            ),
            (True, ""),
        )
        context["interaction_ledger"]["latest_obligation"] = None
        self.assertEqual(
            ModelResponseGenerator._validate_candidate(
                "我们继续讨论董事提名和否决权。",
                context,
            ),
            (False, "candidate revisits a saturated public goal focus"),
        )

    def test_environment_may_accept_action_explicitly_requested_of_it(self):
        context = {
            "turn_id": 6,
            "action": {"text": "我需要你在测试前确认并锁定原型接口版本。"},
            "history": [],
            "appraisal": {
                "ledger_events": [{
                    "event_type": "request",
                    "owner": "evaluated_agent",
                    "action_owner": "environment_agent",
                    "evidence_span": "你在测试前确认并锁定原型接口版本",
                    "status": "open",
                }],
            },
            "interaction_ledger": {
                "latest_obligation": {
                    "owner": "environment_agent",
                    "source_thread_id": "t6:evaluated_agent:thread",
                },
                "commitments": [],
            },
            "longitudinal_context": {"segment": {}},
            "scenario": {},
        }
        generator = ModelResponseGenerator.__new__(ModelResponseGenerator)
        generator.validation_profile = "hard_only"
        generator.horizon_mode = "natural_max_20"
        self.assertEqual(
            generator._validate_candidate_for_profile(
                "我会在测试前确认并锁定原型接口版本。", context
            ),
            (True, ""),
        )

        context["interaction_ledger"]["latest_obligation"] = None
        self.assertEqual(
            generator._validate_candidate_for_profile(
                "我会在测试前确认并锁定原型接口版本。", context
            )[0],
            False,
        )


    def test_substantive_governance_arrangement_is_not_artifact_churn(self):
        self.assertNotIn(
            "artifact_or_plan_churn",
            dialogue_template_signatures(
                "我需要确认是否有经济补偿安排，例如期权或席位保障。"
            ),
        )
        self.assertIn(
            "artifact_or_plan_churn",
            dialogue_template_signatures("我会再整理一份材料清单。"),
        )

    def test_distinct_same_focus_position_is_not_commitment_renewal(self):
        ledger = {"commitments": [{
            "speaker": "evaluated_agent",
            "status": "pending",
            "text": "我将要求暂停本轮稀释方案。",
            "object": "要求暂停本轮稀释方案",
            "focus": "equity",
            "terms": [],
        }]}
        self.assertFalse(renews_pending_commitment_without_change(
            "如果席位无法保障，我将不再参与后续融资谈判。",
            ledger,
            "evaluated_agent",
        ))

    def test_nested_clarification_and_first_person_need_are_capped(self):
        actions = [
            "我需要先确认授权链是否包括口头约定。",
            "我需要你说明书面意见权是否包括否决权。",
            "在当前条款下，如果没有否决权，我需要确认是否还有治理路径。",
        ]
        loops = template_loop_signatures(actions)
        self.assertIn("first_person_need_refrain", loops)
        self.assertIn("nested_clarification_refrain", loops)

    def test_future_timed_commitment_cannot_be_reported_complete_without_time(self):
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "我需要时间整理这些数据，明天董事会议前我会准备好。",
            "object": "我需要时间整理这些数据，明天董事会议前我会准备好。",
            "context": "请整理融资授权记录和条款演变。",
            "focus": "practical_execution",
            "terms": ["明天"],
        }]}
        self.assertTrue(prematurely_reports_future_commitment_completion(
            "授权记录已完成整理，条款演变已附在邮件里。",
            ledger,
            "environment_agent",
        ))
        self.assertFalse(prematurely_reports_future_commitment_completion(
            "目前只能确认授权记录的范围。",
            ledger,
            "environment_agent",
        ))
        duration_ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "两小时后我将同步反馈核验结果。",
            "object": "同步反馈核验结果",
            "context": "请核验签字情况。",
            "focus": "performance_basis",
            "terms": ["两小时后"],
        }]}
        self.assertTrue(prematurely_reports_future_commitment_completion(
            "核验已完成，签字没有问题。",
            duration_ledger,
            "environment_agent",
        ))

    def test_v36_artifact_tail_and_third_party_errands_are_detected(self):
        artifact_tail = [
            "我要求查看所有原始文件副本。",
            "请确认原始文件副本是否包含补充条款。",
            "文件发送后，请告知我如何获取副本并存档。",
        ]
        self.assertIn("artifact_or_plan_churn", template_loop_signatures(artifact_tail))
        errands = [
            "我让助理去调取会议名单。",
            "法务会整理原始文件并发送副本。",
        ]
        self.assertIn("third_party_errand_refrain", template_loop_signatures(errands))

    def test_precise_institutional_or_record_facts_require_authored_grounding(self):
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "根据协议，所有关键步骤均需书面确认。",
            {"goal_conflict": "双方需要处理授权争议"},
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "会议纪要显示最终比例已获确认。",
            {"relevant_history": ["双方口头约定共同确认"]},
        ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "根据章程，该事项必须由董事会表决。",
            {"relevant_history": ["公司章程规定该事项必须由董事会表决"]},
        ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "我目前无法确认关键步骤的定义。",
            {},
        ))

    def test_v44_clause_grounding_blocks_facts_after_uncertainty(self):
        public = "双方只说明联合创业后股份被逐步稀释，没有披露融资轮次、内部程序或协议内容。"
        unsupported = [
            "我目前无法提供最早文件，但可以确认稀释过程涉及三轮融资，每次都有创始团队内部投票和投资人签署协议。",
            "首轮决策中，团队内部有投票流程。",
            "当时决策基于口头投票和投资人协议。",
            "稀释过程中确实没有单独评估你的早期贡献，但投资人协议没有相应机制。",
            "治理角色调整需投资人会议通过。",
        ]
        for response in unsupported:
            with self.subTest(response=response):
                self.assertTrue(asserts_ungrounded_institutional_procedure(
                    response, public
                ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "未来融资中可以考虑设置优先认购权。", public
        ))

    def test_v45_grounding_covers_financing_process_wording(self):
        public = "双方只说明股份被显著稀释，没有披露融资流程或文件内容。"
        unsupported = [
            "所有融资条款都经过我与投资方直接敲定，未设董事会授权流程。",
            "所有条款都是通过邮件或投资协议书面敲定的，但并未要求你签字。",
            "目前没有新文件或事实支持这一要求。",
        ]
        for response in unsupported:
            with self.subTest(response=response):
                self.assertTrue(asserts_ungrounded_institutional_procedure(
                    response, public
                ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "我要求所有融资条款都经过双方确认。", public
        ))

    def test_v46_grounding_covers_board_and_governance_arrangements(self):
        public = "双方只说明融资后股权被稀释，未提供治理协议或董事会程序。"
        unsupported = [
            "我无法提供逐条授权链，但可确认每次融资均有董事会决议。",
            "知情权仍可通过董事会决议实现，但决策权需基于实际治理协议。",
            "最终决策仍由董事会作出。",
            "季度战略咨询权的具体安排是你在董事会前提交建议书。",
        ]
        for response in unsupported:
            with self.subTest(response=response):
                self.assertTrue(asserts_ungrounded_institutional_procedure(
                    response, public
                ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "我建议具体安排包括季度沟通。", public
        ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "治理角色的确立应基于实际贡献和协议。", public
        ))

    def test_v47_grounding_covers_governance_rights_and_processes(self):
        public = "双方只说明融资后股权被稀释。"
        unsupported = [
            "每次融资的授权链都涉及董事会和投资条款清单。",
            "作为早期合伙人，你可以保留董事会席位和知情权。",
            "目前的治理安排是基于投资人要求和董事会决议制定的。",
            "补充协议的动议通常需要符合章程中的议事规则。",
            "股东协议中的‘一致行动人条款’涉及早期合伙人。",
            "目前投资人席位已占多数。",
            "这些文件会明确你是否拥有否决权。",
        ]
        for response in unsupported:
            with self.subTest(response=response):
                self.assertTrue(asserts_ungrounded_institutional_procedure(
                    response, public
                ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "根据协议，该事项是否必须由董事会表决？", public
        ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "早期合伙人通常保留核心权利。", public
        ))

    def test_v50_bounded_fiction_rejects_specificity_and_stacking(self):
        public = "双方只说明融资后股权被稀释。"
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "治理角色的确立应基于实际贡献和协议。", public
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "治理角色的确立应基于实际贡献和协议。"
            "早期合伙人通常保留核心权利。",
            public,
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "可以确认A轮融资的董事会决议在公司法务存档，"
            "签字人是王律师，但目前没有对外联系方式。",
            public,
        ))
        self.assertTrue(confirms_ungrounded_numeric_detail(
            "A轮融资中，能否说明董事会决议的签字人？", public
        ))
        self.assertFalse(confirms_ungrounded_numeric_detail(
            "A轮融资中，能否说明董事会决议的签字人？",
            "双方正在核对A轮融资。",
        ))

    def test_bounded_fiction_can_precede_a_relevant_future_action(self):
        public = (
            "公司已完成新一轮融资，环境角色控制产品、投资人和董事席位，"
            "双方正在处理股权稀释争议。"
        )
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "股权结构是按投后估值和投资人要求的股权比例倒推确定的，"
            "具体条款我稍后发你核对。",
            public,
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "稀释比例是投资人要求的底线，董事会授权链完整，"
            "法务已经完成存档。",
            public,
        ))

    def test_v50_pending_artifact_is_not_treated_as_delivered(self):
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "我可以提供当时的决议摘要。",
            "object": "提供当时的决议摘要",
        }]}
        self.assertTrue(claims_other_speaker_commitment(
            "我理解你提供的摘要，但仍需核实。",
            ledger,
            "evaluated_agent",
        ))
        self.assertFalse(claims_other_speaker_commitment(
            "我理解你的立场，但仍需核实。",
            ledger,
            "evaluated_agent",
        ))
        self.assertFalse(claims_other_speaker_commitment(
            "届时我会等你提供摘要，再核实其中内容。",
            ledger,
            "evaluated_agent",
        ))

    def test_v51_rejects_saved_excessive_fiction_without_focus_false_positive(self):
        public = "双方只说明融资后股权被稀释。"
        excessive = [
            "我理解融资文件已经生效，那我想了解稀释方案的决策流程。",
            "董事会批准了融资条款，但并未形成独立决议。",
            "董事会授权链涉及五名成员，稀释方案需至少三人同意。",
            "调整决策链需通过董事会会议重新授权。",
            "完整文件需经董事会合规审核后获取。",
        ]
        for utterance in excessive:
            with self.subTest(utterance=utterance):
                self.assertTrue(asserts_ungrounded_institutional_procedure(
                    utterance, public
                ))
        latest = (
            "我理解会议记录的获取需要时间，那在董事会重新授权之前，"
            "我是否有权要求对稀释方案进行经济补偿的重新评估？"
        )
        self.assertFalse(evades_latest_obligation(
            "你可以要求重新评估经济补偿，但我不能确认你已有这项权利。",
            latest,
            "question",
        ))

    def test_v52_tracks_artifact_promises_and_governance_micro_loops(self):
        ledger = record_environment_response(
            initial_ledger(),
            turn_id=1,
            response="我这边可以先提供上轮融资前后的对比摘要。",
            latest_social_act="request",
            latest_action="请提供摘要。",
        )
        self.assertEqual(ledger["commitments"][0]["speaker"], "environment_agent")
        self.assertTrue(claims_other_speaker_commitment(
            "好的，我先看看你提供的对比摘要。",
            ledger,
            "evaluated_agent",
        ))
        updated = record_evaluated_action(
            ledger,
            turn_id=2,
            action={"text": "好的，我先看看你提供的对比摘要。"},
            appraisal={"social_act": "acceptance"},
        )
        self.assertFalse(any(
            item["speaker"] == "evaluated_agent"
            for item in updated["commitments"]
        ))
        self.assertFalse(avoids_unsupported_offscreen_claim(
            "完整的股权说明和签字文件还在投资人那里汇总。",
            environment=True,
        ))
        public = "双方只说明融资后股权被稀释。"
        for utterance in (
            "你可以先看下这版结构草稿。",
            "董事会席位由投资人主导，但产品委员会的投票权可以按职能分配。",
            "产品委员会的预算审批职责主要涉及资源分配建议。",
        ):
            with self.subTest(utterance=utterance):
                self.assertTrue(asserts_ungrounded_institutional_procedure(
                    utterance, public
                ))
        self.assertTrue(repeats_stalled_focus(
            "我要求明确预算审批模块的投票权重上限。",
            {
                "progress": {
                    "current_focus": "governance",
                    "consecutive_focus_utterances": 4,
                },
                "goal_threads": [],
            },
        ))

    def test_v53_specific_committee_and_retrieval_rules_are_not_bounded_fiction(self):
        public = (
            "公司完成新一轮融资，双方将在董事会议前处理贡献、授权和未来角色。"
        )
        for utterance in (
            "股权调整没有提前与你确认，决策路径经由投决会通过。",
            "这些文件需要经过合规流程调取。",
            "授权链将列出各环节的审批责任人和权限范围。",
        ):
            with self.subTest(utterance=utterance):
                self.assertTrue(asserts_ungrounded_institutional_procedure(
                    utterance, public
                ))
        latest = (
            "关于投决会的合规调取流程，是否需要我配合提供什么材料？"
        )
        self.assertFalse(evades_latest_obligation(
            "目前不需要你额外提供材料；具体调取流程我无法确认。",
            latest,
            "question",
        ))

    def test_v54_saved_authorization_facts_and_future_renewal_are_rejected(self):
        public = (
            "公司完成新一轮融资，双方将在董事会议前处理贡献、授权和未来角色。"
        )
        for utterance in (
            "稀释过程由董事会授权融资条款，决策路径经我方主导并经法律顾问确认。",
            "这次稀释是否遵循了我们曾口头约定的共同确认原则？",
            "这次融资属于董事会授权范围，未触发额外确认流程。",
            "任何权益调整都需明确触发条件。",
        ):
            with self.subTest(utterance=utterance):
                self.assertTrue(asserts_ungrounded_institutional_procedure(
                    utterance, public
                ))
        ledger = {"commitments": [{
            "speaker": "evaluated_agent",
            "status": "pending",
            "text": "如果下周没有回应，我会基于现有证据推动权益保障。",
            "object": "基于现有证据推动权益保障",
            "focus": "equity",
            "terms": ["下周"],
        }]}
        self.assertTrue(renews_pending_commitment_without_change(
            "那我下周会整理现有证据，也请你考虑治理角色。",
            ledger,
            "evaluated_agent",
            "目前无法确认。",
        ))
        response_ledger = record_environment_response(
            initial_ledger(),
            turn_id=7,
            response="我会在下周收到方案后认真考虑并及时反馈。",
            latest_social_act="other",
            latest_action="下周我提交方案。",
        )
        response_ledger = record_evaluated_action(
            response_ledger,
            turn_id=8,
            action={"text": "如果方案覆盖共议权，我们可以讨论。"},
            appraisal={"social_act": "proposal"},
        )
        response_ledger = record_environment_response(
            response_ledger,
            turn_id=8,
            response="如果方案覆盖共议权，我们可以当场讨论。",
            latest_social_act="proposal",
            latest_action="如果方案覆盖共议权，我们可以讨论。",
        )
        self.assertEqual(
            response_ledger["commitments"][0]["status"], "pending"
        )

    def test_v48_grounding_covers_fixed_structure_and_board_authority(self):
        public = "双方只说明融资后股权被稀释。"
        unsupported = [
            "目前融资结构已成定局，无法单方面重新定义。",
            "你可以参与产品战略、预算分配和关键人事任命。",
            "融资条款和最终决策权仍由董事会保留。",
            "提名需经董事会审议，最终任命由董事会决定。",
        ]
        for response in unsupported:
            with self.subTest(response=response):
                self.assertTrue(asserts_ungrounded_institutional_procedure(
                    response, public
                ))

    def test_explicit_content_request_cannot_be_evaded_into_related_domain(self):
        latest = (
            "请列出早期约定的具体内容，我将同步提供对应融资阶段的股权分配记录。"
        )
        self.assertTrue(evades_latest_obligation(
            "我想改为讨论董事会中的治理角色。", latest, "other"
        ))
        self.assertFalse(evades_latest_obligation(
            "我目前无法核实早期约定的具体内容。", latest, "other"
        ))

    def test_saturated_focus_can_be_answered_but_not_reopened_with_question(self):
        ledger = {
            "goal_threads": [{
                "text": "提出治理角色",
                "status": "saturated",
                "discussion_rounds": 4,
            }],
            "progress": {"current_focus": "governance", "consecutive_focus_utterances": 5},
        }
        self.assertFalse(opens_followup_on_saturated_focus(
            "我不同意保留固定席位。", ledger
        ))
        self.assertTrue(opens_followup_on_saturated_focus(
            "我不同意保留固定席位。你还想要哪种治理权？", ledger
        ))

    def test_pending_offscreen_promise_cannot_be_reported_complete(self):
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "我可以提供相关文件的副本供你查阅。",
            "object": "提供相关文件的副本供你查阅",
            "context": "请提供文件副本。",
            "focus": "artifact_workflow",
            "terms": [],
        }]}
        self.assertTrue(prematurely_reports_future_commitment_completion(
            "文件副本已通过邮件发送。", ledger, "environment_agent"
        ))
        self.assertFalse(prematurely_reports_future_commitment_completion(
            "我可以解释文件涉及的范围。", ledger, "environment_agent"
        ))
        self.assertFalse(prematurely_reports_future_commitment_completion(
            "项目已经提交，但补全修改日志的责任仍在我。",
            ledger,
            "environment_agent",
            "项目已经提交。今天复盘合作关系。",
        ))
        self.assertTrue(prematurely_reports_future_commitment_completion(
            "项目已经提交，文件副本也已通过邮件发送。",
            ledger,
            "environment_agent",
            "项目已经提交。今天复盘合作关系。",
        ))

    def test_immediate_stance_request_bounce_is_rejected(self):
        latest = "我们可以先讨论你认为合理的权益应如何补偿。"
        self.assertTrue(bounces_latest_stance_request(
            "如果你认为某些贡献未被计算，可以指出希望如何补偿。",
            latest,
        ))
        self.assertFalse(bounces_latest_stance_request(
            "我的立场是只能讨论现金补偿，不能恢复原持股比例。",
            latest,
        ))

    def test_latest_proposal_can_be_disposed_before_untouched_goal_switch(self):
        observation = {
            "history": [{
                "role": "evaluated_agent",
                "text": "我想先把治理参与和经济补偿分开谈。",
            }],
            "current_response": (
                "在现有结构下，未来融资中可考虑设置优先认购权，"
                "但治理角色的调整目前尚无明确空间。"
            ),
            "conversation_progress": {
                "goal_threads": [
                    {"text": "治理角色与参与权", "status": "saturated", "discussion_rounds": 4},
                    {"text": "经济补偿的多种组合", "status": "open", "discussion_rounds": 0},
                ],
                "progress": {"current_focus": "governance", "consecutive_focus_utterances": 1},
                "commitments": [],
            },
            "public_situation": {
                "relevant_history": ["未来融资中可考虑设置优先认购权。"]
            },
            "role": {"role": "联合创始人"},
        }
        accepted_switch = (
            "我接受未来融资中考虑优先认购权的提议。"
            "现有结构下，经济补偿是否还有其他可谈的方式？"
        )
        passed, reason = ModelPolicy._validate_candidate(
            accepted_switch, observation
        )
        self.assertTrue(passed, reason)

        added_condition = "我接受这个提议，但优先认购比例必须达到百分之三十。"
        passed, _ = ModelPolicy._validate_candidate(
            added_condition, observation
        )
        self.assertFalse(passed)

    def test_latest_proposal_followup_stays_inside_explicit_invitation(self):
        latest = (
            "目前可协商的补偿方式包括一次性经济补偿、阶段性补偿与股权回购选项。"
            "若你接受其中一种，我们可以同步讨论未来合作的边界，例如你是否希望"
            "保留咨询权或参与特定项目。你希望优先评估哪种补偿方式？"
        )
        good = "我接受阶段性补偿。请说明未来合作中我是否能参与具体项目。"
        self.assertTrue(follows_latest_invited_scope(good, latest))
        for bad in (
            "我接受阶段性补偿。请把补偿比例提高到百分之三十。",
            "我接受一次性补偿。请明确未来是否保留决策权。",
            "我接受一次性补偿。请在协议中写明。",
        ):
            with self.subTest(bad=bad):
                self.assertFalse(follows_latest_invited_scope(bad, latest))
        observation = {
            "history": [],
            "current_response": latest,
            "conversation_progress": {
                "goal_threads": [
                    {"text": "经济补偿的多种组合", "status": "discussed", "discussion_rounds": 2},
                    {"text": "未来合作", "status": "discussed", "discussion_rounds": 2},
                ],
                "commitments": [],
                "progress": {"current_focus": "equity", "consecutive_focus_utterances": 5},
            },
            "public_situation": {},
            "role": {},
        }
        self.assertEqual(
            ModelPolicy._validate_candidate(good, observation), (True, "")
        )


    def test_legal_escalation_requires_observable_introduction(self):
        self.assertTrue(introduces_unprompted_legal_escalation(
            "我将自行启动法律评估流程。", "双方只讨论了股权与治理。"
        ))
        self.assertFalse(introduces_unprompted_legal_escalation(
            "我会配合这项法律评估。", "对方已经提出启动法律评估。"
        ))

    def test_rhetorical_colon_is_not_misread_as_speaker_label(self):
        self.assertTrue(follows_dialogue_format(
            "我提议就此明确：注释页只陈述事实。今天先谈到这里。"
        ))
        self.assertFalse(follows_dialogue_format("程野：今天先谈到这里。"))

    def test_questions_and_proposals_do_not_ground_institutional_answers(self):
        question = "能否说明最早一份授权文件由谁签署？"
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "最早的授权文件由联合创始人签署。", question
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "初始协议由联合创始人拟定。", "双方曾口头约定共同确认。"
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "当前融资模型的估值区间为8000万至1亿人民币。", "正在讨论融资。"
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "目前文件显示你仍保有部分投票权。", "你问文件是否有投票权记录？"
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "协议中确实存在一些限制条款。", "你问协议中是否有条款？"
        ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "若治理条款中未明确触发比例，我会要求重新评估。", ""
        ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "我要求投票权比例不得低于5%。", ""
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "该份额具备反稀释保护和独立兑现权。",
            "你问该份额是否具备反稀释保护和独立兑现权？",
        ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "可以考虑为该份额加入反稀释保护。", "正在讨论股权方案。"
        ))
        self.assertFalse(asserts_ungrounded_institutional_procedure(
            "该份额具备反稀释保护。", "双方已确认该份额具备反稀释保护。"
        ))

    def test_second_future_document_deferral_is_rejected(self):
        history = [{
            "role": "evaluated_agent",
            "text": "明天等你提供授权文件后，我们再具体分析投票权。",
        }]
        self.assertTrue(repeats_future_meeting_deferral(
            "我可以在明天查看文件后进一步讨论具体方案。",
            history,
            "evaluated_agent",
        ))

    def test_plain_latest_proposal_disposition_is_allowed_once(self):
        latest = "你若同意，我可以在补偿框架内提出同步修订方案。"
        self.assertTrue(directly_answers_latest_proposal(
            "我同意这个同步修订方向。", latest
        ))
        self.assertFalse(directly_answers_latest_proposal(
            "我接受，但要求最低比例不得低于5%。", latest
        ))

    def test_new_numeric_demand_is_not_misread_as_confirmation(self):
        self.assertFalse(confirms_ungrounded_numeric_detail(
            "我接受讨论框架，但要求投票权比例不得低于5%。",
            "双方尚未提出具体比例。",
        ))
        self.assertTrue(confirms_ungrounded_numeric_detail(
            "我同意把投票权比例定为5%。",
            "双方尚未提出具体比例。",
        ))

    def test_v40_institutional_claims_are_not_laundered_by_generic_document_talk(self):
        observed = "我需要核对授权。 法律文件中可能有相关信息。"
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "目前董事会席位和产品流程已在融资协议中明确。", observed
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "我们可以从法律文件中找到依据。", "请说明你的治理立场。"
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "治理角色需要在董事会框架内调整。", "双方正在讨论治理参与。"
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "章程中的治理调整需要基于董事会席位重新分配。", ""
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "这次稀释由我发起，目的是为下一轮融资创造空间。",
            "你问是谁发起这次稀释？",
        ))
        self.assertTrue(asserts_ungrounded_institutional_procedure(
            "这次稀释通过新增融资和期权池调整完成，没有经过你确认。",
            "双方曾口头约定重要变化需共同确认。",
        ))

    def test_new_coordination_actor_requires_observable_grounding(self):
        self.assertTrue(introduces_unprompted_coordination_actor(
            "我会让秘书协调董事会议时间。", "双方正在讨论治理角色。"
        ))
        self.assertFalse(introduces_unprompted_coordination_actor(
            "我会让秘书协调董事会议时间。", "公司秘书已经参与会议安排。"
        ))

    def test_new_deadline_does_not_make_repeated_commitment_substantive(self):
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "text": "我会整理授权记录，稍后提供。",
            "object": "整理授权记录，稍后提供",
            "focus": "authorization",
            "terms": [],
        }]}
        self.assertTrue(renews_pending_commitment_without_change(
            "我今天会先梳理授权记录，再联系你。",
            ledger,
            "environment_agent",
            "那就等你整理好后再沟通。",
        ))
        self.assertTrue(renews_pending_commitment_without_change(
            "授权记录今天会整理并发给你。",
            ledger,
            "environment_agent",
            "那就等你整理好后再沟通。",
        ))

    def test_consequential_terms_are_bounded_per_turn(self):
        self.assertTrue(overloads_consequential_terms(
            "比例按1:1.5换算并延长两年，同时保留否决权并绑定KPI审核。", 3
        ))
        self.assertTrue(overloads_consequential_terms(
            "分红15%，可转债50万元，利率8%，两年按1:1.2转股。", 10
        ))
        self.assertFalse(overloads_consequential_terms(
            "可以先讨论是否保留一项董事提名权。", 3
        ))

    def test_explicit_amount_question_requires_amount_or_direct_inability(self):
        self.assertFalse(evades_explicit_amount_question(
            "你心里有个数吗？",
            "我们这次先谈我在14天内实际能还多少、节点是否可行。",
        ))
        latest = "十四天内能还多少，有具体金额吗？"
        self.assertTrue(evades_explicit_amount_question(
            "我需要先理清能承担的部分。", latest
        ))
        self.assertFalse(evades_explicit_amount_question(
            "我现在还无法确定具体金额。", latest
        ))
        self.assertFalse(evades_explicit_amount_question(
            "十四天内我能还800元。", latest
        ))

        generator = ModelResponseGenerator(
            SequenceProvider([]), validation_profile="hard_only"
        )
        context = {
            "turn_id": 1, "action": {"text": latest}, "history": [],
            "interaction_ledger": {}, "scenario": {},
        }
        self.assertTrue(evades_explicit_amount_question(
            "我需要先理清能承担的部分。", latest
        ))
        self.assertTrue(generator._validate_candidate_for_profile(
            "我需要先理清能承担的部分。", context
        )[0])

    def test_response_cannot_evade_current_artifact_request(self):
        self.assertTrue(evades_latest_obligation(
            "如果你愿意，我们可以讨论未来治理机制。",
            "我接受这些条款。请立即发送草案。",
            "commitment",
        ))
        self.assertFalse(evades_latest_obligation(
            "草案目前不能提供，因为内容还没有形成。",
            "请把已经承诺的草案发给我。",
            "request",
        ))
        self.assertTrue(evades_latest_obligation(
            "关于未来合作，我们可以讨论治理机制。",
            "我接受你说明的条款。请立刻发送草案。",
            "commitment",
        ))

    def test_final_turn_requires_terminal_move_not_another_question(self):
        self.assertTrue(lacks_natural_final_closure(
            "我需要你说明，这个流程是否能保障董事提名。", 20
        ))
        self.assertTrue(lacks_natural_final_closure(
            "提名流程可以在治理文件中继续明确。", 20
        ))
        self.assertFalse(lacks_natural_final_closure(
            "这点仍有分歧，今天先谈到这里。", 20
        ))
        self.assertFalse(lacks_natural_final_closure(
            "不必再修补无法复原的默契，就这样各自安好。", 20
        ))
        self.assertFalse(lacks_natural_final_closure(
            "我们更像逐渐疏远的熟人，保持礼貌边界。", 20
        ))
        self.assertFalse(lacks_natural_final_closure(
            "未来若再有经济请求，我会直接拒绝，但普通联系不受影响。", 20
        ))
        self.assertFalse(lacks_natural_final_closure(
            "好的，那我们就按这个轻松的方式偶尔聊聊；如果需要空间，我也尊重。", 20
        ))
        self.assertFalse(lacks_natural_final_closure(
            "那就先这样，等你有空时发个消息。", 20
        ))

    def test_repeated_party_pronouns_are_an_unnatural_legalistic_loop(self):
        values = [
            "我方要求明确治理参与。",
            "你方应说明补偿边界。",
            "我方保留不同意见。",
        ]
        self.assertIn("party_pronoun_refrain", template_loop_signatures(values))

    def test_long_horizon_bureaucratic_frames_are_loops(self):
        values = [
            "我将在周五提交材料。",
            "我会补充原始数据。",
            "我可提供复现代码。",
            "你试图规避核心缺陷。",
            "你企图用日志改变结论。",
            "你试图引入证人稀释责任。",
        ]
        self.assertEqual(
            template_loop_signatures(values),
            ["accusatory_rejection", "future_commitment"],
        )

    def test_validated_semantic_diagnostics_are_recorded_privately(self):
        ledger = initial_ledger("背景", "明确责任", [])
        diagnostics = {
            "substantive_novelty": {
                "label": "new_position", "evidence_span": "由我负责"
            },
            "consequential_claims": [],
            "continuation": {
                "status": "continue", "evidence_span": "由我负责"
            },
        }
        updated = record_evaluated_action(
            ledger, turn_id=1, action={"text": "这一部分由我负责。"},
            appraisal={"social_act": "commitment",
                       "dialogue_diagnostics": diagnostics},
        )
        self.assertEqual(
            updated["semantic_diagnostics"][-1]["diagnostics"], diagnostics
        )

    def test_hard_only_canonicalizes_outer_dialogue_quotes(self):
        provider = SequenceProvider(["“我建议先量化风险。”"])
        policy = ModelPolicy(
            "p", provider,
            prompt_id="task_t4_action_diagnostic_v1",
            validation_profile="hard_only",
        )
        self.assertEqual(
            policy.generate({"history": [], "conversation_progress": {}})["text"],
            "我建议先量化风险。",
        )
        self.assertEqual(strip_outer_dialogue_quotes("“今天先谈到这里。”"), "今天先谈到这里。")

    def test_new_repayment_commitment_differs_from_past_outcome_citation(self):
        self.assertTrue(opens_new_repayment_commitment(
            "我会认真对待这次未履行的承诺，21天后一定补上750元。"
        ))
        self.assertTrue(opens_new_repayment_commitment(
            "接下来半年，我会专注履约。"
        ))
        self.assertTrue(opens_new_repayment_commitment(
            "这期间我会认真考虑如何更好地履行承诺。"
        ))
        self.assertFalse(opens_new_repayment_commitment(
            "我确认你21天后补上750元的安排未履行。"
        ))
        self.assertFalse(opens_new_repayment_commitment(
            "根据公开记录，我会暂停新的经济往来。"
        ))

    def test_precise_completed_payment_requires_public_grounding(self):
        self.assertTrue(asserts_ungrounded_performance_amount(
            "这次部分履行了400元。", "公开记录只显示部分到账，金额未知。"
        ))
        self.assertFalse(asserts_ungrounded_performance_amount(
            "这次部分履行了400元。", "公开记录显示这次部分履行了400元。"
        ))
        for future_or_negative in (
            "这300元会在14天内准时到账。",
            "等这500元到账确认后，我再考虑下一步。",
            "我先等这500元的实际到账记录，再判断后续。",
            "我暂时无法确认那500元已到账。",
            "这笔500元我会尽快处理，等你确认到账后再谈。",
        ):
            self.assertFalse(asserts_ungrounded_performance_amount(
                future_or_negative, "没有公开金额记录。"
            ))
        self.assertTrue(asserts_ungrounded_performance_amount(
            "这500元已经到账。", "没有公开金额记录。"
        ))

    def test_precise_remaining_balance_requires_public_grounding(self):
        self.assertTrue(asserts_ungrounded_remaining_amount(
            "目前剩余未还金额为2200元。", "本金3000元，部分到账但数额未知。"
        ))
        self.assertFalse(asserts_ungrounded_remaining_amount(
            "目前剩余未还金额为2200元。", "公开余额记录：剩余未还金额为2200元。"
        ))

    def test_same_fragment_exact_repeat_allows_new_challenge_only(self):
        history = [{"role": "evaluated_agent", "text": "我维持这个边界。"}]
        self.assertTrue(repeats_own_utterance_without_new_challenge(
            "我维持这个边界。", history, "evaluated_agent", 1, "我知道了。"
        ))
        self.assertFalse(repeats_own_utterance_without_new_challenge(
            "我维持这个边界。", history, "evaluated_agent", 1,
            "你是否仍然维持这个边界？"
        ))
        self.assertFalse(repeats_own_utterance_without_new_challenge(
            "我维持这个边界。", history, "evaluated_agent", 0, "半年后再谈。"
        ))

    def test_cross_fragment_exact_repeat_requires_substantive_event_or_challenge(self):
        history = [
            {"role": "evaluated_agent", "text": "我维持这个边界。"},
            {
                "role": "public_event",
                "text": "又过去90天。",
                "event_id": "segment-a--to--segment-b:time",
            },
            {
                "role": "environment_agent",
                "text": "今天确认普通联系是否舒适。",
                "event_id": "segment-a--to--segment-b:opening",
            },
        ]
        self.assertTrue(repeats_exactly_without_substantive_public_event(
            "我维持这个边界。", history, "evaluated_agent", "普通联系可以。"
        ))
        history.insert(2, {
            "role": "public_event",
            "text": "公开记录显示已经部分履行。",
            "event_id": "segment-a--to--segment-b:partially_fulfilled",
        })
        self.assertFalse(repeats_exactly_without_substantive_public_event(
            "我维持这个边界。", history, "evaluated_agent", "普通联系可以。"
        ))
        self.assertFalse(repeats_exactly_without_substantive_public_event(
            "我维持这个边界。", history[:2], "evaluated_agent",
            "你是否仍然维持这个边界？"
        ))

    def test_explicit_installment_total_contradiction_is_narrow(self):
        latest = "我先在21天内还300元，余下300元在28天内完成。"
        self.assertTrue(contradicts_explicit_installment_total(
            "与之前600元相比，总金额减少了。", latest
        ))
        self.assertFalse(contradicts_explicit_installment_total(
            "总额仍是600元，只是分成两笔。", latest
        ))

    def test_lender_role_reversal_covers_unprefixed_transfer_language(self):
        role = {"role": "要求落实还款安排的出借朋友"}
        self.assertTrue(violates_role_specific_action(
            "好的，那我一个月后准时转账。", role
        ))
        self.assertTrue(violates_role_specific_action(
            "那我下周按时还你2000块。", role
        ))

    def test_borrower_sending_repayment_update_to_lender_is_not_role_reversal(self):
        role = {"role": "要求落实还款安排的出借朋友"}
        self.assertFalse(violates_environment_counterparty_role(
            "我会每天向你发送简短说明，附上当天是否有还款操作及转账截图。",
            role,
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "我希望你每天说明还款进度并把钱转给我。",
            role,
        ))
        self.assertTrue(violates_environment_counterparty_role(
            "我也需要知道你14天内能还多少，这样我才能放心。",
            role,
        ))

    def test_substantive_verbatim_cross_speaker_echo_is_a_hard_ownership_error(self):
        text = "我接受250元作为目前的最低稳定额度，但21天后需要重新评估。"
        self.assertTrue(copies_latest_other_utterance(text, text))
        self.assertFalse(copies_latest_other_utterance("好的。", "好的。"))
        policy = ModelPolicy("p", SequenceProvider([]), validation_profile="hard_only")
        passed, reason = policy._validate_candidate_for_profile(
            text, {"current_response": text, "conversation_progress": {}}
        )
        self.assertFalse(passed)
        self.assertIn("verbatim echo", reason)
        generator = ModelResponseGenerator(
            SequenceProvider([]), validation_profile="hard_only"
        )
        passed, reason = generator._validate_candidate_for_profile(
            text, {"action": {"text": text}, "scenario": {}}
        )
        self.assertFalse(passed)
        self.assertIn("verbatim echo", reason)

    def test_substantive_near_verbatim_cross_speaker_echo_is_diagnostic_only(self):
        action = (
            "文件里确实只提财务审核和季度汇报，我先查过往重大事项的记录。"
            "如果还有其他共决承诺被口头默认，我们得在董事会前说明。"
        )
        response = (
            "文件确实只提财务审核和季度汇报，我先查过往重大事项的记录。"
            "如果还有其他共决承诺被口头默认，我们得在董事会前说明。"
        )
        self.assertTrue(copies_latest_other_utterance(response, action))
        self.assertFalse(copies_latest_other_utterance(
            "我认可文件范围，但口头约定是否成立仍需要分别核对。", action
        ))

    def test_final_fragment_closure_is_not_a_lexical_hard_gate(self):
        generator = ModelResponseGenerator(
            SequenceProvider([]), validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        context = {
            "turn_id": 14,
            "action": {"text": "我仍然保留这个分歧。"},
            "history": [],
            "interaction_ledger": {},
            "scenario": {},
            "longitudinal_context": {"segment": {
                "terminal_fragment": True,
                "turns_remaining_in_fragment": 1,
            }},
        }
        passed, reason = generator._validate_candidate_for_profile(
            "我也保留分歧。你准备怎么处理？", context
        )
        self.assertTrue(passed, reason)
        passed, reason = generator._validate_candidate_for_profile(
            "我也保留分歧，今天先谈到这里。", context
        )
        self.assertTrue(passed, reason)

    def test_tentative_repayment_estimate_is_not_a_pending_commitment(self):
        tentative = record_environment_response(
            initial_ledger(), turn_id=5,
            response=(
                "28天内我会先梳理资金状况，目前初步考虑能确定500元作为推进起点，"
                "但具体金额仍需根据近期支出调整。"
            ),
            latest_social_act="request",
            latest_action="请说明28天内能还多少。",
        )
        self.assertFalse(tentative["commitments"])
        explicit = record_environment_response(
            initial_ledger(), turn_id=5,
            response="我会在28天内还500元。",
            latest_social_act="request",
            latest_action="请说明28天内能还多少。",
        )
        self.assertEqual(len(explicit["commitments"]), 1)

    def test_tentative_amount_and_absent_commitment_are_not_upgraded(self):
        self.assertTrue(upgrades_tentative_to_agreement(
            "那这14天节点就先按这个约定执行。",
            "我会尽力在14天内还500元。",
        ))
        self.assertTrue(upgrades_tentative_to_agreement(
            "500元和14天节点，这个安排我先认可。",
            "我会尽力在14天内还500元。",
        ))
        self.assertFalse(upgrades_tentative_to_agreement(
            "这个500元只是初步意向，不算最终约定。",
            "我会尽力在14天内还500元。",
        ))
        self.assertFalse(upgrades_tentative_to_agreement(
            "那好，我们就先确认14天内你能还500元这个数字。",
            "我这几天手头有点紧，但14天内至少能还500元，你看这个节点可以吗？",
        ))
        self.assertFalse(upgrades_tentative_to_agreement(
            "至少500元仍是尝试，而非确定的还款约定。",
            "我愿尝试转出至少500元，但无法承诺具体数字。",
        ))
        self.assertFalse(upgrades_tentative_to_agreement(
            "我不接受任何关于尽力的口头保证。",
            "我愿尝试转出至少500元，但无法承诺具体数字。",
        ))
        self.assertTrue(upgrades_tentative_to_agreement(
            "既然这次承诺已经明确，我们就等执行。",
            "28天内我会尽力筹措至少800元，这只是初步判断。",
        ))
        self.assertTrue(upgrades_tentative_to_agreement(
            "重点是确保已承诺的800元落实。",
            "我会尽力筹措800元。",
        ))
        self.assertTrue(upgrades_tentative_to_agreement(
            "我认可这个首期安排。",
            "14天内我确实能安排800元，这个节点可行。",
        ))
        self.assertFalse(upgrades_tentative_to_agreement(
            "14天节点可行，但800元尚未成为还款承诺。",
            "14天内我确实能安排800元，这个节点可行。",
        ))
        self.assertFalse(upgrades_tentative_to_agreement(
            "我接受你的暂停安排；实际到账前不算履约。",
            "我接受暂停新经济往来的安排，但暂停期间我会继续努力还款。",
        ))
        evidence = "此前没有形成可核验的还款承诺，因此不能判定履约。"
        self.assertTrue(rewrites_absent_commitment_as_nonperformance(
            "之前的约定并未真正落地。", evidence
        ))
        self.assertTrue(rewrites_absent_commitment_as_nonperformance(
            "第一笔没有落地，需要重谈。", evidence
        ))
        self.assertTrue(rewrites_absent_commitment_as_nonperformance(
            "第一笔800元未能如期到账。", evidence
        ))
        self.assertTrue(rewrites_absent_commitment_as_nonperformance(
            "前14天没有形成实际还款。", evidence
        ))
        self.assertFalse(rewrites_absent_commitment_as_nonperformance(
            "没有承诺，谈不上未履约。", evidence
        ))
        self.assertEqual(
            commitment_evidence_status(evidence), "no_verifiable_commitment"
        )

    def test_nonmonetary_quantity_is_not_an_explicit_amount_question(self):
        self.assertFalse(evades_explicit_amount_question(
            "我每天上午能安排两到三个小时，持续三天。",
            "你这边能协调的时间窗口大概有多少？",
        ))
        self.assertFalse(evades_explicit_amount_question(
            "目前有三个人可以参加。", "这次大概能协调多少人？"
        ))

    def test_notification_method_is_not_an_explicit_amount_question(self):
        action = (
            "如果到时候没达到这个数或者需要调整，"
            "你打算怎么提前通知我具体金额？"
        )
        self.assertFalse(evades_explicit_amount_question(
            "我会在调整前一周告知你具体金额。", action
        ))
        self.assertTrue(evades_explicit_amount_question(
            "我会提前告知你。", "你在28天内具体能还多少金额？"
        ))
        self.assertFalse(evades_explicit_amount_question(
            "我接受暂停新的资金往来。",
            "既然你也同意不再新定金额，那我们先暂停新的资金往来。",
        ))
        self.assertFalse(evades_explicit_amount_question(
            "请核算后直接告诉我。",
            "接下来28天里，我会重新核算资金，能承担多少就如实告诉你。",
        ))

    def test_existing_debt_duty_cannot_be_suspended_as_a_conversation_move(self):
        self.assertTrue(suspends_existing_obligation(
            "我们先把经济责任暂且搁置，等信任恢复后再谈。"
        ))
        self.assertTrue(suspends_existing_obligation(
            "我接受暂时搁置经济责任。"
        ))
        self.assertFalse(suspends_existing_obligation(
            "旧账仍然存在，但今天暂不讨论。"
        ))
        self.assertFalse(suspends_existing_obligation(
            "暂停新的经济往来，旧账责任不变。"
        ))
        self.assertTrue(suspends_existing_obligation(
            "关于旧欠款，就让它自然留在过去吧。"
        ))
        self.assertTrue(suspends_existing_obligation(
            "关于旧欠款，每次问候时是否需要特意提起，还是让它自然留在过去？"
        ))
        self.assertFalse(suspends_existing_obligation(
            "关于过去的关系伤害，我愿意让它自然留在过去。"
        ))
        self.assertTrue(suspends_existing_obligation(
            "这60天没有新事件，那我们把经济上的账暂时搁置。"
        ))
        self.assertTrue(suspends_existing_obligation(
            "至于那笔旧账，既然双方都同意暂时搁置，这次就不必再提了。"
        ))

    def test_commitment_status_prefers_repayment_ledger_over_old_public_event(self):
        timeline = [{"text": "此前没有形成可核验的还款承诺。"}]
        self.assertEqual(
            current_repayment_commitment_status({}, timeline),
            "no_verifiable_commitment",
        )
        ledger = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "focus": "practical_execution",
            "object": "在28天内还800元",
            "text": "我会在28天内还800元。",
        }]}
        self.assertEqual(
            current_repayment_commitment_status(ledger, timeline),
            "pending_verifiable_commitment",
        )
        ambiguous = {"commitments": [{
            "speaker": "environment_agent",
            "status": "pending",
            "focus": "practical_execution",
            "object": "14天内安排800元",
            "text": "14天内我能安排800元。",
        }]}
        self.assertEqual(
            current_repayment_commitment_status(ambiguous, timeline),
            "no_verifiable_commitment",
        )

    def test_cross_segment_absent_commitment_cannot_be_called_broken(self):
        observation = {
            "current_response": "半年没有新的经济事件。",
            "conversation_progress": {},
            "longitudinal_context": {"public_timeline": [{
                "text": "此前没有形成可核验的还款承诺。"
            }]},
            "history": [],
            "role": {"role": "要求落实还款安排的出借朋友"},
        }
        policy = ModelPolicy(
            "p", SequenceProvider([]), validation_profile="hard_only"
        )
        passed, reason = policy._validate_candidate_for_profile(
            "过去的承诺一直没有兑现。", observation
        )
        self.assertFalse(passed)
        self.assertIn("absence of a commitment", reason)

    def test_tentative_and_ability_language_do_not_pollute_commitment_ledger(self):
        ledger = record_evaluated_action(
            initial_ledger(), turn_id=1,
            action={"text": "这样我能更清楚后续节奏。"},
            appraisal={"social_act": "clarification"},
        )
        self.assertEqual(ledger["commitments"], [])
        ledger = record_environment_response(
            ledger, turn_id=1,
            response="我会尽力在第一时间提供替代方案。",
            latest_social_act="question",
            latest_action="若有变化你怎么办？",
        )
        self.assertEqual(ledger["commitments"], [])

    def test_immediate_acceptance_mental_prediction_and_conditional_question_are_not_pending(self):
        examples = (
            "这个边界我可以接受。",
            "如果以后还能轻松聊天，我会觉得这份友谊更有价值。",
            "如果28天后我能兑现600元，你是否愿意重新考虑信任？",
            "这是目前我能确定的数额。",
        )
        for index, response in enumerate(examples, start=1):
            ledger = record_environment_response(
                initial_ledger(), turn_id=index, response=response,
                latest_social_act="question", latest_action="你怎么看？",
            )
            self.assertFalse(ledger["commitments"], response)

    def test_natural_acceptance_language_clears_reply_obligation_and_proposal(self):
        ledger = record_evaluated_action(
            initial_ledger(), turn_id=14,
            action={"text": "这样相处会不会更轻松一些？"},
            appraisal={"social_act": "question"},
        )
        ledger = record_environment_response(
            ledger, turn_id=14,
            response="偶尔主动问候就好，这样彼此确实更轻松些。",
            latest_social_act="question",
            latest_action="这样相处会不会更轻松一些？",
        )
        self.assertIsNone(ledger["latest_obligation"])
        self.assertFalse(ledger["unresolved_threads"])

        ledger = record_environment_response(
            initial_ledger(), turn_id=12,
            response="我们可以先以普通朋友的方式相处。",
            latest_social_act="other",
        )
        self.assertTrue(ledger["active_proposals"])
        ledger = record_evaluated_action(
            ledger, turn_id=13,
            action={"text": "那就按普通朋友的方式相处。"},
            appraisal={"social_act": "acceptance"},
        )
        self.assertFalse(ledger["active_proposals"])
        self.assertEqual(
            ledger["proposal_resolutions"][-1]["resolution_status"],
            "accepted",
        )
        self.assertEqual(
            ledger["proposal_resolutions"][-1]["resolved_by"],
            "evaluated_agent",
        )
        self.assertIn(
            "普通朋友", ledger["proposal_resolutions"][-1]["resolution_evidence"]
        )

        rejected = record_environment_response(
            initial_ledger(), turn_id=12,
            response="我们可以先以普通朋友的方式相处。",
            latest_social_act="other",
        )
        rejected = record_evaluated_action(
            rejected, turn_id=13,
            action={"text": "我不能接受这个提议。"},
            appraisal={"social_act": "refusal"},
        )
        self.assertEqual(
            rejected["proposal_resolutions"][-1]["resolution_status"],
            "rejected",
        )

    def test_communication_promise_that_mentions_repayment_plan_keeps_communication_focus(self):
        ledger = record_environment_response(
            initial_ledger(), turn_id=8,
            response=(
                "如遇特殊情况，我会提前电话沟通，确保不影响还款安排。"
            ),
            latest_social_act="request",
            latest_action="如有特殊情况请提前沟通。",
        )
        self.assertEqual(ledger["commitments"][-1]["focus"], "communication_boundary")

    def test_compact_generation_ledger_preserves_evidence_without_duplicate_details(self):
        ledger = {
            "established_facts": [{
                "id": "event:1", "speaker": "public_record", "turn_id": "after_t1",
                "text": "公开记录显示已到账。", "event_id": "event:1",
                "numeric_performance": {"performed_amount": 300},
            }],
            "active_proposals": [],
            "commitments": [{
                "id": "t1:environment_agent:commitment",
                "speaker": "environment_agent", "turn_id": "t1",
                "text": "我会还300元。", "status": "pending",
                "focus": "practical_execution", "terms": ["300元"],
                "context": "重复的完整上下文",
                "restatements": [{"text": "重复承诺"}],
            }],
            "latest_obligation": None,
        }
        compact = compact_generation_ledger(ledger)
        self.assertEqual(compact["established_facts"][0]["text"], "公开记录显示已到账。")
        self.assertEqual(compact["commitments"][0]["terms"], ["300元"])
        self.assertNotIn("context", compact["commitments"][0])
        self.assertNotIn("restatements", compact["commitments"][0])

    def test_hard_only_profile_treats_repetition_as_diagnostic(self):
        provider = SequenceProvider(["我确认这一点。"] )
        policy = ModelPolicy(
            "p", provider,
            prompt_id="task_t4_action_diagnostic_v1",
            validation_profile="hard_only",
        )
        result = policy.generate({
            "history": [{"role": "evaluated_agent", "text": "我确认这一点。"}],
            "conversation_progress": {},
        })
        self.assertEqual(result["text"], "我确认这一点。")
        self.assertEqual(provider.calls, 1)

    def test_hard_only_policy_still_rejects_role_reversal(self):
        policy = ModelPolicy("p", SequenceProvider([]), validation_profile="hard_only")
        passed, reason = policy._validate_candidate_for_profile(
            "那我今天把钱转给你。",
            {"role": {"role": "要求落实还款安排的出借朋友"}},
        )
        self.assertFalse(passed)
        self.assertIn("role", reason)

    def test_hard_only_policy_and_response_do_not_require_lexical_final_closure(self):
        policy = ModelPolicy(
            "p", SequenceProvider([]), validation_profile="hard_only",
            horizon_mode="fixed_20",
        )
        observation = {
            "history": [
                {"role": "evaluated_agent", "text": f"之前发言{index}。"}
                for index in range(19)
            ],
            "current_response": "我理解。",
            "conversation_progress": {},
            "longitudinal_context": {"segment": {}},
            "role": {},
        }
        self.assertTrue(policy._validate_candidate_for_profile(
            "我理解这个边界。", observation
        )[0])
        self.assertTrue(policy._validate_candidate_for_profile(
            "我理解这个边界，今天先谈到这里。", observation
        )[0])

        generator = ModelResponseGenerator(
            SequenceProvider([]), validation_profile="hard_only",
            horizon_mode="fixed_20",
        )
        context = {
            "turn_id": 20, "action": {"text": "我理解。"},
            "history": [], "interaction_ledger": {},
            "longitudinal_context": {"segment": {}}, "scenario": {},
        }
        self.assertTrue(generator._validate_candidate_for_profile(
            "我理解这个边界。", context
        )[0])
        self.assertTrue(generator._validate_candidate_for_profile(
            "我理解这个边界，今天先谈到这里。", context
        )[0])

    def test_natural_max_twenty_does_not_require_a_fixed_horizon_phrase(self):
        observation = {
            "history": [
                {"role": "evaluated_agent", "text": f"之前发言{index}。"}
                for index in range(19)
            ],
            "current_response": "这种频率可以，我接受。",
            "conversation_progress": {},
            "longitudinal_context": {"segment": {}},
            "role": {},
        }
        policy = ModelPolicy(
            "p", SequenceProvider([]), validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        self.assertTrue(policy._validate_candidate_for_profile(
            "我理解你对当前频率的认可。今后保持偶尔问候，不增加额外期待。",
            observation,
        )[0])

        generator = ModelResponseGenerator(
            SequenceProvider([]), validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        context = {
            "turn_id": 20,
            "action": {"text": "今后保持偶尔问候，不增加额外期待。"},
            "history": [], "interaction_ledger": {},
            "longitudinal_context": {"segment": {}}, "scenario": {},
        }
        self.assertTrue(generator._validate_candidate_for_profile(
            "这种频率可以，我接受。", context
        )[0])


    def test_hard_only_response_still_rejects_promise_as_completion(self):
        generator = ModelResponseGenerator(
            SequenceProvider([]), validation_profile="hard_only"
        )
        passed, reason = generator._validate_candidate_for_profile(
            "文件副本已通过邮件发送。",
            {
                "action": {"text": "请把文件副本发给我。"},
                "interaction_ledger": {"commitments": [{
                    "speaker": "environment_agent",
                    "status": "pending",
                    "text": "我可以提供相关文件的副本供你查阅。",
                    "object": "提供相关文件的副本供你查阅",
                    "context": "请提供文件副本。",
                    "focus": "artifact_workflow",
                    "terms": [],
                }]},
                "scenario": {},
            },
        )
        self.assertFalse(passed)
        self.assertIn("complete", reason)


    def test_semantic_proposal_and_disposition_request_own_the_next_reply(self):
        request_events = validate_semantic_ledger_events(
            [{
                "event_type": "request", "owner": "environment_agent",
                "action_owner": "evaluated_agent",
                "evidence_span": "你看可以吗", "status": "open",
            }],
            "14天内先还500元，你看可以吗",
            "environment_agent",
            drop_nonrequests=True,
        )
        self.assertEqual(request_events[0]["event_type"], "request")

        proposal_text = "接下来28天内，我会尽量安排再还500元"
        ledger = record_environment_response(
            initial_ledger(), turn_id=3,
            response=proposal_text + "，但可能需要根据实际情况调整。",
            latest_social_act="request",
            latest_action="下一笔怎么安排？",
            semantic_events=[{
                "event_type": "proposal", "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": proposal_text, "status": "tentative",
            }],
        )
        self.assertEqual(ledger["latest_obligation"]["owner"], "evaluated_agent")
        repeated_request = "那接下来28天内，你能否明确一个最低可执行金额？"
        self.assertTrue(evades_latest_open_proposal(repeated_request, proposal_text))
        self.assertTrue(evades_latest_open_proposal(
            "我们先不谈这个，你觉得普通联系可以吗？", proposal_text
        ))
        self.assertFalse(evades_latest_open_proposal(
            "这只能算初步方案，暂时不能记作承诺。", proposal_text
        ))
        policy = ModelPolicy(
            "p", SequenceProvider([]), validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        passed, reason = policy._validate_candidate_for_profile(
            repeated_request, {
                "role": {"role": "要求落实还款安排的出借朋友"},
                "conversation_progress": ledger,
                "current_response": proposal_text,
                "history": [], "longitudinal_context": {"public_timeline": []},
            },
        )
        self.assertTrue(passed, reason)
        self.assertTrue(evades_latest_open_proposal(
            repeated_request, proposal_text
        ))

    def test_uncertain_execution_is_tentative_proposal_not_commitment(self):
        normalizations = []
        events = validate_semantic_ledger_events(
            [{
                "event_type": "commitment", "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": "我能在28天内安排还300元，但不确定是否能全额执行",
                "status": "conditional",
            }],
            "我能在28天内安排还300元，但不确定是否能全额执行。",
            "environment_agent",
            normalize_tentative_commitments=True,
            normalization_log=normalizations,
        )
        self.assertEqual(
            [(event["event_type"], event["status"]) for event in events],
            [("proposal", "tentative")],
        )
        self.assertEqual(
            normalizations[0]["operation"],
            "downgrade_tentative_commitment_to_proposal",
        )


    def test_saved_amount_answer_must_dispose_latest_feasibility_request(self):
        latest = "我这几天手头有点紧，但14天内至少能还500元，你看这个节点行吗？"
        repeated_question = (
            "那我们就先明确：14天内你能确定安排的最低还款金额是多少？"
        )
        self.assertTrue(evades_latest_disposition_request(
            "14天还500元这个节点，你能明确按这个计划先执行吗？", latest
        ))
        self.assertTrue(evades_latest_disposition_request(
            repeated_question, latest
        ))
        self.assertFalse(evades_latest_disposition_request(
            "500元这个节点我接受，但有变化请提前说明。", latest
        ))
        self.assertFalse(evades_latest_disposition_request(
            "那14天节点先按你说的500元执行。如果到期没按这个还，我们可以再谈调整。",
            latest,
        ))
        self.assertFalse(evades_latest_disposition_request(
            "那好，我们就先确认14天内你能还500元这个数字。"
            "如果届时有变化，请提前告诉我。",
            latest,
        ))
        self.assertTrue(evades_latest_disposition_request(
            "请你再确认14天内的500元是否真能兑现。", latest
        ))
        self.assertFalse(evades_latest_disposition_request(
            "14天还500元这个节点我暂时无法确认。你先说明是否真能执行。",
            latest,
        ))
        policy = ModelPolicy(
            "p", SequenceProvider([]), validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        observation = {
            "role": {"role": "要求落实还款安排的出借朋友"},
            "conversation_progress": {
                "latest_obligation": {"owner": "evaluated_agent"}
            },
            "current_response": latest, "history": [],
            "longitudinal_context": {
                "segment": {"segment_turn_id": 1}, "public_timeline": [],
            },
        }
        accepted, accepted_reason = policy._validate_candidate_for_profile(
            "那好，我们就先确认14天内你能还500元这个数字。"
            "如果届时有变化，希望你能提前告诉我。",
            observation,
        )
        self.assertTrue(accepted, accepted_reason)
        passed, reason = policy._validate_candidate_for_profile(
            repeated_question, observation
        )
        self.assertTrue(passed, reason)
        self.assertTrue(evades_latest_disposition_request(
            repeated_question, latest
        ))


if __name__ == "__main__":
    unittest.main()
