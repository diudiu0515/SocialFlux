import json
import unittest
from copy import deepcopy
from unittest.mock import patch
from scripts.run_unified_gpt50_corrected import corrected_plans
from scripts.resume_unified_gpt50 import OUT as WRONG
from pipeline.runtime import build_environment_factory,build_policy
from environment.unified_appraisal import UnifiedEnvironmentFactory

class Captured(BaseException): pass

class GPT50HorizonRepairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plans,_=corrected_plans()
        cls.turn=json.loads((WRONG/'01_GPT50_002_gpt/trajectory.json').read_text())['turns'][0]

    def environment(self):
        p=self.plans[1]
        env=UnifiedEnvironmentFactory(build_environment_factory(p['scenario'],p['environment']))()
        env.reset();return env

    def test_all_fifty_inherit_the_established_horizon(self):
        self.assertEqual(len({p['case']['scenario_id'] for p in self.plans}),50)
        for p in self.plans:
            env=UnifiedEnvironmentFactory(build_environment_factory(p['scenario'],p['environment']))()
            policy=build_policy(p['policy'])
            self.assertEqual((env.minimum_natural_turns,env.response_generator.minimum_natural_turns,policy.minimum_natural_turns),(10,10,10))
            self.assertTrue(env.response_opportunity_guidance)
            self.assertEqual(p['policy']['runs'],1)

    def test_actual_policy_and_response_requests_include_depth_guidance(self):
        env=self.environment();p=self.plans[1];t=self.turn
        policy=build_policy(p['policy'])
        messages,_=policy._build_request(env.observe())
        self.assertIn('before its minimum effective history depth',json.dumps(messages))
        captured={}
        def capture(context):
            captured['context']=deepcopy(context)
            captured['messages']=env.response_generator._build_request(context)[1]
            raise Captured()
        frame=env._begin_turn(t['policy_action'])
        transition_result={'transition':{'appraisal':t['appraisal']},'response_ledger':t['interaction_ledger_before'],
                           'state_numeric':t['numeric_state_delta'],'state_after':t['state_after'],
                           'dynamics_after':t['dynamics_after'],'memory_view':t['memory_view']}
        with patch.object(env.response_generator,'generate',side_effect=capture):
            with self.assertRaises(Captured): env._run_response_stage(frame,transition_result,None)
        self.assertIn('before its minimum effective history depth',json.dumps(captured['messages']))
        self.assertTrue(captured['context']['state_transition_opportunity'])

    def test_identical_school_can_close_does_not_end_at_turn_one(self):
        env=self.environment();t=self.turn
        frame=env._begin_turn(t['policy_action'])
        transition={'transition':{'appraisal':t['appraisal']},'state_after':t['state_after'],'dynamics_after':t['dynamics_after']}
        response={'ledger_after':t['interaction_ledger_after'],'text':t['environment_response'],
                  'ledger_events':t['environment_response_ledger_events']}
        env._finish_turn(frame,transition,response)
        self.assertEqual(env.session['status'],'active')
        frame['turn_id']=10
        env._finish_turn(frame,transition,response)
        self.assertEqual(env.session['ending'],{'reason':'natural_completion','turn_id':10})

if __name__=='__main__':unittest.main()
