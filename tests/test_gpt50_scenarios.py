import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from prompts.loader import prompt_manifest
from scripts.generate_gpt50_scenarios import (
    CURATED_CONTEXTS,
    NARRATIVE_COUNT,
    SOURCE_WORKS,
    _scenario_complete,
    curated_brief,
    TOTAL_COUNT,
    requested_identity,
    source_type_for_ordinal,
    validate_brief_batch,
)



def brief_for(identity):
    coverage = {
        "domain": "community governance",
        "opening_condition": "A deadline creates a concrete request.",
        "choice_space": "Require at least three materially different choices.",
        "longitudinal_need": "A later record changes how earlier conduct is read.",
        "originality_boundary": "All people, facts, events, and wording are original.",
    }
    if identity["source_type"] == "narrative-derived":
        coverage.update({
            "source_work": {"title": "A Known Film", "medium": "film"},
            "adaptation_policy": (
                "structural_abstraction_only_original_surface_text"
            ),
        })
    else:
        coverage["origin_policy"] = "fully_original_synthetic_scenario"
    return {
        "scenario_id": identity["scenario_id"],
        "source_type": identity["source_type"],
        "provenance_id": identity["provenance_id"],
        "mechanism": "conflicting obligations under incomplete information",
        "relationship_structure": "two long-term collaborators",
        "power_structure": "one controls access while the other holds evidence",
        "goal_conflict": "accuracy conflicts with a consequential deadline",
        "information_asymmetry": "each person knows a different material fact",
        "history_dependency": ["an earlier promise", "a later verification"],
        "coverage_requirements": coverage,
    }


class Gpt50ScenarioTest(unittest.TestCase):
    def test_rebuild_resume_skips_only_completed_v2_scenarios(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            target = output / "scenarios" / "scenario_001" / "scenario_001.json"
            run = output / "authoring" / "scenario_001" / "run_manifest.json"
            target.parent.mkdir(parents=True)
            run.parent.mkdir(parents=True)
            run.write_text(json.dumps({
                "status": "candidate_generated_pending_human_gate1",
                "model_routes_sha256": "routes-hash",
                "prompts": {
                    prompt_id: prompt_manifest()["prompts"][prompt_id]
                    for prompt_id in (
                        "scenario_candidate_script_v2",
                        "scenario_candidate_quality_gate_v1",
                        "scenario_candidate_core_v1",
                        "scenario_candidate_runtime_design_v2",
                "scenario_evaluated_persona_backfill_v1",
                        "scenario_candidate_state_values_v1",
                        "scenario_candidate_expression_triggers_v1",
                    )
                },
            }), encoding="utf-8")
            with patch(
                "scripts.generate_gpt50_scenarios.validate_scenario"
            ):
                target.write_text(json.dumps({
                    "state_contract_version": "socialflux_state_v1",
                }), encoding="utf-8")
                self.assertFalse(_scenario_complete(
                    output,
                    1,
                    "routes-hash",
                    required_contract_version="socialflux_state_v2",
                ))
                target.write_text(json.dumps({
                    "state_contract_version": "socialflux_state_v2",
                    "evaluated_agent_role": {
                        "persona": {
                            "name": "Test Agent",
                            "role": "Test Role",
                            "core_values": ["care"],
                            "temperament": ["steady"],
                            "communication_style": "clear",
                            "decision_style": "deliberate",
                            "conflict_style": "direct",
                            "boundaries": ["no deception"],
                        },
                    },
                }), encoding="utf-8")
                self.assertTrue(_scenario_complete(
                    output,
                    1,
                    "routes-hash",
                    required_contract_version="socialflux_state_v2",
                ))

    def test_source_ratio_is_exact_three_to_seven(self):
        sources = [
            source_type_for_ordinal(ordinal)
            for ordinal in range(1, TOTAL_COUNT + 1)
        ]
        self.assertEqual(sources.count("narrative-derived"), NARRATIVE_COUNT)
        self.assertEqual(
            sources.count("synthetic-script"),
            TOTAL_COUNT - NARRATIVE_COUNT,
        )
        for start in range(0, TOTAL_COUNT, 10):
            window = sources[start:start + 10]
            self.assertEqual(window.count("narrative-derived"), 3)
            self.assertEqual(window.count("synthetic-script"), 7)

    def test_curated_matrix_covers_fifty_unique_domains(self):
        self.assertEqual(len(CURATED_CONTEXTS), 50)
        self.assertEqual(len(SOURCE_WORKS), NARRATIVE_COUNT)
        briefs = [curated_brief(ordinal) for ordinal in range(1, TOTAL_COUNT + 1)]
        domains = [item["coverage_requirements"]["domain"] for item in briefs]
        self.assertEqual(len(domains), len(set(domains)))
        self.assertTrue(all(len(item["history_dependency"]) >= 2 for item in briefs))

    def test_batch_preserves_requested_identities(self):
        requested = [requested_identity(1), requested_identity(4)]
        value = {"briefs": [brief_for(item) for item in requested]}
        self.assertEqual(validate_brief_batch(value, requested), value["briefs"])

    def test_narrative_requires_source_work(self):
        identity = requested_identity(1)
        brief = brief_for(identity)
        del brief["coverage_requirements"]["source_work"]
        with self.assertRaisesRegex(ValueError, "source_work"):
            validate_brief_batch({"briefs": [brief]}, [identity])

    def test_synthetic_forbids_source_work(self):
        identity = requested_identity(4)
        brief = brief_for(identity)
        brief["coverage_requirements"]["source_work"] = {
            "title": "A Film",
            "medium": "film",
        }
        with self.assertRaisesRegex(ValueError, "must not name"):
            validate_brief_batch({"briefs": [brief]}, [identity])

    def test_identity_contains_no_parent_catalog_reference(self):
        for ordinal in (1, 15, 50):
            identity = requested_identity(ordinal)
            self.assertNotIn("qwen", str(identity).lower())
            self.assertNotIn("scale300", str(identity).lower())



if __name__ == "__main__":
    unittest.main()
