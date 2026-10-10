from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from scripts.auto_gate2_unified_gpt50 import UnifiedReplay,interpret,project_history
from scripts import auto_gate2_unified_gpt50 as gate2
from rollout.configuration import load_rollout_config
from unittest.mock import patch
from scripts.run_unified_gpt50_corrected import corrected_plans
from scripts.prepare_human_review_workspace import pending_e1_e2
from scripts.validate_state_context_samples import load,save

class StopCapture(BaseException): pass

class FollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plans,_=corrected_plans()

    def test_replay_uses_unified_appraisers_and_preserves_counterfactual_persona(self):
        from environment.unified_appraisal import UnifiedStateAppraiser,SchemaBoundInteractionAppraiser
        scenario=deepcopy(self.plans[1]['scenario'])
        scenario['environment_agent']['persona']['communication_style']='Patient and explicit.'
        with tempfile.TemporaryDirectory() as directory:
            runtime=UnifiedReplay(self.plans,directory)
            env=runtime.factory(scenario)()
            self.assertIsInstance(env.state_updater.state_appraiser,UnifiedStateAppraiser)
            self.assertIsInstance(env.state_updater.interaction_appraiser,SchemaBoundInteractionAppraiser)
            self.assertEqual(env.scenario['environment_agent']['persona']['communication_style'],'Patient and explicit.')
            env.reset()
            captured={}
            class Updater:
                def update(self,*,action,previous_state,previous_dynamics,memory,appraisal_context=None,interaction_ledger=None,current_event_id=None,longitudinal_context=None):
                    captured.update(context=appraisal_context,ledger=interaction_ledger,event=current_event_id)
                    raise StopCapture()
            env.state_updater=Updater()
            with self.assertRaises(StopCapture):interpret(env,{'text':'请先明确书面安排。'})
            self.assertIsNotNone(captured['context'])
            self.assertIsNotNone(captured['ledger'])
            self.assertEqual(captured['event'],'t1')

    def test_history_removal_cannot_survive_in_evidence_or_ledger(self):
        snapshot={'history':[{'turn_id':2,'text':'visible'}],
                  'turns':[{'turn_id':'t1','text':'REMOVED_SECRET'},{'turn_id':'t2','text':'visible'}],
                  'interaction_ledger':{'events':[{'turn_id':'t1','text':'REMOVED_SECRET'}],
                                        'latest_obligation':{'turn_id':'t1','text':'REMOVED_SECRET'}},
                  'state':{'trust':5},'dynamics':{'pressure':4}}
        result=project_history(snapshot)
        self.assertNotIn('REMOVED_SECRET',str(result))
        self.assertEqual(result['state'],snapshot['state'])
        self.assertEqual(result['dynamics'],snapshot['dynamics'])
        self.assertIn('REMOVED_SECRET',str(snapshot))

    def test_fifty_scenarios_are_not_fifty_policy_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(gate2,'DEST',Path(directory)):
                coverage=gate2.materialize(self.plans)
                config=load_rollout_config(Path(directory)/'rollout.runtime.json')
            self.assertEqual(len(coverage),50)
            self.assertEqual(config['candidate_strategy'],'single_first_pass')
            self.assertEqual(sum(p.get('runs',1) for p in config['policies']),1)

    def test_preparation_leaves_human_fields_pending_and_preserves_signed_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            pending_e1_e2(root,[],[])
            for name in ('state_transition_agreement.json','trajectory_plausibility.json'):
                record=load(root/name)['record']
                self.assertFalse(record['human_attestation'])
                self.assertEqual(record['review_status'],'pending_human')
            signed={'record':{'human_attestation':True,'reviewers':['human'],'agreement':0.9}}
            save(root/'state_transition_agreement.json',signed)
            pending_e1_e2(root,[],[])
            self.assertEqual(load(root/'state_transition_agreement.json'),signed)

if __name__=='__main__':unittest.main()
