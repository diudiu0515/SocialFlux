import copy
import json
import unittest

from evaluation.t4_batch import aggregate_scores, modality_audit, summarize
from evaluation.t4_evaluation import T4_DIMENSIONS, public_t4_judge_packet, validate_t4_judgment
from tasks.T4.answering import build_judge_messages


def fixture():
    scenario = {
        "scenario_id": "case", "background": "SECRET_WORLD_CONTEXT",
        "policy_background": "Known public facts", "opening_response": "What do you propose?",
        "evaluated_agent_role": {"name": "A", "role": "reporter", "explicit_goal": "Get agreement",
                                 "hidden_intention": "SECRET_EVALUATED_INTENTION"},
        "environment_agent": {"persona": {"name": "B", "role": "editor"}, "hidden_intention": "SECRET_OTHER_INTENTION"},
    }
    trajectory = {"trajectory_id": "episode", "scenario_id": "case",
                  "policy_provenance": {"observation_condition": "text_only"},
                  "ending": {"reason": "natural_completion", "turn_id": 1},
                  "turns": [{"turn_id": "t1", "policy_action": {"text": "Let's agree", "private": "SECRET_ACTION"},
                             "environment_response": "Agreed", "observable_expression": {"text": "SECRET_CUE"},
                             "state_after": {"trust": 9}, "media": [{"media_type": "video", "asset_status": "planned",
                                                                        "asset_url": None, "event_family": "SECRET_FAMILY"}]}]}
    return scenario, trajectory


def judgment():
    return {"dimensions": {key: {"score": 6, "evidence_turn_ids": ["t1"], "rationale": "Observed agreement",
                                   "uncertainty": "External outcome pending", "insufficient_evidence": False}
                            for key in T4_DIMENSIONS},
            "overall_uncertainty": "Single judge", "human_validation_status": "not_human_validated"}


class T4ScoringTest(unittest.TestCase):
    def test_public_packet_removes_private_background_role_and_cue_metadata(self):
        scenario, trajectory = fixture()
        packet = public_t4_judge_packet(trajectory, scenario)
        self.assertNotIn("SECRET_", json.dumps(packet))
        self.assertEqual(packet["public_background"], "Known public facts")
        self.assertEqual(packet["opening_response"], scenario["opening_response"])
        self.assertEqual(packet["ending"], trajectory["ending"])
        self.assertEqual(set(packet["rubric"]["anchors"]), set(T4_DIMENSIONS))

    def test_judge_video_requires_actual_assets_and_preserves_text(self):
        scenario, trajectory = fixture()
        packet = public_t4_judge_packet(trajectory, scenario)
        with self.assertRaises(ValueError):
            build_judge_messages(packet, trajectory, "text_video")
        trajectory["turns"][0]["media"][0].update(asset_status="available", asset_url="https://example.test/clip.mp4")
        text = build_judge_messages(packet, trajectory)[0]["content"]
        video = build_judge_messages(packet, trajectory, "text_video")[0]["content"]
        self.assertEqual(video[0], {"type": "text", "text": text})
        self.assertEqual(video[2]["type"], "video_url")
        self.assertNotIn("SECRET_FAMILY", json.dumps(video))

    def test_policy_modality_never_inferred_from_planned_or_final_video(self):
        _, trajectory = fixture()
        self.assertEqual(modality_audit(trajectory)["policy_video_observations"], 0)
        trajectory["policy_provenance"]["observation_condition"] = "text_video"
        with self.assertRaises(ValueError):
            modality_audit(trajectory)
        trajectory["turns"][0]["observation"] = {"media": [{"media_type": "video", "asset_status": "available", "asset_url": "https://example.test/clip.mp4"}]}
        self.assertEqual(modality_audit(trajectory)["policy_video_observations"], 1)

    def test_null_recovery_preserves_comparable_core_score(self):
        value = judgment()
        value["dimensions"]["recovery"].update(score=None, insufficient_evidence=True)
        validate_t4_judgment(value, ["t1"])
        scores = aggregate_scores(value)
        self.assertEqual(scores["core_four_mean"], 6)
        self.assertEqual(scores["available_dimension_mean"], 6)
        self.assertIsNone(scores["five_dimension_mean"])
        value["dimensions"]["goal_achievement"].update(score=None, insufficient_evidence=True)
        with self.assertRaises(ValueError):
            validate_t4_judgment(value, ["t1"])

    def test_scores_require_integer_valid_evidence_and_real_explanations(self):
        for changes in ({"score": True}, {"score": 6.5}, {"evidence_turn_ids": []},
                        {"evidence_turn_ids": ["t2"]}, {"rationale": None},
                        {"evidence_turn_ids": ["t1", "t1"]}):
            value = judgment()
            value["dimensions"]["risk_management"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_t4_judgment(value, ["t1"])

    def test_summary_excludes_missing_and_pairs_only_same_scenario(self):
        row = {"scenario_id": "a", "status": "completed", "modality": {"policy_condition": "text_only"},
               "scores": aggregate_scores(judgment())}
        other = copy.deepcopy(row)
        other.update(scenario_id="b", modality={"policy_condition": "text_video"})
        summary = summarize([row, other, {"status": "source_unavailable"}])
        self.assertEqual(summary["matched_scenarios"], 0)
        self.assertIsNone(summary["paired_text_video_minus_text"]["goal_achievement"]["mean"])
        other["scenario_id"] = "a"
        other["scores"]["goal_achievement"] = 8
        summary = summarize([row, other])
        self.assertEqual(summary["paired_text_video_minus_text"]["goal_achievement"]["mean"], 2)
        self.assertEqual(summary["conditions"]["text_only"]["n"], 1)


if __name__ == "__main__":
    unittest.main()
