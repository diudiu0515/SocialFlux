import json
from pathlib import Path
import tempfile
import unittest

from pipeline.localization import EnglishOutputProvider, export_projection, translate_export
from scripts.recover_exploratory_response_budget import ReplayPrefixProvider
from pipeline.translation_checks import check_export, exact_span


class Provider:
    provenance = {'provider': 'test'}
    audit_records = []

    def __init__(self):
        self.calls = []

    def complete(self, messages, **generation):
        self.calls.append(messages)
        if 'texts' in messages[-1]['content']:
            payload = json.loads(messages[-1]['content'])
            return json.dumps({'translations': [
                {'我会发送。': 'I will send it.', '尚未发送。': 'It has not been sent.',
                 '这只是承诺。': 'This is only a promise.'}[x] for x in payload['texts']]})
        return 'A new English response.'


class LocalizationTest(unittest.TestCase):
    def test_evidence_alignment_returns_actual_words_without_changing_meaning(self):
        self.assertEqual(exact_span('Both households have withdrawn.',
                                   'I cannot promise that; both households have withdrawn.'),
                         'both households have withdrawn')
        self.assertIsNone(exact_span('The funds have arrived', 'The funds may arrive'))
        self.assertEqual(exact_span('STRASSE', 'Straße'), 'Straße')

    def test_saved_prefix_is_not_regenerated_and_only_fresh_calls_change_language(self):
        messages = [{'role': 'system', 'content': 'Use one to three natural Chinese sentences.'},
                    {'role': 'user', 'content': '历史. Output one to three natural Chinese sentences.'}]
        provider = Provider()
        replay = ReplayPrefixProvider(EnglishOutputProvider(provider), [
            {'messages': messages, 'generation': {'seed': 2}, 'raw_output': '已生成原文'}], 'source')
        self.assertEqual(replay.complete(messages, seed=2), '已生成原文')
        self.assertEqual(provider.calls, [])
        self.assertEqual(replay.complete(messages, seed=3), 'A new English response.')
        self.assertIn('natural English sentences', provider.calls[0][0]['content'])
        self.assertIn('Output language: English.', provider.calls[0][0]['content'])
        self.assertEqual(provider.calls[0][1]['content'], '历史. Output one to three natural English sentences.')
        self.assertIn('Chinese sentences', messages[0]['content'])

    def test_translation_preserves_states_ids_originals_and_cache(self):
        scenario = {'scenario_id': 'S1', 'title': 'English title', 'initial_state': {'trust': 4}}
        trajectory = {'trajectory_id': 'T1', 'initial_state': {'trust': 4}, 'turns': [{
            'turn_id': 't1', 'policy_action': {'text': '我会发送。'},
            'environment_response': '尚未发送。', 'state_before': {'trust': 4},
            'state_after': {'trust': 4}, 'numeric_state_delta': {'trust': 0},
            'state_judgments': [{'variable': 'trust', 'judgment': 'no_relevant_evidence',
                'evidence_span': '我会发送。', 'rationale': '这只是承诺。'}],
            'state_appraisal_call': {'credential': 'not-for-export'},
        }]}
        source = json.dumps(trajectory, ensure_ascii=False)
        provider = Provider()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cache.json'
            translated = translate_export(scenario, trajectory, provider, path)
            again = translate_export(scenario, trajectory, provider, path)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(again, translated)
        self.assertEqual(translated['rollout']['trajectory_id'], 'T1')
        turn = translated['rollout']['turns'][0]
        self.assertEqual(turn['policy_action']['text'], 'I will send it.')
        self.assertEqual(turn['state_after'], {'trust': 4})
        self.assertEqual(turn['state_judgments'][0]['evidence_span'], 'I will send it.')
        self.assertEqual(turn['state_judgments'][0]['source_evidence_span'], '我会发送。')
        self.assertNotIn('not-for-export', json.dumps(translated))
        self.assertEqual(json.dumps(trajectory, ensure_ascii=False), source)
        self.assertEqual(translated['localization']['human_review_status'], 'pending')


if __name__ == '__main__':
    unittest.main()
