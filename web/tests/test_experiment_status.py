import json
import unittest

from web.experiment_status import load_experiment_status,model_summary,process_alive


class ExperimentStatusTests(unittest.TestCase):
    def test_denominators_na_and_delegated_slots_preserved(self):
        value=model_summary({
            'status_counts':{'completed':2,'failed':1,'delegated_to_run':66},
            'conditions':{'text_only':{'n':2,'metrics':{
                'recovery':{'n':0,'mean':None},'five_dimension_mean':{'n':0,'mean':None},
                'core_four_mean':{'n':2,'mean':8.1}}}},
            'matched_scenarios':0,'paired_text_video_minus_text':{},
            'private_state':'SHOULD_NOT_APPEAR','provider':{'api_key':'SHOULD_NOT_APPEAR'}})
        self.assertEqual(value['status_counts']['completed'],2)
        self.assertEqual(value['status_counts']['delegated_to_run'],66)
        self.assertIsNone(value['conditions']['text_only']['metrics']['five_dimension_mean']['mean'])
        self.assertNotIn('SHOULD_NOT_APPEAR',json.dumps(value))
        self.assertNotIn('core_four_mean',json.dumps(value))

    def test_current_gate_and_bank_snapshot_is_not_human_approval(self):
        data=load_experiment_status()
        self.assertEqual([g['id'] for g in data['gates']],['Gate 1','Gate 2','Gate 3','Gate 4'])
        self.assertEqual(data['rollouts']['expected'],50)
        self.assertEqual(data['offline']['item_count'],300)
        self.assertEqual(data['offline']['t2_replay_pending_scenes'],0)
        self.assertEqual(data['offline']['formal_admitted'],0)
        self.assertEqual(data['offline']['human_labeled'],0)
        self.assertTrue(all(g['formal_status']=='pending' for g in data['gates']))
        self.assertEqual(len(data['gates'][1]['experiments']),9)
        self.assertTrue(data['sources'])

    def test_snapshot_does_not_include_calls_trajectories_or_private_states(self):
        data=load_experiment_status()
        forbidden={'messages','api_key','trajectory','appraisal','state_before','state_after','hidden_intention','persona'}
        def visit(value):
            if isinstance(value,dict):
                self.assertFalse(value.keys() & forbidden)
                for child in value.values():visit(child)
            elif isinstance(value,list):
                for child in value:visit(child)
        visit(data)
        self.assertFalse(process_alive(-1,'irrelevant'))


if __name__=='__main__':unittest.main()
