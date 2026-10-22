"""Protect source identity and numeric evidence during the English migration."""
import unittest
import hashlib
import json
from pathlib import Path
from copy import deepcopy

from pipeline.localization import digest, translate_export
from scripts.localize_current_data import clean, same_structure, seed_pairs, translate_tree
from scripts.publish_english_data import encode, rebind_documents
from tasks.offline_choice import answer_prompt, validate_item


class CurrentDataLocalizationTest(unittest.TestCase):
    def test_translation_changes_text_only_and_keeps_matching_evidence(self):
        original = {
            'instance_id': 'SFV2-001-T1-01', 'answer': 'B', 'difficulty': 'hard',
            'state': {'trust': 4, 'delta': -1}, 'human_verified': False,
            'options': {'A': '已发送。', 'B': '尚未发送。'},
            'history': ['尚未发送。'], 'empirical_difficulty': None,
        }
        cache = {digest('已发送。'): 'It has been sent.',
                 digest('尚未发送。'): 'It has not been sent.'}
        result = translate_tree(original, cache)
        same_structure(original, result)
        self.assertEqual(result['options']['B'], result['history'][0])
        self.assertEqual(result['answer'], 'B')
        self.assertEqual(result['difficulty'], 'hard')
        self.assertEqual(original['history'][0], '尚未发送。')
        result['state']['trust'] = 5
        with self.assertRaises(AssertionError):
            same_structure(original, result)
        with self.assertRaisesRegex(AssertionError, 'Textual evidence IDs changed'):
            same_structure('截至 t2，支持 action_1。', 'By t3, action_1 is supported.')
        with self.assertRaisesRegex(AssertionError, 'Explicit time changed'):
            same_structure('7:28仍是明确界限。', 'The cutoff still applies.')
        with self.assertRaisesRegex(AssertionError, 'Dialogue summary lost'):
            same_structure('evaluated_agent: 我会发送。 environment_agent: 尚未发送。', 'I will send it.')

    def test_cleanup_removes_raw_call_copies_and_chinese_source_quotes_only(self):
        original = {'turns': [{'turn_id': 't1', 'state_before': {'trust': 4},
            'state_judgments': [{'evidence_span': 'I will send it.', 'source_evidence_span': '我会发送。'}],
            'state_appraisal_call': {'request_messages': ['中文历史']},
            'environment_snapshot_before': {'state': {'trust': 4}, 'history': ['尚未发送。']}}]}
        removed = []
        result = clean(original, removed)
        self.assertNotIn('state_appraisal_call', result['turns'][0])
        self.assertNotIn('source_evidence_span', result['turns'][0]['state_judgments'][0])
        self.assertEqual(result['turns'][0]['environment_snapshot_before'],
                         original['turns'][0]['environment_snapshot_before'])
        self.assertEqual(removed[0]['sha256'], digest(original['turns'][0]['state_appraisal_call']))
        self.assertNotIn('中文历史', str(removed))

    def test_preexisting_english_translation_is_reused_without_translating_english(self):
        cache = {}
        seed_pairs({'turns': [{'text': '尚未发送。'}]},
                   {'turns': [{'text': 'It has not been sent.'}]}, cache)
        self.assertEqual(translate_tree('尚未发送。', cache), 'It has not been sent.')
        self.assertEqual(translate_tree('GPT50_001', cache), 'GPT50_001')
        with self.assertRaises(KeyError):
            translate_tree('未翻译', cache)
        with self.assertRaises(ValueError):
            translate_tree({'中文结构键': 1}, cache)

    def test_rebinding_propagates_source_hash_through_packet(self):
        documents = {'trajectory.json': {'text': 'I will send it.', 'trust': 4},
                     'packet.json': {'trajectory_sha256': 'old-trajectory'}}
        result, mapping = rebind_documents(documents, {
            'trajectory.json': 'old-trajectory', 'packet.json': 'old-packet'})
        self.assertEqual(result['packet.json']['trajectory_sha256'],
                         hashlib.sha256(encode(result['trajectory.json'])).hexdigest())
        self.assertEqual(mapping['old-packet'], hashlib.sha256(encode(result['packet.json'])).hexdigest())
        self.assertEqual(result['trajectory.json']['trust'], 4)

    def test_english_numbered_actions_keep_schema_and_english_answer_instruction(self):
        path = Path(__file__).resolve().parents[1] / 'tasks/examples/offline_scenarios_v2/items.jsonl'
        item = next(json.loads(s) for s in path.read_text().splitlines() if json.loads(s)['task'] == 'T3')
        item = deepcopy(item)
        for i, action in enumerate(item['input']['candidate_actions'], 1):
            action['label'] = f'Action {i}'
        validate_item(item)
        item['metadata']['language'] = 'en'
        self.assertTrue(answer_prompt(item).startswith('Using the supplied background'))
        item['input']['candidate_actions'][0]['label'] = 'A'
        with self.assertRaises(ValueError):
            validate_item(item)

    def test_english_only_export_does_not_reintroduce_source_quotes(self):
        import tempfile
        from tests.test_localization import Provider
        source = {'turns': [{'turn_id': 't1', 'policy_action': {'text': '我会发送。'},
                            'state_judgments': [{'evidence_span': '我会发送。'}]}]}
        with tempfile.TemporaryDirectory() as directory:
            output = translate_export({}, source, Provider(), Path(directory) / 'cache.json',
                                      preserve_source_evidence=False)
        self.assertNotIn('source_evidence_span', output['rollout']['turns'][0]['state_judgments'][0])


if __name__ == '__main__':
    unittest.main()
