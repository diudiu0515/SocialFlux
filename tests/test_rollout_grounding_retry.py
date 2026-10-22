import json
import unittest
from copy import deepcopy
from pathlib import Path

from environment.env import StatefulEnvironment
from environment.state_updater import UnsupportedConsequentialClaim
from rollout.runner import RolloutRunner
from tests.support import ContextualTestResponse, ContextualTestUpdater, TextPolicy


SCENARIO = json.loads(Path(
    "data/gpt50/experiment/scenario/scenarios/scenario_001/scenario_001.json"
).read_text(encoding="utf-8"))


class RejectFirstUnsupportedClaim(ContextualTestUpdater):
    def update(self, **kwargs):
        action = kwargs["action"]
        if "未经证实" in action["text"]:
            claim = {
                "claim_span": "未经证实的关键事实",
                "impact_domains": ["responsibility"],
                "grounding": "unsupported_assertion",
            }
            raise UnsupportedConsequentialClaim(
                [claim], {"dialogue_diagnostics": {
                    "consequential_claims": [claim]
                }},
            )
        return super().update(**kwargs)


class RolloutGroundingRetryTest(unittest.TestCase):
    def test_resume_preserves_completed_turn_and_uses_actual_snapshot(self):
        scenario=deepcopy(SCENARIO);scenario['max_turns']=3
        def factory():
            return StatefulEnvironment(scenario,state_updater=ContextualTestUpdater(scenario),
                                       response_generator=ContextualTestResponse())
        checkpoints=[]
        first=RolloutRunner(factory,checkpoint_writer=checkpoints.append).run(
            TextPolicy('prefix',['我想先核对当前条件。']),max_turns=1)
        saved=checkpoints[-1]
        resumed=RolloutRunner(factory).run(TextPolicy('prefix',['请说明尚待确认的边界。']),
                                          max_turns=2,resume_from=saved)
        self.assertEqual(resumed['turns'][0],first['turns'][0])
        self.assertEqual(len(resumed['turns']),2)
        self.assertEqual(resumed['turns'][1]['state_before'],saved['resume_snapshot']['state'])
        self.assertEqual(resumed['resumed_from']['completed_turns'],1)
        bad=deepcopy(saved);bad['resume_snapshot']['turn_id']=99
        with self.assertRaisesRegex(ValueError,'last completed turn'):
            RolloutRunner(factory).run(TextPolicy('prefix',['继续。']),max_turns=2,resume_from=bad)

    def test_rejected_action_is_preserved_when_repair_call_fails(self):
        scenario = deepcopy(SCENARIO)
        scenario["max_turns"] = 1

        def factory():
            return StatefulEnvironment(
                scenario,
                state_updater=RejectFirstUnsupportedClaim(scenario),
                response_generator=ContextualTestResponse(),
            )

        class FailingRepairPolicy(TextPolicy):
            def generate(self, observation):
                if self.index:
                    raise TimeoutError("repair request timed out")
                return super().generate(observation)

        policy = FailingRepairPolicy(
            "grounding-repair-timeout",
            ["这是未经证实的关键事实。"],
        )
        with self.assertRaises(TimeoutError) as caught:
            RolloutRunner(factory).run(policy, max_turns=1)
        diagnostics = caught.exception.partial_trajectory[
            "generation_error"
        ]["rejected_policy_action_attempts"]
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(
            diagnostics[0]["policy_action"]["text"],
            "这是未经证实的关键事实。",
        )

    def test_rejected_action_is_replaced_before_state_commit(self):
        scenario = deepcopy(SCENARIO)
        scenario["max_turns"] = 1

        def factory():
            return StatefulEnvironment(
                scenario,
                state_updater=RejectFirstUnsupportedClaim(scenario),
                response_generator=ContextualTestResponse(),
            )

        policy = TextPolicy(
            "grounding-retry",
            ["这是未经证实的关键事实。", "我不确定这一点，请先核对。"],
        )
        checkpoints = []
        trajectory = RolloutRunner(
            factory,
            checkpoint_writer=checkpoints.append,
        ).run(policy, max_turns=1)
        turn = trajectory["turns"][0]
        self.assertEqual(
            turn["policy_action"]["text"], "我不确定这一点，请先核对。"
        )
        self.assertEqual(len(turn["rejected_policy_action_attempts"]), 1)
        rejected = turn["rejected_policy_action_attempts"][0]
        self.assertEqual(rejected["attempt"], 1)
        self.assertEqual(
            rejected["reason"], "unsupported_consequential_claim"
        )
        self.assertEqual(trajectory["actual_request_counts"]["total"], None)
        self.assertEqual(
            [item["checkpoint_status"] for item in checkpoints],
            ["turn_completed", "trajectory_completed"],
        )
        self.assertEqual(len(checkpoints[-1]["turns"]), 1)


if __name__ == "__main__":
    unittest.main()
