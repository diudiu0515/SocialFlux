import json
import unittest
from copy import deepcopy
from pathlib import Path

from scenario_design.revision import apply_revision, validate_revision
from scripts.revise_scale300_scenarios import provider_request_count


SCENARIO = json.loads(Path(
    "configs/scale300_v1/scenarios/scenario_201/scenario_201.json"
).read_text(encoding="utf-8"))


def revision():
    scenario = deepcopy(SCENARIO)
    narrative = deepcopy(scenario["narrative_design"])
    narrative["relevant_history"][-1] = (
        "事实边界：合同只证明接单，收入到账与三个月后的稳定性仍需公开记录。"
    )
    return {
        "format": "socialflux_scenario_revision_v1",
        "scenario_id": scenario["scenario_id"],
        "decision": "revise",
        "diagnosis": "旧设计使用了与人物期限不一致的固定三片段。",
        "estimated_natural_turn_range": [9, 16],
        "task_potential": {
            "T1": "strong", "T2": "strong", "T3": "usable", "T4": "strong",
        },
        "patch": {
            "title": scenario["title"],
            "mechanism": scenario["mechanism"],
            "background": scenario["background"],
            "narrative_design": narrative,
            "environment_agent": deepcopy(scenario["environment_agent"]),
            "evaluated_agent_role": deepcopy(scenario["evaluated_agent_role"]),
            "opening_response": "你说想试三个月，先告诉我这期间家用和风险怎么安排。",
            "longitudinal_design": None,
        },
    }


class ScenarioRevisionTest(unittest.TestCase):
    def test_batch_request_count_prefers_actual_provider_attempts(self):
        provider = type("Provider", (), {
            "metrics": {"request_count": 4}, "_call_index": 1,
        })()
        self.assertEqual(provider_request_count(provider), 4)

    def test_revision_preserves_source_and_numeric_state(self):
        value = revision()
        validate_revision(value, SCENARIO)
        revised = apply_revision(SCENARIO, value)
        self.assertEqual(revised["source"], SCENARIO["source"])
        self.assertEqual(revised["initial_state"], SCENARIO["initial_state"])
        self.assertNotIn("longitudinal_design", revised)
        self.assertEqual(revised["construction_status"]["quality_gate"],
                         "pending_generation_and_semantic_review")

    def test_revision_requires_explicit_fact_boundary(self):
        value = revision()
        value["patch"]["narrative_design"]["relevant_history"][-1] = "没有边界标签"
        with self.assertRaisesRegex(ValueError, "事实边界"):
            validate_revision(value, SCENARIO)

    def test_revision_cannot_change_character_id(self):
        value = revision()
        value["patch"]["evaluated_agent_role"]["character_id"] = "OTHER"
        with self.assertRaisesRegex(ValueError, "character_id"):
            validate_revision(value, SCENARIO)


if __name__ == "__main__":
    unittest.main()
