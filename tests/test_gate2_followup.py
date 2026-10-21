import tempfile
from pathlib import Path
import unittest
from evaluation.t4_multimodal import RequestBudget
from scripts.run_gate2_followup import count_leaves, recent_snapshot, aggregate_metrics


class Gate2FollowupTests(unittest.TestCase):
    def test_budget_reaches_forwarding_wrapper_network_leaf(self):
        class Leaf:
            def complete(self, messages, **kwargs): return 'result'
        class Wrapper:
            def __init__(self, provider): self.provider = provider
            def __getattr__(self, key): return getattr(self.provider, key)
            def complete(self, messages, **kwargs): return self.provider.complete(messages, **kwargs)
        with tempfile.TemporaryDirectory() as folder:
            budget = RequestBudget(Path(folder)/'budget.json', 1)
            p = count_leaves(Wrapper(Wrapper(Leaf())), budget)
            self.assertEqual(p.complete([]), 'result')
            self.assertEqual(budget.count, 1)
            with self.assertRaises(RuntimeError):p.complete([])

    def test_recent_history_removes_copies_and_keeps_state(self):
        snapshot = {'history':[{'turn_id':i} for i in range(1, 6)],
                    'turns':[{'turn_id':f't{i}'} for i in range(1, 6)],
                    'interaction_ledger':{'events':[{'turn_id':'t1'},{'turn_id':'t5'}]}, 'state':{'x':3}}
        result=recent_snapshot(snapshot)
        self.assertEqual([x['turn_id'] for x in result['history']], [3,4,5])
        self.assertEqual([x['turn_id'] for x in result['turns']], ['t3','t4','t5'])
        self.assertEqual(result['interaction_ledger']['events'], [{'turn_id':'t5'}])
        self.assertEqual(result['state'], snapshot['state'])
        self.assertEqual(len(snapshot['history']), 5)

    def test_no_pairs_is_unknown_not_perfect_stability(self):
        result=aggregate_metrics([{'errors':{'construction':{}}}], 'paraphrase')
        self.assertEqual(result['pairs'], 0)
        self.assertIsNone(result['direction_agreement'])

    def test_recent3_keeps_both_speakers_of_three_complete_turns(self):
        history = [{'turn_id': i, 'role': role} for i in range(1, 7) for role in ('evaluated_agent', 'environment_agent')]
        result = recent_snapshot({'history': history})
        self.assertEqual([row['turn_id'] for row in result['history']], [4, 4, 5, 5, 6, 6])


if __name__=='__main__':unittest.main()
