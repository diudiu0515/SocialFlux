import unittest

from tasks.T1.answering import answer_prompt as t1_answer_prompt
from tasks.T1.answering import validate_answer as validate_t1
from tasks.T3.action_authoring import validate_actions
from tasks.T3.answering import (
    answer_prompt as t3_answer_prompt, canonicalize_instance,
    validate_answer as validate_t3,
)


class TaskAnsweringTest(unittest.TestCase):

    def test_author_answer_prompt_sees_private_persona_without_mutating_instance(self):
        t1 = {
            "instance_id": "private_t1",
            "input": {"history": [{"turn_id": "t1"}]},
            "target_spec": {"target_state_ids": ["relationship.trust"]},
        }
        marker = "PRIVATE_PERSONA_ANSWER_MARKER_4C2D"
        persona = {"conflict_style": marker}
        rendered = t1_answer_prompt(t1, persona)
        self.assertIn(marker, rendered)
        self.assertNotIn("persona", t1)

        t3 = {
            "instance_id": "private_t3",
            "input": {
                "history": [{"turn_id": "t1"}],
                "current_observation": {"turn_id": "t2"},
                "candidate_actions": [{"text": "a"}],
            },
            "target_spec": {"target_state_ids": ["relationship.trust"]},
        }
        self.assertIn(marker, t3_answer_prompt(t3, persona))
        self.assertNotIn("persona", t3)

    def test_t1_contract(self):
        instance = {
            "instance_id": "x_t1",
            "input": {"history": [{"turn_id": "t1"}]},
            "target_spec": {"target_state_ids": ["emotion.anger"]},
        }
        answer = {
            "instance_id": "x_t1",
            "predictions": [{
                "state_id": "emotion.anger",
                "intensity_probabilities": {
                    "absent": 0, "mild": 0, "moderate": 1, "strong": 0,
                    "very_strong": 0, "cannot_determine": 0,
                },
                "change_probabilities": {
                    "increase": 0.7, "similar": 0.2, "decrease": 0,
                    "cannot_determine": 0.1,
                },
                "evidence_turn_ids": ["t1"],
                "confidence": 0.8,
            }],
        }
        self.assertEqual(validate_t1(answer, instance), answer)

    def test_t3_actions_and_answer_contract(self):
        validate_actions({"actions": [
            {"text": "我想先核对记录。", "strategy": "核对"},
            {"text": "我不同意现在推进。", "strategy": "拒绝"},
            {"text": "可以先做可撤回的小范围尝试。", "strategy": "折中"},
        ]})
        instance = {
            "instance_id": "x_t3",
            "input": {
                "history": [{"turn_id": "t1"}],
                "current_observation": {"turn_id": "t2"},
                "candidate_actions": [{"text": "a"}, {"text": "b"}],
            },
            "target_spec": {"target_state_ids": ["relationship.trust"]},
        }
        distribution = {
            "increase": 0.5, "similar": 0.2, "decrease": 0.1,
            "cannot_determine": 0.2,
        }
        answer = {
            "instance_id": "x_t3",
            "options": [{
                "action_index": index,
                "state_predictions": [{
                    "state_id": "relationship.trust",
                    "immediate": dict(distribution),
                    "delayed": dict(distribution),
                    "evidence_turn_ids": ["t2"],
                }],
            } for index in range(2)],
        }
        self.assertEqual(validate_t3(answer, instance), answer)

    def test_rejects_invisible_evidence(self):
        instance = {
            "instance_id": "x_t1",
            "input": {"history": [{"turn_id": "t1"}]},
            "target_spec": {"target_state_ids": ["emotion.anger"]},
        }
        answer = {
            "instance_id": "x_t1",
            "predictions": [{
                "state_id": "emotion.anger",
                "intensity_probabilities": {
                    "absent": 1, "mild": 0, "moderate": 0, "strong": 0,
                    "very_strong": 0, "cannot_determine": 0,
                },
                "change_probabilities": {
                    "increase": 0, "similar": 1, "decrease": 0,
                    "cannot_determine": 0,
                },
                "evidence_turn_ids": ["t9"],
                "confidence": 1,
            }],
        }
        with self.assertRaisesRegex(ValueError, "evidence"):
            validate_t1(answer, instance)

    def test_t3_legacy_numeric_turn_ids_are_canonicalized(self):
        instance = {
            "instance_id": "x_t3",
            "input": {
                "history": [{"turn_id": 1}],
                "current_observation": {"turn_id": 2},
                "candidate_actions": [{"text": "a"}, {"text": "b"}],
            },
            "target_spec": {"target_state_ids": ["relationship.trust"]},
        }
        normalized = canonicalize_instance(instance)
        self.assertEqual(normalized["input"]["history"][0]["turn_id"], "t1")
        self.assertEqual(normalized["input"]["current_observation"]["turn_id"], "t2")
        self.assertEqual(instance["input"]["history"][0]["turn_id"], 1)


if __name__ == "__main__":
    unittest.main()
