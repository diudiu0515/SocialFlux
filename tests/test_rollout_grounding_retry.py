import json
import unittest
from copy import deepcopy
from pathlib import Path

from environment.env import StatefulEnvironment
from environment.state_updater import UnsupportedConsequentialClaim
from rollout.runner import RolloutRunner
from tests.support import ContextualTestResponse, ContextualTestUpdater, TextPolicy


SCENARIO = json.loads(Path(
    "configs/scenarios/scenario_001/scenario_001.json"
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
