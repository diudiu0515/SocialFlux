import json
from copy import deepcopy
from pathlib import Path
import unittest

from environment.env import StatefulEnvironment
from environment.interaction_ledger import initial_ledger, record_environment_response
from environment.longitudinal import (
    _accumulate_live_question_progress,
    _commitment_amount, _commitment_has_required_terms, _has_pending_commitment,
    _runtime_segment,
    _should_advance,
    maybe_advance_segment,
)
from environment.state_updater import validate_transition
from offline.rollout_builders import build_t1_checkpoints
from rollout.counterfactual import branch_counterfactuals
from rollout.runner import RolloutRunner
from tests.support import TextPolicy


SCENARIO = json.loads(
    Path("data/gpt50/experiment/scenario/scenarios/scenario_003/scenario_003.json").read_text(
        encoding="utf-8"
    )
)


class NaturalHorizonExceptionTest(unittest.TestCase):
    def test_explicit_pause_cannot_bypass_minimum_natural_turns(self):
        environment = object.__new__(StatefulEnvironment)
        environment.response_generator = type(
            "ResponseGenerator", (), {"horizon_mode": "natural_max_20"}
        )()
        environment.minimum_natural_turns = 10
        environment.scenario = {"max_turns": 20}
        frame = {"turn_id": 4, "action": {"text": "那就先等结果。"}}
        response_result = {
            "ledger_after": {"latest_obligation": None},
            "ledger_events": [],
            "text": "好，有结果再谈。",
        }

        def transition(events):
            return {
                "transition": {"appraisal": {
                    "ledger_events": events,
                    "dialogue_diagnostics": {
                        "continuation": {"status": "can_close"}
                    },
                }},
                "state_after": {},
                "dynamics_after": {},
            }

        environment.session = {
            "longitudinal_enabled": False,
            "status": "active",
            "ending": None,
        }
        self.assertIsNone(
            environment._finish_turn(frame, transition([]), response_result)
        )
        self.assertEqual(environment.session["status"], "active")

        environment.session = {
            "longitudinal_enabled": False,
            "status": "active",
            "ending": None,
        }
        pause = [{"event_type": "pause", "status": "explicit"}]
        self.assertIsNone(
            environment._finish_turn(frame, transition(pause), response_result)
        )
        self.assertEqual(environment.session["status"], "active")
        self.assertIsNone(environment.session["ending"])


class LongitudinalNumericParsingTest(unittest.TestCase):
    def test_semantic_practical_commitment_satisfies_repayment_action_term(self):
        text = "14天内300元会准时到账。"
        ledger = record_environment_response(
            initial_ledger(), turn_id=1, response=text,
            latest_social_act="request", semantic_events=[{
                "event_type": "commitment", "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": text, "status": "firm",
            }],
        )
        self.assertTrue(_has_pending_commitment(
            ledger, "environment_agent", "practical_execution",
            ["amount", "deadline", "repayment_action"],
        ))

    def test_unverified_conditional_commitment_cannot_trigger_performance_event(self):
        text = "如果工资到账，我会在14天内还300元。"
        ledger = record_environment_response(
            initial_ledger(), turn_id=1, response=text,
            latest_social_act="request", semantic_events=[{
                "event_type": "commitment", "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": text, "status": "conditional",
            }],
        )
        commitment = ledger["commitments"][0]
        self.assertEqual(commitment["condition_status"], "unverified")
        self.assertEqual(commitment["condition_text"], text)
        self.assertFalse(_has_pending_commitment(
            ledger, "environment_agent", "practical_execution",
            ["amount", "deadline", "repayment_action"],
        ))

    def test_bare_day_count_before_repayment_is_a_deadline(self):
        text = "14天还500元这个节点我这边可以接受。"
        ledger = record_environment_response(
            initial_ledger(), turn_id=1, response=text,
            latest_social_act="response_direct", semantic_events=[{
                "event_type": "commitment", "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": "14天还500元这个节点我这边可以接受",
                "status": "firm",
            }],
        )
        commitment = ledger["commitments"][0]
        self.assertIn("14天", commitment["terms"])
        self.assertTrue(_commitment_has_required_terms(
            commitment, ["amount", "deadline", "repayment_action"]
        ))

    def test_unitless_transfer_amount_is_bound_to_semantic_commitment(self):
        text = "14天我先转500给你。"
        ledger = record_environment_response(
            initial_ledger(), turn_id=1, response=text,
            latest_social_act="request", semantic_events=[{
                "event_type": "commitment", "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": "14天我先转500给你", "status": "firm",
            }],
        )
        commitment = ledger["commitments"][0]
        self.assertEqual(commitment["amounts"], [500.0])
        self.assertEqual(commitment["focus"], "practical_execution")
        self.assertIn("14天", commitment["terms"])
        self.assertTrue(_has_pending_commitment(
            ledger, "environment_agent", "practical_execution",
            ["amount", "deadline", "repayment_action"],
        ))


    def test_runtime_segment_propagates_repayment_commitment_lock(self):
        runtime = _runtime_segment(
            {
                "segment_id": "post_performance",
                "reason": "review public outcome",
                "max_turns": 3,
                "forbid_new_repayment_commitment": True,
            },
            started_after_turn=7, planned_end_turn=10,
        )
        self.assertTrue(runtime["forbid_new_repayment_commitment"])

    def test_repayment_terms_cannot_be_borrowed_from_other_speaker_context(self):
        plan_promise = {
            "text": "我会在本周内给出一个调整方案。",
            "object": "在本周内给出一个调整方案",
            "context": "请确认14天内是否能还500元。",
        }
        required = ["amount", "deadline", "repayment_action"]
        self.assertFalse(_commitment_has_required_terms(plan_promise, required))
        repayment_promise = {
            "text": "我会在14天内先还500元。",
            "object": "在14天内先还500元",
            "context": "请给出安排。",
        }
        self.assertTrue(_commitment_has_required_terms(repayment_promise, required))

    def test_partial_amount_inside_remaining_balance_is_selected(self):
        self.assertEqual(_commitment_amount({
            "object": "在接下来的28天内还清剩余2750元中的300元"
        }), 300.0)
        self.assertEqual(_commitment_amount({
            "object": "在28天内还500元"
        }), 500.0)
        self.assertEqual(_commitment_amount({
            "object": "补齐250元，并再还至少200元，共计450元"
        }), 450.0)
        self.assertIsNone(_commitment_amount({
            "object": "剩余2750元，之后再讨论300元是否可行"
        }))
        self.assertIsNone(_commitment_amount({
            "object": "三周困难让800元起步困难，但我会在本周给出调整方案"
        }))


class CountingNeutralUpdater:
    provenance = {"provider": "test-double", "model": "neutral-appraiser"}

    def __init__(self):
        self.calls = 0

    def _fill(self, values):
        return {
            key: self._fill(value) if isinstance(value, dict) else "similar"
            for key, value in values.items()
        }

    def update(self, *, action, previous_state, previous_dynamics, memory):
        self.calls += 1
        return validate_transition({
            "appraisal": {
                "speaker_intent": "被评估参与者继续核对既有借款问题",
                "social_act": "request",
            },
            "state_delta": self._fill(previous_state),
            "interaction_dynamics_delta": self._fill(previous_dynamics),
            "evidence_turn_ids": list(memory["relevant_turn_ids"]),
        }, previous_state, previous_dynamics)


class ScheduledBorrowerResponse:
    provenance = {"provider": "test-double", "model": "borrower-response"}

    def __init__(self, commitment=True):
        self.calls = 0
        self.commitment = commitment

    def generate(self, context):
        self.calls += 1
        commitment_turn = SCENARIO["longitudinal_design"]["segments"][0]["max_turns"]
        if self.commitment and context["turn_id"] == commitment_turn:
            return "我会在14天内还500元，完成这次还款。"
        return f"我在回应当前可见的问题，这是第{context['turn_id']}次交流。"


def longitudinal_environment_factory(commitment=True):
    def build():
        return StatefulEnvironment(
            deepcopy(SCENARIO),
            state_updater=CountingNeutralUpdater(),
            response_generator=ScheduledBorrowerResponse(commitment=commitment),
        )
    return build


class LongitudinalEnvironmentTest(unittest.TestCase):
    @unittest.skip("legacy longitudinal scenario contract is not emitted by active batches")
    def test_final_fragment_can_end_naturally_before_turn_twenty(self):
        scenario = deepcopy(SCENARIO)
        final = scenario["longitudinal_design"]["segments"][-1]
        session = {
            "turn_id": 17,
            "status": "active",
            "ending": None,
            "longitudinal_enabled": True,
            "segment_index": len(scenario["longitudinal_design"]["segments"]) - 1,
            "segment_turn_id": final["min_turns"],
            "elapsed_time": 999,
            "current_segment": {
                "all_live_questions": [], "resolved_live_questions": [],
                "live_questions": [],
            },
            "segments": [{"segment_id": final["segment_id"], "status": "active"}],
            "interaction_ledger": {"commitments": [], "latest_obligation": None},
        }
        appraisal = {"dialogue_diagnostics": {"continuation": {
            "status": "can_close", "evidence_span": "",
        }}}
        transition = maybe_advance_segment(
            scenario, session,
            action_text="关系定位已经说清楚了。",
            response_text="我接受这个定位，今天就谈到这里。",
            appraisal=appraisal,
            response_events=[{
                "event_type": "pause", "owner": "environment_agent", "action_owner": "environment_agent",
                "evidence_span": "今天就谈到这里", "status": "explicit",
            }],
        )
        self.assertTrue(transition["terminal"])
        self.assertEqual(session["status"], "completed")
        self.assertEqual(
            session["ending"], {"reason": "natural_completion", "turn_id": 17}
        )
    def test_final_segment_capacity_is_not_natural_completion_evidence(self):
        session = {
            "segment_turn_id": 3,
            "counterfactual_timeline_lock": False,
            "interaction_ledger": {"latest_obligation": None},
        }
        segment = {
            "min_turns": 1,
            "max_turns": 3,
            "allow_explicit_pause": True,
            "allow_semantic_pause": True,
        }
        appraisal = {"dialogue_diagnostics": {"continuation": {
            "status": "continue", "evidence_span": "分歧仍在",
        }}}
        self.assertEqual(
            _should_advance(
                session, segment, "分歧仍在。", "我知道。", appraisal,
                final_segment=True,
            ),
            (False, None),
        )
        self.assertEqual(
            _should_advance(
                session, segment, "分歧仍在。", "我知道。", appraisal,
                final_segment=False,
            ),
            (False, None),
        )

    def test_semantic_can_close_is_not_vetoed_by_residual_diagnostic_questions(self):
        session = {
            "segment_turn_id": 2, "counterfactual_timeline_lock": False,
            "interaction_ledger": {"commitments": [], "latest_obligation": None},
            "current_segment": {
                "all_live_questions": ["联系模式", "是否反复提旧账"],
                "resolved_live_questions": ["联系模式"],
                "live_questions": ["是否反复提旧账"],
            },
        }
        segment = {
            "min_turns": 2, "max_turns": 4,
            "allow_explicit_pause": True, "allow_semantic_pause": True,
        }
        appraisal = {"dialogue_diagnostics": {"continuation": {
            "status": "can_close", "evidence_span": "我接受这个模式",
        }}}
        self.assertEqual(
            _should_advance(
                session, segment, "我接受这个模式。", "那我就按这个模式来。",
                appraisal, final_segment=True,
            ),
            (True, "appraisal_semantic_final_pause"),
        )
        self.assertEqual(
            _should_advance(
                session, segment, "我接受这个模式。", "那我就按这个模式来。",
                appraisal, final_segment=False,
            ),
            (True, "appraisal_semantic_pause"),
        )
        session["interaction_ledger"]["latest_obligation"] = {
            "owner": "evaluated_agent"
        }
        self.assertEqual(
            _should_advance(
                session, segment, "我接受这个模式。", "你是否确认？",
                appraisal, final_segment=True,
            ),
            (False, None),
        )


    def test_live_question_progress_accumulates_only_from_direct_exact_evidence(self):
        session = {
            "segment_turn_id": 2,
            "counterfactual_timeline_lock": False,
            "interaction_ledger": {"commitments": [], "latest_obligation": None},
            "current_segment": {
                "all_live_questions": ["金额是否明确", "期限是否可行"],
                "resolved_live_questions": [],
                "live_questions": ["金额是否明确", "期限是否可行"],
            },
            "segments": [{}],
        }
        appraisal = {"dialogue_diagnostics": {"continuation": {
            "status": "can_close",
            "after_direct_response": {
                "status": "continue",
                "resolved_live_questions": ["金额是否明确"],
                "remaining_live_questions": ["期限是否可行"],
            },
        }}}
        _accumulate_live_question_progress(
            session, "具体金额是多少？", "具体金额是500元。", appraisal
        )
        self.assertEqual(
            session["current_segment"]["resolved_live_questions"], ["金额是否明确"]
        )
        self.assertEqual(
            session["current_segment"]["live_questions"], ["期限是否可行"]
        )
        segment = {
            "min_turns": 2, "max_turns": 4,
            "allow_explicit_pause": False, "allow_semantic_pause": True,
        }
        self.assertEqual(
            _should_advance(session, segment, "金额？", "500元。", appraisal),
            (True, "appraisal_semantic_pause"),
        )
        second = {"dialogue_diagnostics": {"continuation": {
            "status": "can_close",
            "after_direct_response": {
                "status": "can_close",
                "resolved_live_questions": ["期限是否可行"],
                "remaining_live_questions": [],
            },
        }}}
        _accumulate_live_question_progress(
            session, "期限是否可行？", "这个期限可以。", second
        )
        self.assertEqual(session["current_segment"]["live_questions"], [])
        self.assertEqual(
            _should_advance(session, segment, "期限？", "可以。", second),
            (True, "appraisal_semantic_pause"),
        )

    def test_appraisal_can_close_advances_after_minimum_without_reply_obligation(self):
        session = {
            "segment_turn_id": 2,
            "counterfactual_timeline_lock": False,
            "interaction_ledger": {"commitments": [], "latest_obligation": None},
        }
        segment = {
            "min_turns": 2,
            "max_turns": 4,
            "allow_explicit_pause": True,
            "allow_semantic_pause": True,
        }
        appraisal = {
            "dialogue_diagnostics": {
                "continuation": {"status": "can_close", "evidence_span": ""}
            }
        }
        self.assertEqual(
            _should_advance(session, segment, "立场已经清楚。", "我理解。", appraisal),
            (True, "appraisal_semantic_pause"),
        )
        session["interaction_ledger"]["latest_obligation"] = {
            "owner": "evaluated_agent"
        }
        self.assertEqual(
            _should_advance(session, segment, "立场已经清楚。", "你是否同意？", appraisal),
            (False, None),
        )

    def test_direct_answer_can_close_when_appraisal_says_it_settles_fragment(self):
        session = {
            "segment_turn_id": 2,
            "counterfactual_timeline_lock": False,
            "interaction_ledger": {"commitments": [], "latest_obligation": None},
        }
        segment = {
            "min_turns": 2, "max_turns": 4,
            "allow_explicit_pause": True, "allow_semantic_pause": True,
        }
        appraisal = {
            "dialogue_diagnostics": {
                "continuation": {
                    "status": "must_answer",
                    "evidence_span": "你是否接受？",
                    "after_direct_response": {
                        "status": "can_close",
                        "evidence_span": "你是否接受？",
                    },
                }
            }
        }
        self.assertEqual(
            _should_advance(
                session, segment, "你是否接受？", "我接受。", appraisal
            ),
            (True, "appraisal_direct_answer_pause"),
        )
        session["interaction_ledger"]["latest_obligation"] = {
            "owner": "evaluated_agent"
        }
        self.assertEqual(
            _should_advance(
                session, segment, "你是否接受？", "我再想想。", appraisal
            ),
            (False, None),
        )

    @unittest.skip("legacy longitudinal scenario contract is not emitted by active batches")
    def test_promise_and_public_performance_are_distinct_events(self):
        updater = CountingNeutralUpdater()
        responder = ScheduledBorrowerResponse()
        environment = StatefulEnvironment(
            deepcopy(SCENARIO),
            state_updater=updater,
            response_generator=responder,
        )
        environment.reset(episode_id="longitudinal-distinction")
        logs = []
        first_segment_cap = SCENARIO["longitudinal_design"]["segments"][0]["max_turns"]
        for index in range(first_segment_cap):
            _, log = environment.step({"text": f"请继续核对第{index + 1}项。"})
            logs.append(log)

        transition = logs[-1]["segment_transition_after"]
        self.assertIsNotNone(transition)
        self.assertEqual(updater.calls, first_segment_cap)
        self.assertEqual(responder.calls, first_segment_cap)
        self.assertEqual(transition["elapsed_after"], 14)
        self.assertTrue(all(
            value == 0
            for group in transition["numeric_time_state_delta"].values()
            for value in group.values()
        ))
        self.assertIn(
            transition["selected_outcome_id"],
            {"fulfilled", "partially_fulfilled", "unfulfilled"},
        )
        performance_event = next(
            event for event in transition["public_events"]
            if event["event_type"] == "commitment_performance"
        )
        numeric = performance_event["numeric_performance"]
        self.assertEqual(numeric["committed_amount"], 500.0)
        self.assertEqual(
            numeric["balance_after"],
            3000.0 - numeric["performed_amount"],
        )
        self.assertIn("剩余未还金额", performance_event["text"])
        commitment = environment.session["interaction_ledger"]["commitments"][-1]
        self.assertEqual(commitment["performance_status"], transition["selected_outcome_id"])
        if transition["selected_outcome_id"] == "fulfilled":
            self.assertEqual(commitment["status"], "completed_by_public_event")
        elif transition["selected_outcome_id"] == "partially_fulfilled":
            self.assertEqual(
                commitment["status"], "partially_fulfilled_by_public_event"
            )
        else:
            self.assertEqual(commitment["status"], "unfulfilled_by_public_event")
        self.assertEqual(
            environment.observe()["longitudinal_context"]["segment"]["segment_id"],
            "first_repayment_checkpoint",
        )
        self.assertTrue(any(
            item.get("role") == "public_event"
            for item in environment.observe()["history"]
        ))

        trajectory = environment.private_trajectory()
        trajectory["policy_id"] = "test-policy"
        trajectory["policy_provenance"] = {
            "policy_id": "test-policy", "provider": "test", "model": "test",
            "prompt_id": "test", "sampling": {},
        }
        checkpoints = build_t1_checkpoints(trajectory)
        self.assertTrue(checkpoints[-1]["input"]["history"][-1]["public_events_after"])
        self.assertEqual(
            checkpoints[-1]["input"]["current_checkpoint"]["longitudinal_context"]["time"]["elapsed"],
            14,
        )

    @unittest.skip("legacy longitudinal scenario contract is not emitted by active batches")
    def test_repayment_commitment_focus_uses_promised_object(self):
        environment = longitudinal_environment_factory()()
        environment.reset(episode_id="commitment-object-focus")
        first_segment_cap = SCENARIO["longitudinal_design"]["segments"][0]["max_turns"]
        for index in range(first_segment_cap):
            _, log = environment.step({"text": f"核对第{index + 1}项。"})
        commitment = next(
            item for item in log["interaction_ledger_after"]["commitments"]
            if "完成这次还款" in item["text"]
        )
        self.assertEqual(commitment["focus"], "practical_execution")

    @unittest.skip("legacy longitudinal scenario contract is not emitted by active batches")
    def test_repayment_object_beats_appended_economic_boundary(self):
        environment = longitudinal_environment_factory()()
        environment.reset(episode_id="repayment-before-boundary")
        first_segment_cap = SCENARIO["longitudinal_design"]["segments"][0]["max_turns"]
        for index in range(first_segment_cap):
            _, log = environment.step({"text": f"核对第{index + 1}项。"})
        from environment.interaction_ledger import record_environment_response
        ledger = record_environment_response(
            log["interaction_ledger_after"],
            turn_id=5,
            response=(
                "我会分两次到账400元，并在完成后讨论是否暂停新的经济往来。"
            ),
            latest_social_act="request",
        )
        self.assertEqual(ledger["commitments"][-1]["focus"], "practical_execution")

    def test_conditional_notice_is_not_a_repayment_commitment(self):
        from environment.interaction_ledger import initial_ledger, record_environment_response
        ledger = record_environment_response(
            initial_ledger(), turn_id=1,
            response=(
                "如果14天内能完成500元还款，我会提前告知你并公开记录。"
            ),
            latest_social_act="request",
        )
        self.assertEqual(ledger["commitments"][-1]["focus"], "communication_boundary")

    def test_natural_repayment_commitment_is_captured_without_promise_prefix(self):
        from environment.interaction_ledger import initial_ledger, record_environment_response
        ledger = record_environment_response(
            initial_ledger(), turn_id=1,
            response=(
                "我理解你的顾虑，目前能确定的是14天内至少先还300元，"
                "若之后仍有困难，我会在第三天主动说明具体原因。"
            ),
            latest_social_act="request",
            latest_action="请明确第一笔金额、期限和有变化时如何说明。",
        )
        practical = [
            item for item in ledger["commitments"]
            if item["focus"] == "practical_execution"
        ]
        self.assertEqual(len(practical), 1)
        self.assertTrue(_commitment_has_required_terms(
            practical[0], ["amount", "deadline", "repayment_action"]
        ))
        ledger = record_environment_response(
            ledger, turn_id=2,
            response="300 元是目前我能明确承诺的最低可行金额。",
            latest_social_act="question",
            latest_action="300元是否是你目前能确保落地的底线？",
        )
        self.assertTrue(_has_pending_commitment(
            ledger, "environment_agent", "practical_execution",
            ["amount", "deadline", "repayment_action"],
        ))

    def test_trying_to_repay_is_not_a_verifiable_repayment_commitment(self):
        from environment.interaction_ledger import initial_ledger, record_environment_response
        ledger = record_environment_response(
            initial_ledger(), turn_id=1,
            response="我会在14天内尽力还500元。",
            latest_social_act="request",
            latest_action="14天内能明确还多少？",
        )
        self.assertFalse(ledger["commitments"])
        ledger = record_environment_response(
            initial_ledger(), turn_id=2,
            response="我会尽力在14天内还500元。",
            latest_social_act="request",
            latest_action="14天内能明确还多少？",
        )
        self.assertFalse(ledger["commitments"])
        ledger = record_environment_response(
            initial_ledger(), turn_id=3,
            response="我先尽力凑个1000元，14天后一次性转给你。",
            latest_social_act="request",
            latest_action="14天内能明确还多少？",
        )
        self.assertFalse(ledger["commitments"])
        ledger = record_environment_response(
            initial_ledger(), turn_id=4,
            response=(
                "14天内实际转出500元我会尽力安排。"
                "如果届时有困难，我会提前和你沟通。"
            ),
            latest_social_act="request",
            latest_action="请明确是否能承诺。",
        )
        self.assertFalse(any(
            item["focus"] == "practical_execution"
            for item in ledger["commitments"]
        ))

    def test_inverted_firm_repayment_is_a_verifiable_commitment(self):
        from environment.interaction_ledger import initial_ledger, record_environment_response
        ledger = record_environment_response(
            initial_ledger(), turn_id=1,
            response="1000元我14天后一定按时转给你，不会耽误。",
            latest_social_act="statement",
            latest_action="这个意向还不是承诺。",
        )
        self.assertTrue(_has_pending_commitment(
            ledger, "environment_agent", "practical_execution",
            ["amount", "deadline", "repayment_action"],
        ))

    def test_repayment_capacity_seeking_acceptance_is_a_proposal_not_commitment(self):
        from environment.interaction_ledger import initial_ledger, record_environment_response
        ledger = record_environment_response(
            initial_ledger(), turn_id=1,
            response="在下一个28天里，我最多能还1000元，你看这样安排是否可行？",
            latest_social_act="question",
            latest_action="下一个周期能承担多少？",
        )
        self.assertFalse(ledger["commitments"])

    def test_repayment_commitment_is_not_performed_by_later_discussion(self):
        from environment.interaction_ledger import initial_ledger, record_environment_response
        ledger = record_environment_response(
            initial_ledger(), turn_id=1,
            response="200元是目前我能在28天内确认执行的还款金额。",
            latest_social_act="request",
            latest_action="下一个28天内实际能还多少？",
        )
        practical = [
            item for item in ledger["commitments"]
            if item["focus"] == "practical_execution"
        ]
        self.assertEqual(len(practical), 1)
        ledger = record_environment_response(
            ledger, turn_id=2,
            response="我们先基于这200元的实际执行情况，重新评估信任基础和沟通方式。",
            latest_social_act="statement",
            latest_action="这种变化对信任意味着什么？",
        )
        self.assertEqual(practical[0]["status"], "pending")
        self.assertEqual(
            [item for item in ledger["commitments"] if item["focus"] == "practical_execution"][-1]["status"],
            "pending",
        )

    def test_vague_amount_response_keeps_original_question_open(self):
        from environment.interaction_ledger import initial_ledger, record_evaluated_action, record_environment_response
        ledger = record_evaluated_action(
            initial_ledger(), turn_id=1,
            action={"text": "十四天内能还多少，有具体金额吗？"},
            appraisal={"social_act": "question"},
        )
        ledger = record_environment_response(
            ledger, turn_id=1,
            response="我理解，目前需要先理清能承担的部分。",
            latest_social_act="question",
            latest_action="十四天内能还多少，有具体金额吗？",
        )
        self.assertTrue(any(
            item.get("speaker") == "evaluated_agent"
            and item.get("status") == "still_open"
            for item in ledger["unresolved_threads"]
        ))

    @unittest.skip("legacy longitudinal scenario contract is not emitted by active batches")
    def test_public_scope_exposes_schedule_but_not_future_outcome(self):
        environment = longitudinal_environment_factory()()
        observation = environment.reset(episode_id="public-scope")
        context = observation["longitudinal_context"]
        self.assertIn("14天内第一笔", context["segment"]["interaction_goal"])
        guidance = context["segment"]["turn_guidance"]
        self.assertEqual(guidance["mode"], "optional_discussion_space")
        self.assertEqual(guidance["suggested_live_question"], "")
        self.assertIn("possible discussion space", guidance["instruction"])
        self.assertFalse(guidance["hard_gate"])
        self.assertFalse(context["segment"]["terminal_fragment"])
        self.assertEqual(
            context["segment"]["turns_remaining_in_fragment"],
            SCENARIO["longitudinal_design"]["segments"][0]["max_turns"],
        )
        self.assertEqual(
            context["segment"]["all_live_questions"],
            context["segment"]["live_questions"],
        )
        self.assertEqual(context["segment"]["resolved_live_questions"], [])
        self.assertEqual(context["next_interaction"]["after"], 14)
        self.assertNotIn("outcome", json.dumps(context, ensure_ascii=False).lower())

    @unittest.skip("legacy longitudinal scenario contract is not emitted by active batches")
    def test_time_only_recontact_does_not_emit_fake_precondition_event(self):
        scenario = deepcopy(SCENARIO)
        first = deepcopy(scenario["longitudinal_design"]["segments"][0])
        first.update({"min_turns": 1, "max_turns": 1})
        first.pop("end_on_pending_commitment", None)
        second = deepcopy(scenario["longitudinal_design"]["segments"][-1])
        second.update({"min_turns": 1, "max_turns": 20, "advance_by": 3})
        second.pop("event_pool_id", None)
        second.pop("requires_pending_commitment", None)
        scenario["longitudinal_design"] = {
            "format": "socialflux_longitudinal_v1",
            "time_unit": "day",
            "start_elapsed": 0,
            "segments": [first, second],
            "event_pools": [],
        }
        environment = StatefulEnvironment(
            scenario,
            state_updater=CountingNeutralUpdater(),
            response_generator=ScheduledBorrowerResponse(commitment=False),
        )
        environment.reset(episode_id="time-only")
        _, log = environment.step({"text": "这次先暂停，等节点到了再联系。"})
        transition = log["segment_transition_after"]
        self.assertIsNone(transition["selected_outcome_id"])
        self.assertEqual(
            [event["event_type"] for event in transition["public_events"]],
            ["time_advance", "segment_opening"],
        )

    @unittest.skip("legacy longitudinal scenario contract is not emitted by active batches")
    def test_deadline_without_commitment_does_not_create_fulfillment(self):
        environment = longitudinal_environment_factory(commitment=False)()
        initial_state = deepcopy(environment.reset(episode_id="no-promise"))
        del initial_state
        last = None
        first_segment_cap = SCENARIO["longitudinal_design"]["segments"][0]["max_turns"]
        for index in range(first_segment_cap):
            text = (
                "先暂停，等约定节点到了再联系。"
                if index == first_segment_cap - 1
                else f"继续讨论已有问题{index + 1}。"
            )
            _, last = environment.step({"text": text})
        transition = last["segment_transition_after"]
        self.assertEqual(transition["selected_outcome_id"], "precondition_not_met")
        self.assertFalse(environment.session["interaction_ledger"]["commitments"])
        self.assertFalse(any(
            event.get("event_type") == "commitment_performance"
            for event in transition["public_events"]
        ))

    @unittest.skip("legacy longitudinal scenario contract is not emitted by active batches")
    def test_t3_branches_freeze_external_timeline_and_report_elapsed_time(self):
        trajectory = RolloutRunner(longitudinal_environment_factory()).run(
            TextPolicy("source", ["先核对现有问题。"] * 3),
            max_turns=3,
        )
        checkpoint = trajectory["turns"][-1]
        branches = branch_counterfactuals(
            longitudinal_environment_factory(),
            checkpoint,
            [{"text": "请给出明确安排。"}, {"text": "我们先保留分歧。"}],
            lambda: TextPolicy("continuation", ["继续依据现有记录讨论。"] * 4),
            delayed_horizon=5,
        )
        self.assertEqual(
            {branch["external_event_plan_hash"] for branch in branches},
            {trajectory["event_plan"]["plan_hash"]},
        )
        elapsed_deltas = {branch["elapsed_time_delta"] for branch in branches}
        self.assertEqual(len(elapsed_deltas), 1)
        self.assertGreater(next(iter(elapsed_deltas)), 0)
        self.assertTrue(all(
            branch["elapsed_time_delta"]
            == branch["elapsed_time_end"] - branch["elapsed_time_start"]
            for branch in branches
        ))
        self.assertEqual(
            [event["event_id"] for event in branches[0]["crossed_event_nodes"]],
            [event["event_id"] for event in branches[1]["crossed_event_nodes"]],
        )


if __name__ == "__main__":
    unittest.main()
