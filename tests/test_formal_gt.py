import unittest

from annotation.formal_gt import build_annotation_packets, finalize_ground_truth


class FormalGroundTruthTest(unittest.TestCase):
    def setUp(self):
        self.instances = [{
            "instance_id": "i1",
            "task_type": "T1_state_tracking",
            "language": "zh",
            "modality": "text",
            "input": {"history": [{"turn_id": "t1", "text": "公开历史"}]},
            "target_spec": {"target_state_ids": ["emotion.anger"]},
            "metadata": {"source_trajectory_id": "private-source"},
        }]
        self.packets = build_annotation_packets(self.instances)

    def test_packets_are_blinded_and_require_three_annotators(self):
        packet = self.packets[0]
        self.assertNotIn("metadata", packet)
        self.assertEqual(packet["required_annotators"], 3)

    def test_three_human_votes_finalize(self):
        annotation_id = self.packets[0]["annotation_id"]
        packet_sha256 = self.packets[0]["packet_sha256"]
        label = {"predictions": [{"state_id": "emotion.anger", "intensity": "medium", "change": "increase", "evidence_turn_ids": ["t1"]}]}
        votes = [{
            "annotation_id": annotation_id,
            "annotator_id": f"human-{index}",
            "human_attestation": True,
            "packet_sha256": packet_sha256,
            "annotated_at_utc": "2026-09-06T02:00:00Z",
            "label": label,
        } for index in range(3)]
        result = finalize_ground_truth(self.packets, votes, [])
        self.assertEqual(result["records"][0]["label_status"], "formal_human_gt")
        self.assertEqual(result["fleiss_kappa_exact_label"], 1.0)

    def test_disagreement_cannot_skip_adjudication(self):
        annotation_id = self.packets[0]["annotation_id"]
        packet_sha256 = self.packets[0]["packet_sha256"]
        changes = ("increase", "decrease", "similar")
        votes = [{
            "annotation_id": annotation_id,
            "annotator_id": f"human-{index}",
            "human_attestation": True,
            "packet_sha256": packet_sha256,
            "annotated_at_utc": "2026-09-06T02:00:00Z",
            "label": {"predictions": [{"state_id": "emotion.anger", "intensity": "medium", "change": changes[index], "evidence_turn_ids": ["t1"]}]},
        } for index in range(3)]
        with self.assertRaisesRegex(ValueError, "adjudication"):
            finalize_ground_truth(self.packets, votes, [])

    def test_automation_cannot_claim_human_attestation(self):
        annotation_id = self.packets[0]["annotation_id"]
        packet_sha256 = self.packets[0]["packet_sha256"]
        label = {"predictions": [{"state_id": "emotion.anger", "intensity": "medium", "change": "increase", "evidence_turn_ids": ["t1"]}]}
        votes = [{
            "annotation_id": annotation_id,
            "annotator_id": f"worker-{index}",
            "human_attestation": False,
            "packet_sha256": packet_sha256,
            "annotated_at_utc": "2026-09-06T02:00:00Z",
            "label": label,
        } for index in range(3)]
        with self.assertRaisesRegex(ValueError, "human_attestation"):
            finalize_ground_truth(self.packets, votes, [])

    def test_arbitrary_json_label_is_rejected(self):
        packet = self.packets[0]
        votes = [{
            "annotation_id": packet["annotation_id"],
            "annotator_id": f"human-{index}",
            "human_attestation": True,
            "packet_sha256": packet["packet_sha256"],
            "annotated_at_utc": "2026-09-06T02:00:00Z",
            "label": {"direction": "increase"},
        } for index in range(3)]
        with self.assertRaisesRegex(ValueError, "T1 human label"):
            finalize_ground_truth(self.packets, votes, [])

    def test_t2_and_t3_contracts_are_embedded(self):
        instances = [
            {
                "instance_id": "i2", "task_type": "T2_history_sensitive_merge",
                "language": "zh", "modality": "text",
                "input": {"history_a": [], "history_b": [], "shared_current_observation": {}},
                "target_spec": {"target_state_ids": ["relationship.trust"]},
            },
            {
                "instance_id": "i3", "task_type": "T3_counterfactual_choice_effect",
                "language": "zh", "modality": "text",
                "input": {"candidate_actions": [{"text": "A"}, {"text": "B"}]},
                "target_spec": {"target_state_ids": ["relationship.trust"]},
            },
        ]
        packets = build_annotation_packets(instances)
        self.assertEqual(packets[0]["annotation_contract"]["direction_labels"], ["cannot_determine", "higher_in_a", "higher_in_b", "similar"])
        self.assertEqual(packets[1]["annotation_contract"]["action_indices"], [0, 1])

    def test_tampered_packet_hash_is_rejected(self):
        packet = self.packets[0]
        packet["input"] = {"history": [{"text": "tampered"}]}
        with self.assertRaisesRegex(ValueError, "packet_sha256"):
            finalize_ground_truth([packet], [], [])


if __name__ == "__main__":
    unittest.main()
