import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evaluation.t4_batch import save, summarize
from evaluation.t4_dispatch import delegate_unstarted_scenarios


class DispatchTest(unittest.TestCase):
    def prepare(self, root):
        source, target = root / 'source', root / 'target'
        save(source / 'plan.json', {'config': {'scenario_ids': ['A', 'B']}, 'providers': {'gpt': {}}})
        return source, target

    def test_delegation_never_counts_as_success_and_keeps_destination(self):
        with TemporaryDirectory() as directory:
            source, target = self.prepare(Path(directory))
            result = delegate_unstarted_scenarios(source, target, ['B'], ['gpt'])
            self.assertEqual(result['episode_count'], 2)
            rows = [json.loads(p.read_text()) for p in source.glob('episodes/*/*/*/result.json')]
            summary = summarize(rows)
            self.assertEqual(summary['status_counts'], {'delegated_to_run': 2})
            self.assertEqual(summary['conditions']['text_video']['n'], 0)
            self.assertFalse((target / 'episodes').exists())
            self.assertTrue(all(r['destination_result'].startswith(str(target)) for r in rows))

    def test_any_existing_partial_blocks_transfer_before_writing_records(self):
        with TemporaryDirectory() as directory:
            source, target = self.prepare(Path(directory))
            save(source / 'episodes/B/gpt/text_only/checkpoint.json', {'turns': ['retained']})
            with self.assertRaisesRegex(ValueError, 'already has'):
                delegate_unstarted_scenarios(source, target, ['A', 'B'], ['gpt'])
            self.assertFalse((source / 'episodes/A').exists())
            self.assertEqual(json.loads((source / 'episodes/B/gpt/text_only/checkpoint.json').read_text())['turns'], ['retained'])


if __name__ == '__main__':
    unittest.main()
