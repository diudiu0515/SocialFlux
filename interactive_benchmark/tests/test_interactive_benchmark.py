import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "interactive_benchmark" / "scripts"))
from convert_interactive_to_benchmark import records, paths_to


class InteractiveBenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.story_paths = [
            ROOT / "worlds" / "IA001" / "story.json",
            ROOT / "worlds" / "IA002" / "story.json",
        ]
        cls.stories = [json.loads(path.read_text()) for path in cls.story_paths]

    def test_expected_instance_counts(self):
        rows_by_story = {story["scenario"]["scenario_id"]: list(records(story)) for story in self.stories}
        self.assertEqual(len(rows_by_story["IA001"]), 24)
        self.assertEqual(len(rows_by_story["IA002"]), 24)
        all_rows = rows_by_story["IA001"] + rows_by_story["IA002"]
        self.assertEqual(len(all_rows), 48)
        self.assertEqual(len({row["instance_id"] for row in all_rows}), 48)

    def test_exactly_five_t1_semantic_instances_per_world(self):
        for story in self.stories:
            rows = [row for row in records(story) if row["task_type"] == "T1_state_tracking"]
            semantic_ids = {row["semantic_instance_id"] for row in rows}
            self.assertEqual(len(semantic_ids), 5)
            self.assertEqual(len(rows), 10)
            self.assertEqual(sum(row["modality"] == "text" for row in rows), 5)
            self.assertEqual(sum(row["modality"] == "text_video" for row in rows), 5)
            for semantic_id in semantic_ids:
                variants = {row["variant_id"] for row in rows if row["semantic_instance_id"] == semantic_id}
                self.assertEqual(variants, {"text", "text_video"})

    def test_t1_v02_definition_and_history(self):
        risk_state_ids = {"graduation_risk", "job_risk", "user_safety_risk"}
        for story in self.stories:
            for row in records(story):
                if row["task_type"] != "T1_state_tracking":
                    continue
                self.assertGreaterEqual(row["metadata"]["history_length_rounds"], 8)
                self.assertEqual(row["input"]["history_view"], "full_history")
                self.assertEqual(row["target_spec"]["prediction_format"], "subjective_state_tracking_v0.2")
                self.assertEqual(
                    row["target_spec"]["intensity_labels"],
                    ["absent", "mild", "moderate", "strong", "very_strong", "cannot_determine"],
                )
                self.assertFalse(row["target_spec"]["require_self_reported_confidence"])
                self.assertTrue(row["target_spec"]["require_intensity_probability_distribution"])
                self.assertTrue(risk_state_ids.isdisjoint(row["target_spec"]["target_state_ids"]))
                self.assertIn("change_anchor_node_id", row["input"])
                self.assertIn("semantic_instance_id", row)
                self.assertIn("variant_id", row)

    def test_exactly_four_t3_semantic_instances_per_world(self):
        for story in self.stories:
            rows = [row for row in records(story) if row["task_type"] == "T3_counterfactual_choice_effect"]
            semantic_ids = {row["semantic_instance_id"] for row in rows}
            self.assertEqual(len(semantic_ids), 4)
            self.assertEqual(len(rows), 8)
            self.assertEqual(sum(row["modality"] == "text" for row in rows), 4)
            self.assertEqual(sum(row["modality"] == "text_video" for row in rows), 4)
            for semantic_id in semantic_ids:
                paired = [row for row in rows if row["semantic_instance_id"] == semantic_id]
                self.assertEqual({row["variant_id"] for row in paired}, {"text", "text_video"})
                self.assertEqual(len({json.dumps(row["input"]["candidate_options"], sort_keys=True) for row in paired}), 1)
            for row in rows:
                self.assertEqual(row["input"]["history_view"], "full_history")
                self.assertEqual(row["target_spec"]["prediction_format"], "counterfactual_option_effects_v0.2")
                self.assertEqual(row["target_spec"]["time_horizons"], ["immediate", "delayed"])
                self.assertEqual(row["target_spec"]["change_direction_labels"], ["increase", "similar", "decrease", "cannot_determine"])
                self.assertFalse(row["target_spec"]["require_self_reported_confidence"])
                self.assertGreaterEqual(len(row["target_spec"]["target_state_ids"]), 6)
                self.assertLessEqual(len(row["target_spec"]["target_state_ids"]), 10)
                self.assertGreaterEqual(len(row["input"]["candidate_options"]), 2)
                self.assertLessEqual(len(row["input"]["candidate_options"]), 4)

    def test_author_effects_never_exposed(self):
        for story in self.stories:
            serialized = "\n".join(json.dumps(row, ensure_ascii=False) for row in records(story))
            self.assertNotIn('"effects"', serialized)
            self.assertNotIn('"flags_set"', serialized)
            self.assertTrue(all(row["ground_truth"] is None for row in records(story)))

    def test_t2_has_identical_current_scene(self):
        for story in self.stories:
            rows = [row for row in records(story) if row["task_type"] == "T2_history_sensitive_merge"]
            semantic_ids = {row["semantic_instance_id"] for row in rows}
            self.assertEqual(len(semantic_ids), 3)
            self.assertEqual(len(rows), 6)
            self.assertEqual(sum(row["modality"] == "text" for row in rows), 3)
            self.assertEqual(sum(row["modality"] == "text_video" for row in rows), 3)
            for semantic_id in semantic_ids:
                paired = [row for row in rows if row["semantic_instance_id"] == semantic_id]
                self.assertEqual({row["variant_id"] for row in paired}, {"text", "text_video"})
                self.assertEqual(len({row["metadata"]["shared_current_scene_hash"] for row in paired}), 1)
            for row in rows:
                self.assertTrue(row["metadata"]["controlled_current_scene"])
                self.assertIn("shared_current_scene", row["input"])
                self.assertNotEqual(
                    row["metadata"]["canonical_history_a_choice_path"],
                    row["metadata"]["canonical_history_b_choice_path"],
                )
                self.assertEqual(row["target_spec"]["prediction_format"], "pairwise_state_difference_v0.2")
                self.assertEqual(
                    row["target_spec"]["direction_labels"],
                    ["higher_in_a", "similar", "higher_in_b", "cannot_determine"],
                )
                self.assertFalse(row["target_spec"]["require_self_reported_confidence"])
                self.assertTrue(row["target_spec"]["require_causal_choice_probabilities"])
                self.assertGreaterEqual(len(row["target_spec"]["candidate_causal_choice_ids"]), 2)
                self.assertGreaterEqual(len(row["target_spec"]["target_state_ids"]), 6)
                self.assertLessEqual(len(row["target_spec"]["target_state_ids"]), 10)

    def test_all_configured_selectors_resolve(self):
        for story in self.stories:
            for comparison in story["benchmark_design"]["merge_comparisons"]:
                paths = paths_to(story, comparison["merge_node_id"])
                choice_paths = [[c["option_id"] for c in path["choices"]] for path in paths]
                self.assertIn(comparison["history_a"]["choice_path"], choice_paths)
                self.assertIn(comparison["history_b"]["choice_path"], choice_paths)


if __name__ == "__main__":
    unittest.main()
