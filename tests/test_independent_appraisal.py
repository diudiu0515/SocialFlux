import json
from pathlib import Path
import unittest

from environment.independent_appraisal import (
    ModelInteractionAppraiser,
    ModelStateAppraiser,
)
from environment.state_updater import ModelStateUpdater
from providers.base import ModelProvider


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = ROOT / "data/gpt50/experiment/scenario/scenarios_state_v3/scenario_003/scenario_003.json"


class StaticProvider(ModelProvider):
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, messages, **generation):
        self.calls.append({"messages": messages, "generation": generation})
        return json.dumps(self.response, ensure_ascii=False)

    @property
    def audit_records(self):
        return [{
            "request": call,
            "raw_output": json.dumps(self.response, ensure_ascii=False),
            "finish_reason": "stop",
            "complete": True,
        } for call in self.calls]


def no_evidence(variable):
    return {
        "variable": variable,
        "judgment": "no_relevant_evidence",
        "direction": None,
        "evidence_span": "",
        "directness": None,
        "evidence_feature": None,
        "rationale": "本轮没有改变该项既有判断。",
    }


class IndependentAppraisalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))

    def test_parallel_appraisals_merge_once_and_preserve_variable_completeness(self):
        action_text = "我拒绝把未经核实的说法写成事实。"
        state_variables = [
            f"{family}.{name}"
            for family, values in self.scenario["initial_state"].items()
            for name in values
        ]
        dynamics_variables = list(self.scenario["initial_dynamics"])
        judgments = [no_evidence(path) for path in state_variables]
        trust = next(item for item in judgments if item["variable"] == "relationship.trust")
        trust.update({
            "judgment": "decisive_new_evidence",
            "direction": "increase",
            "evidence_span": "拒绝把未经核实的说法写成事实",
            "directness": "direct",
            "evidence_feature": "commitment_signal",
            "rationale": "本轮拒绝失实表述，改变了对其可靠性的既有顾虑。",
        })
        features = {name: 0 for name in (
            "goal_alignment", "cooperation_signal", "repair_signal", "pressure",
            "face_threat", "commitment_signal", "uncertainty_reduction",
            "boundary_violation", "respect_signal", "withdrawal_signal",
        )}
        features["commitment_signal"] = 2
        state_provider = StaticProvider({
            "event_features": features,
            "state_judgments": judgments,
            "dynamics_judgments": [
                no_evidence(path) for path in dynamics_variables
            ],
            "evidence_turn_ids": [],
        })
        interaction_provider = StaticProvider({
            "appraisal": {
                "speaker_intent": "evaluated_agent 拒绝将未核实内容写成事实。",
                "social_act": "refusal",
                "ledger_events": [],
                "ledger_resolutions": [],
                "dialogue_diagnostics": {
                    "substantive_novelty": {
                        "label": "new_decision",
                        "evidence_span": "拒绝把未经核实的说法写成事实",
                    },
                    "consequential_claims": [],
                    "continuation": {
                        "status": "continue",
                        "evidence_span": action_text,
                        "after_direct_response": {
                            "status": "continue",
                            "evidence_span": action_text,
                        },
                    },
                },
            },
            "evidence_turn_ids": [],
        })
        updater = ModelStateUpdater(
            self.scenario,
            state_provider,
            {"temperature": 0, "max_tokens": 3500},
            state_appraiser=ModelStateAppraiser(
                self.scenario, state_provider, {"temperature": 0, "max_tokens": 3500}
            ),
            interaction_appraiser=ModelInteractionAppraiser(
                self.scenario, interaction_provider,
                {"temperature": 0, "max_tokens": 3500},
            ),
            calibration_profile="evidence_causal_slow_priority_hysteretic_v6",
        )
        transition = updater.update(
            action={"text": action_text},
            previous_state=self.scenario["initial_state"],
            previous_dynamics=self.scenario["initial_dynamics"],
            memory={"relevant_turn_ids": []},
            longitudinal_context={},
            interaction_ledger={"active_proposals": []},
        )
        self.assertEqual(len(transition["state_judgments"]), len(state_variables))
        self.assertEqual(transition["state_delta"]["relationship"]["trust"], "moderate_increase")
        self.assertEqual(len(state_provider.calls), 1)
        self.assertEqual(len(interaction_provider.calls), 1)
        self.assertEqual(state_provider.calls[0]["generation"]["max_tokens"], 6000)
        self.assertEqual(interaction_provider.calls[0]["generation"]["max_tokens"], 3500)
        trust_judgment = next(
            item for item in transition["state_judgments"]
            if item["variable"] == "relationship.trust"
        )
        self.assertEqual(
            trust_judgment["feature_interface_validation"], "valid"
        )
        trust_diagnostic = next(
            item for item in transition["calibration"]["state_impacts"]
            if item["variable"] == "relationship.trust"
        )
        self.assertEqual(trust_diagnostic["eligibility_status"], "eligible")
        self.assertEqual(trust_diagnostic["final_delta"], "moderate_increase")


if __name__ == "__main__":
    unittest.main()
