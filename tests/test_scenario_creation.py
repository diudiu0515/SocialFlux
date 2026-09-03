import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from schemas.validate import QUALITY_CHECKS, validate_scenario
from scripts import scenario_sources


BASE = json.loads(
    Path("configs/scenarios/scenario_001/scenario_001.json").read_text(encoding="utf-8")
)


class StaticProvider:
    provenance = {"provider": "test-double", "model": "scenario-smoke"}

    def __init__(self, result):
        self.result = result

    def complete(self, messages, **generation):
        return json.dumps(self.result, ensure_ascii=False)


class ScenarioCreationSmokeTest(unittest.TestCase):
    def _common(self, source, output):
        return {
            "input": source,
            "provider_config": Path("unused-provider.json"),
            "output": output,
            "temperature": 0.2,
            "seed": 7,
        }

    def test_narrative_structure_extraction_contract(self):
        structure = {
            "source_work": {"title": "Example Work", "medium": "film"},
            "abstract_mechanism": "authority under incomplete evidence",
            "relationship_structure": "expert adviser and accountable decision maker",
            "power_structure": "one controls action while the other controls interpretation",
            "goal_conflict": "speed conflicts with evidentiary confidence",
            "information_asymmetry": "each party holds different operational facts",
            "longitudinal_dependency": [
                "an earlier warning changed trust",
                "a delayed disclosure changes later interpretations",
            ],
            "adaptation_boundaries": [
                "confidence must be calibrated over time",
                "neither total compliance nor refusal always succeeds",
            ],
            "elements_to_discard": [
                "character names", "dialogue", "distinctive objects", "plot sequence",
            ],
            "originalization_requirements": [
                "new setting", "new characters", "new events", "new stakes",
            ],
            "redistribution_policy": "structural_abstraction_only_original_surface_text",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = root / "request.json"
            request.write_text(
                json.dumps({"title": "Example Work", "medium": "film"}),
                encoding="utf-8",
            )
            output = root / "structure.json"
            args = SimpleNamespace(**self._common(request, output))
            with patch.object(
                scenario_sources,
                "_provider",
                return_value=StaticProvider(structure),
            ):
                scenario_sources.extract_structure(args)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                structure,
            )

    def test_quality_normalization_initialization_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.md"
            source.write_text("一段具有真实冲突、信息差和长期后果的原创社会叙事。", encoding="utf-8")
            quality_path = root / "quality.json"
            quality = {
                "format": "socialflux_source_quality_v1",
                "source_type": BASE["source"]["type"],
                "checks": {key: "pass" for key in QUALITY_CHECKS},
                "recommendation": "pass",
                "summary": "结构可进入人工审核。",
                "review_status": "pending_human_review",
            }
            quality_args = SimpleNamespace(
                **self._common(source, quality_path),
                source_type=BASE["source"]["type"],
                provenance_id=BASE["source"]["provenance_id"],
            )
            with patch.object(scenario_sources, "_provider", return_value=StaticProvider(quality)):
                scenario_sources.quality_check(quality_args)
            saved_quality = json.loads(quality_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_quality["review_status"], "pending_human_review")

            blueprint_keys = {
                "scenario_id", "title", "mechanism", "source", "narrative_design",
                "background", "environment_agent", "evaluated_agent_role",
                "selected_state_variables", "target_state_ids",
            }
            blueprint = {key: BASE[key] for key in blueprint_keys}
            blueprint["multimodal_event_concepts"] = ["关系张力跨越显著阈值"]
            blueprint["suggested_horizon"] = BASE["max_turns"]
            blueprint_path = root / "blueprint.json"
            normalize_args = SimpleNamespace(
                **self._common(source, blueprint_path),
                source_type=BASE["source"]["type"],
                provenance_id=BASE["source"]["provenance_id"],
                quality_report=quality_path,
            )
            with patch.object(scenario_sources, "_provider", return_value=StaticProvider(blueprint)):
                with self.assertRaises(ValueError):
                    scenario_sources.normalize(normalize_args)

            saved_quality["review_status"] = "approved"
            quality_path.write_text(json.dumps(saved_quality, ensure_ascii=False), encoding="utf-8")
            with patch.object(scenario_sources, "_provider", return_value=StaticProvider(blueprint)):
                scenario_sources.normalize(normalize_args)

            proposal = {
                "initial_state": BASE["initial_state"],
                "initial_dynamics": BASE["initial_dynamics"],
                "observable_expression": BASE["observable_expression"],
                "media_generation": BASE["media_generation"],
                "video_triggers": BASE["video_triggers"],
                "max_turns": BASE["max_turns"],
                "t3_delayed_horizon": BASE["t3_delayed_horizon"],
                "sampling_plan": BASE["sampling_plan"],
                "rationale": {"summary": "由人物关系和初始事件推导。"},
                "trigger_reachability": ["初始未触发，互动中可达。"],
                "status": "candidate_pending_human_freeze",
            }
            scenario_path = root / "scenario_001.json"
            initialize_args = SimpleNamespace(**self._common(blueprint_path, scenario_path))
            with patch.object(scenario_sources, "_provider", return_value=StaticProvider(proposal)):
                scenario_sources.initialize(initialize_args)
            generated = json.loads(scenario_path.read_text(encoding="utf-8"))
            validate_scenario(generated)
            self.assertNotIn("multimodal_event_concepts", generated)
            self.assertNotIn("suggested_horizon", generated)
            self.assertEqual(
                generated["construction_status"]["initial_state"],
                "candidate_pending_human_freeze",
            )


if __name__ == "__main__":
    unittest.main()
