"""Oracle evidence is frozen to actual sources and stays outside test inputs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from offline.oracle import BANK, ROOT, bound_source, canonical_expression, evidence_packet, patch_item, validate_t2_replay
from offline.choice_builder import save
from tasks.offline_choice import public_instance
from tasks.offline_choice import validate_item
from offline.oracle_release import relabel_rationale, LETTER


class OracleEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = [json.loads(line) for line in (BANK / "items.jsonl").read_text().splitlines()]

    def test_t1_excludes_future_and_unrecorded_states(self):
        item = next(x for x in self.items if x["task"] == "T1")
        packet = evidence_packet(item, ROOT / "build/test_oracle")
        self.assertEqual([t["turn_id"] for t in packet["prefix"]], ["t1", "t2"])
        self.assertNotIn("branches", packet)
        self.assertEqual(set(packet["allowed_state_paths"]), set(packet["initial_state"]))
        public = json.dumps(public_instance(item))
        for key in ("private_character", "initial_state", "state_judgments", "oracle_reference"):
            self.assertNotIn(key, public)

    def test_source_hash_tampering_is_rejected(self):
        source = deepcopy(self.items[0]["authoring"]["construction_source"])
        source["trajectory_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash"):
            bound_source(source, "trajectory")

    def test_option_rotation_preserves_history_labels(self):
        text = "历程A为7，B为5；选项A正确，选项B错误，A:t2不能改。"
        selected = [text.index("选项A") + 2, text.index("选项B") + 2]
        result = relabel_rationale(text, {"A": "B", "B": "C", "C": "D", "D": "A"}, selected)
        self.assertEqual(result, "历程A为7，B为5；选项B正确，选项C错误，A:t2不能改。")
        self.assertNotIn(text.index("A:t2"), [m.start() for m in LETTER.finditer(text)])

    def test_partial_public_expression_adds_only_empty_cues(self):
        expression = {"facial_expression": "专注", "behavioral_cues": ["停顿"]}
        normalized = canonical_expression(expression)
        self.assertEqual(normalized["facial_expression"], "专注")
        self.assertEqual(normalized["gaze"], "")
        self.assertEqual(normalized["speech_style"], "")
        self.assertEqual(expression, {"facial_expression": "专注", "behavioral_cues": ["停顿"]})

    def test_t3_has_actual_complete_action_specific_windows(self):
        item = next(x for x in self.items if x["task"] == "T3")
        packet = evidence_packet(item, ROOT / "build/test_oracle")
        self.assertEqual(len(packet["branches"]), 2)
        self.assertTrue(all(len(b["turns"]) == 5 for b in packet["branches"]))
        self.assertIn("action_1:immediate", packet["evidence_ids"])
        self.assertIn("action_2:step5", packet["evidence_ids"])

    def test_immediate_oracle_cannot_claim_later_branch_evidence(self):
        item = deepcopy(next(x for x in self.items if x["task"] == "T3" and x["target_spec"]["horizon"] == "immediate"))
        item["authoring"]["oracle_reference"] = {"evidence_ids": ["action_1:step2"]}
        with self.assertRaisesRegex(ValueError, "later branch"):
            validate_item(item)

    def test_oracle_combination_cannot_degrade_to_single_variable(self):
        item = deepcopy(next(x for x in self.items if x["subtype"] == "joint_comparison"))
        variable = item["target_spec"]["target_state_ids"][0]
        item["target_spec"]["target_state_ids"] = [variable]
        item["analysis"]["state_bindings"] = [b for b in item["analysis"]["state_bindings"] if b["state_id"] == variable]
        for letter, values in item["authoring"]["option_variable_map"].items():
            item["authoring"]["option_variable_map"][letter] = {k: v for k, v in values.items() if k.split("@")[0] == variable}
        item["authoring"]["oracle_reference"] = {"evidence_ids": ["private:A:ending"]}
        with self.assertRaisesRegex(ValueError, "two recorded"):
            validate_item(item)

    def test_t2_wrong_controlled_ending_cannot_be_reused(self):
        item = next(x for x in self.items if x["task"] == "T2" and x["authoring"]["replay_status"] == "validated")
        source = item["authoring"]["construction_source"]
        trajectory, replay = bound_source(source, "trajectory"), bound_source(source, "replay")
        replay["b"]["environment_response"] = "different ending"
        with self.assertRaisesRegex(ValueError, "T2 replay"):
            validate_t2_replay(item, trajectory, replay)

    def test_proposal_cannot_select_missing_state_or_mint_gt(self):
        item = next(x for x in self.items if x["task"] == "T1")
        packet = evidence_packet(item, ROOT / "build/test_oracle")
        proposal = {k: deepcopy(item[k]) for k in ("instance_id", "subtype", "question", "options", "target_spec")}
        proposal.update({k: deepcopy(item["authoring"][k]) for k in
                         ("answer", "rationale", "evidence_ids", "counterevidence_ids", "option_errors", "option_variable_map")})
        proposal.update(oracle_rationale="actual checkpoint evidence", oracle_evidence_ids=["private:t2"],
                        unresolved_issues=[], changes="unchanged")
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            artifact = Path(directory) / "result.json"
            save(artifact.with_name("evidence.json"), packet)
            result = patch_item(item, proposal, packet, artifact)
            self.assertIsNone(result["ground_truth"])
            self.assertFalse(result["authoring"]["source_admission"]["formal_admitted"])
            self.assertEqual(public_instance(result), public_instance(item))
            proposal["target_spec"]["target_state_ids"] = ["relationship.unknown_variable"]
            with self.assertRaisesRegex(ValueError, "unrecorded"):
                patch_item(item, proposal, packet, artifact)


if __name__ == "__main__":
    unittest.main()
