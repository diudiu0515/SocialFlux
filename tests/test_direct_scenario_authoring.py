import unittest

from schemas.validate import (
    QUALITY_CHECKS, validate_blueprint, validate_private_persona,
    validate_v2_dynamics,
)
from scripts.generate_scale300_candidates import (
    _assemble_candidate,
    _blueprint_core_validator,
    _blueprint_validator,
    _validate_brief,
    _quality_validator,
)


class DirectScenarioAuthoringTest(unittest.TestCase):

    def _v2_blueprint(self):
        return {
            "scenario_id": "V2_001",
            "title": "v2 candidate",
            "mechanism": "conflicting obligations",
            "source": {"type": "synthetic-script"},
            "narrative_design": {},
            "background": "A bounded conflict.",
            "state_contract_version": "socialflux_state_v2",
            "environment_agent": {
                "persona": {
                    "name": "甲",
                    "role": "负责人",
                    "core_values": ["可靠", "公平"],
                    "temperament": ["谨慎", "克制"],
                    "communication_style": "直接但礼貌",
                    "decision_style": "证据优先",
                    "conflict_style": "先澄清再设边界",
                    "boundaries": ["不承诺未经核验的结果"],
                },
                "explicit_goal": "完成核验",
                "hidden_intention": "避免重复承担他人错误",
            },
            "evaluated_agent_role": {
                "character_id": "EVALUATED_AGENT",
                "name": "乙",
                "role": "项目伙伴",
                "explicit_goal": "获得可靠决定",
            },
            "selected_state_variables": {
                "emotion": ["anxiety"],
                "behavioral_disposition": ["evidence_seeking"],
                "relationship": ["trust"],
                "consequence_risk": ["goal_failure_risk"],
            },
            "target_state_ids": ["relationship.trust"],
        }

    def test_v2_blueprint_enforces_four_state_families(self):
        blueprint = self._v2_blueprint()
        self.assertIs(validate_blueprint(blueprint), blueprint)
        drifted = dict(blueprint)
        drifted["selected_state_variables"] = {
            "emotion": ["anxiety"],
            "behavioral_disposition": ["evidence_seeking"],
            "relationship": ["trust"],
            "pressure": ["deadline_pressure"],
        }
        with self.assertRaisesRegex(ValueError, "exactly emotion"):
            validate_blueprint(drifted)

    def test_v2_persona_rejects_dynamic_state_traits(self):
        persona = dict(self._v2_blueprint()["environment_agent"]["persona"])
        persona["current_trust"] = "low"
        with self.assertRaisesRegex(ValueError, "persona fields"):
            validate_private_persona(persona)

    def test_v2_dynamics_are_flat_external_conditions(self):
        valid = {"deadline_pressure": 7, "negotiation_openness": 4}
        self.assertIs(validate_v2_dynamics(valid), valid)
        with self.assertRaisesRegex(ValueError, "unapproved"):
            validate_v2_dynamics({"deadline_pressure": 7, "goal_failure_risk": 6})
    def test_blueprint_core_rejects_prose_in_list_fields(self):
        brief = {
            "scenario_id": "IA_PIPE_001",
            "source_type": "synthetic-script",
            "provenance_id": "direct-001",
        }
        core = {
            "scenario_id": "IA_PIPE_001",
            "title": "candidate",
            "mechanism": "conflict",
            "source": {
                "type": "synthetic-script",
                "provenance_id": "direct-001",
                "surface_text_policy": "original_surface_text",
                "redistribution_status": "original_synthetic_script",
            },
            "narrative_design": {
                "relationship_structure": "collaborators",
                "power_structure": "asymmetric authority",
                "goal_conflict": "accuracy versus deadline",
                "information_asymmetry": "different records",
                "relevant_history": "one prose history",
                "meaningful_choice_space": "three choices in prose",
            },
            "background": "A deadline creates a bounded conflict.",
        }
        with self.assertRaisesRegex(ValueError, "relevant_history"):
            _blueprint_core_validator(core, brief)

    def test_blueprint_rejects_string_persona(self):
        brief = {
            "scenario_id": "IA_PIPE_001",
            "source_type": "synthetic-script",
            "provenance_id": "direct-001",
        }
        blueprint = {
            "scenario_id": "IA_PIPE_001",
            "title": "candidate",
            "mechanism": "conflict",
            "source": {
                "type": "synthetic-script",
                "provenance_id": "direct-001",
            },
            "narrative_design": {},
            "background": "background",
            "state_contract_version": "socialflux_state_v2",
            "environment_agent": {
                "persona": "name: role",
                "explicit_goal": "goal",
                "hidden_intention": "intention",
            },
            "evaluated_agent_role": {"character_id": "EVALUATED_AGENT"},
            "selected_state_variables": {"trust": ["working_trust", "repair_intent"], "risk": ["failure_risk", "delay_risk"]},
            "target_state_ids": ["trust.working_trust"],
            "multimodal_event_concepts": [],
            "suggested_horizon": 20,
        }
        with self.assertRaisesRegex(ValueError, "persona must be an object"):
            _blueprint_validator(blueprint, brief)

    def test_quality_validator_preserves_pending_human_boundary(self):
        report = {
            "format": "socialflux_source_quality_v1",
            "source_type": "synthetic-script",
            "checks": {key: "pass" for key in QUALITY_CHECKS},
            "recommendation": "pass",
            "summary": "bounded candidate",
            "review_status": "pending_human_review",
        }
        self.assertIs(_quality_validator(report, "synthetic-script"), report)

    def test_brief_has_no_parent_catalog_input(self):
        brief = {
            "scenario_id": "IA_PIPE_001",
            "source_type": "synthetic-script",
            "provenance_id": "direct-001",
            "mechanism": "conflicting obligations",
            "relationship_structure": "long-term collaborators",
            "power_structure": "asymmetric public authority",
            "goal_conflict": "deadline and disclosure conflict",
            "information_asymmetry": "each holds different evidence",
            "history_dependency": ["earlier promise", "later verification"],
            "coverage_requirements": {"domain": "community work"},
        }
        self.assertIs(_validate_brief(brief), brief)
        self.assertFalse(any("parent" in key for key in brief))

    def test_blueprint_rejects_scalar_or_description_map_state_variables(self):
        base = {
            "scenario_id": "IA_PIPE_001",
            "title": "candidate",
            "mechanism": "conflict",
            "source": {"type": "synthetic-script"},
            "narrative_design": {},
            "background": "background",
            "environment_agent": {},
            "evaluated_agent_role": {},
            "target_state_ids": ["trust.working_trust"],
        }
        for invalid in (
            {"trust": "working_trust", "risk": ["failure_risk", "delay_risk"], "goal": ["clarity"]},
            {"trust": {"working_trust": "description"}, "risk": ["failure_risk"], "goal": ["clarity", "openness"]},
        ):
            with self.assertRaisesRegex(ValueError, "non-empty array"):
                validate_blueprint({**base, "selected_state_variables": invalid})

    def test_machine_output_remains_pending_human_gate1(self):
        blueprint = {
            "scenario_id": "IA_PIPE_001",
            "title": "候选场景",
            "mechanism": "conflicting obligations",
            "source": {
                "type": "synthetic-script",
                "provenance_id": "direct-001",
                "surface_text_policy": "original_surface_text",
                "redistribution_status": "original_synthetic_script",
            },
            "narrative_design": {
                "relationship_structure": "长期合作者",
                "power_structure": "公开权限不对称",
                "goal_conflict": "披露与期限冲突",
                "information_asymmetry": "双方掌握不同证据",
                "relevant_history": ["此前共同承诺核对失败"],
                "meaningful_choice_space": ["核对", "有限披露", "延迟并设条件"],
            },
            "background": "五天后截止，两天后有可核验记录。",
            "environment_agent": {
                "persona": {"name": "甲", "role": "负责人"},
                "explicit_goal": "按时更新进展",
                "hidden_intention": "避免独自承担声誉损失",
            },
            "evaluated_agent_role": {
                "character_id": "EVALUATED_AGENT",
                "name": "乙",
                "role": "项目伙伴",
                "explicit_goal": "确保披露准确并公平分担责任",
            },
            "selected_state_variables": {"emotion": ["anxiety"], "relationship": ["trust"]},
            "target_state_ids": ["emotion.anxiety", "relationship.trust"],
        }
        proposal = {
            "initial_state": {"emotion": {"anxiety": 4}, "relationship": {"trust": 6}},
            "initial_dynamics": {"disclosure_risk": 4},
            "observable_expression": {"default": {"speech_style": "克制"}},
            "media_generation": {"stage": "structured_expression"},
            "video_triggers": [
                {
                    "trigger_id": f"trigger_{index}",
                    "trigger_mode": "threshold",
                    "conditions": {"emotion.anxiety": {"operator": ">=", "threshold": 7 + index}},
                    "priority": index + 1,
                    "cooldown_turns": 2,
                    "cue_template": f"cue_{index}",
                    "observable_expression": {"speech_style": "变化"},
                }
                for index in range(3)
            ],
            "max_turns": 20,
            "t3_delayed_horizon": 5,
            "sampling_plan": {},
            "rationale": {"emotion.anxiety": "期限压力"},
            "trigger_reachability": [],
            "status": "candidate_pending_human_freeze",
        }
        quality = {"checks": {key: "pass" for key in QUALITY_CHECKS}}
        scenario = _assemble_candidate(blueprint, proposal, quality)
        self.assertEqual(
            scenario["construction_status"]["quality_gate"],
            "pending_human_review",
        )
        self.assertEqual(
            scenario["construction_status"]["initial_state"],
            "candidate_pending_human_freeze",
        )


if __name__ == "__main__":
    unittest.main()
