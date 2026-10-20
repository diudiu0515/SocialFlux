import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evaluation.t4_human_review import export_human_review
from tests.test_t4_scoring import fixture


class HumanReviewTest(unittest.TestCase):
    def test_blind_evidence_has_no_machine_scores_private_state_or_model_label(self):
        scenario, trajectory = fixture()
        trajectory['policy_provenance']['model'] = 'SECRET_MODEL'
        trajectory['scores'] = {'goal_achievement': 10}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = export_human_review(trajectory, scenario, root / 'episode', root / 'review')
            content = Path(result['packet']).read_text()
            self.assertNotIn('SECRET_', content)
            self.assertNotIn('policy_provenance', content)
            self.assertNotIn('"scores"', content)
            packet = json.loads(content)['evidence']
            self.assertEqual(packet['observable_trajectory'][0]['evaluated_action']['text'], "Let's agree")
            form = json.loads(Path(result['rating_form']).read_text())
            self.assertEqual(form['rating_status'], 'pending')
            self.assertTrue(all(v['score'] is None for v in form['dimensions'].values()))

    def test_export_preserves_human_entries_and_rejects_changed_evidence(self):
        scenario, trajectory = fixture()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = export_human_review(trajectory, scenario, root / 'episode', root / 'review')
            form_path = Path(result['rating_form'])
            form = json.loads(form_path.read_text())
            form['reviewer_id'] = 'human-1'
            form_path.write_text(json.dumps(form))
            export_human_review(trajectory, scenario, root / 'episode', root / 'review')
            self.assertEqual(json.loads(form_path.read_text())['reviewer_id'], 'human-1')
            trajectory['turns'][0]['environment_response'] = 'Different response'
            with self.assertRaisesRegex(ValueError, 'evidence changed'):
                export_human_review(trajectory, scenario, root / 'episode', root / 'review')


if __name__ == '__main__':
    unittest.main()
