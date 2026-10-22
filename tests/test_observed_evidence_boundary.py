from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from environment.observation import build_initial_policy_observation, build_policy_observation
from environment.public_situation import build_policy_situation, policy_narrative_reference, render_public_background
from rollout.configuration import load_rollout_config
from rollout.runner import _actual_request_counts, _provider_run_metrics
from environment.policy_context import public_scenario_context
from environment.interaction_ledger import initial_ledger
from schemas.validate import validate_scenario
from environment.state_transition_contract import validate_state_transition_environment_config
from environment.env import StatefulEnvironment
from environment.independent_appraisal import ModelStateAppraiser, ModelInteractionAppraiser
from environment.appraisal_context import build_appraisal_context
from environment.response_generator import ModelResponseGenerator
from scripts import validate_state_context_samples as v


class ObservedEvidenceBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = json.loads(Path('data/gpt50/experiment/scenario/scenarios_state_v3/scenario_003/scenario_003.json').read_text())

    def test_undisclosed_environment_fact_is_private_but_retained_for_environment(self):
        secret = next(x for x in self.scenario['narrative_design']['relevant_history'] if 'not yet disclosed' in x)
        observed = build_initial_policy_observation(self.scenario)
        self.assertNotIn(secret, json.dumps(observed))
        self.assertEqual(observed['public_situation']['relevant_history'], [])
        self.assertIn(secret, render_public_background(self.scenario))
        self.assertEqual(observed['background'], '')  # Unreviewed mixed context fails closed.

    def test_explicit_public_grants_preserve_order_and_are_content_bound(self):
        scenario = deepcopy(self.scenario)
        scenario['policy_visible_narrative'] = [
            policy_narrative_reference(scenario, path)
            for path in ('relevant_history.1', 'relationship_structure', 'relevant_history.0')]
        public = build_policy_situation(scenario)
        self.assertEqual(public['relationship_structure'], scenario['narrative_design']['relationship_structure'])
        self.assertEqual(public['relevant_history'], scenario['narrative_design']['relevant_history'][:2])
        scenario['narrative_design']['relevant_history'][0] += ' A newly introduced private fact.'
        with self.assertRaisesRegex(ValueError, 'stale'):
            build_policy_situation(scenario)

    def test_unknown_duplicate_and_malformed_grants_fail_closed(self):
        for grants in ({}, [{'path':'information_asymmetry','sha256':'x'}],
                       [{'path':'relevant_history.99','sha256':'x'}],
                       [policy_narrative_reference(self.scenario,'relevant_history.0')]*2):
            with self.subTest(grants=grants):
                scenario=deepcopy(self.scenario);scenario['policy_visible_narrative']=grants
                with self.assertRaises(ValueError):
                    build_policy_situation(scenario)

    def test_real_disclosures_in_observed_history_remain_visible(self):
        history=[{'turn_id':1,'role':'environment_agent','text':'I now disclose the conflict.'}]
        observed=build_policy_observation(self.scenario, {'history':history})
        self.assertEqual(observed['history'],history)

    def test_mixed_background_cannot_leak_through_initial_ledger(self):
        scenario=deepcopy(self.scenario)
        scenario['background']='PRIVATE_WORLD_FACT_NOT_DISCLOSED'
        ledger=initial_ledger(scenario['background'])
        before=deepcopy(ledger)
        observed=build_policy_observation(scenario, {'interaction_ledger':ledger})
        self.assertNotIn('PRIVATE_WORLD_FACT_NOT_DISCLOSED',json.dumps(observed))
        self.assertEqual(ledger,before)
        scenario['policy_background']='Publicly known publication deadline.'
        observed=build_policy_observation(scenario, {'interaction_ledger':ledger})
        self.assertEqual(observed['background'],scenario['policy_background'])
        self.assertEqual(observed['conversation_progress']['established_facts'],[])
        scenario['shared_background']='A jointly known deadline.'
        observed=build_policy_observation(scenario, {'interaction_ledger':ledger})
        self.assertEqual(observed['conversation_progress']['established_facts'][0]['text'],scenario['shared_background'])
        self.assertNotIn('PRIVATE_WORLD_FACT_NOT_DISCLOSED',json.dumps(public_scenario_context(scenario)))
        self.assertIn('PRIVATE_WORLD_FACT_NOT_DISCLOSED',render_public_background(scenario))

    def test_actual_later_disclosure_is_not_removed_by_secret_text_filter(self):
        scenario=deepcopy(self.scenario);scenario['policy_background']='A public meeting.'
        ledger=initial_ledger('PRIVATE_FACT')
        disclosed={'id':'t1:environment_agent:fact','turn_id':'t1','speaker':'environment_agent','text':'PRIVATE_FACT'}
        ledger['established_facts'].append(disclosed)
        observed=build_policy_observation(scenario,{'interaction_ledger':ledger})
        self.assertEqual(observed['conversation_progress']['established_facts'][-1],disclosed)

    def test_six_candidate_views_are_populated_without_known_secrets(self):
        base=v.BASE/'observed_evidence_v6_pilot_preparation'
        manifest=v.load(base/'manifest.json')
        for case in manifest['cases']:
            scenario=v.load(v.ROOT/case['candidate']);source=v.load(v.ROOT/case['source'])
            with self.subTest(scenario=case['scenario_id']):
                validate_scenario(scenario)
                observed=build_initial_policy_observation(scenario)
                self.assertGreater(len(observed['background']),100)
                self.assertEqual(scenario['background'],source['background'])
                self.assertEqual(scenario['initial_state'],source['initial_state'])
                self.assertEqual(scenario['initial_dynamics'],source['initial_dynamics'])
                rendered=json.dumps(observed)
                environment=StatefulEnvironment(scenario,state_updater=object(),response_generator=object())
                real_observation=environment.reset()
                self.assertEqual(real_observation['background'],scenario['policy_background'])
                self.assertEqual(environment.session['interaction_ledger']['established_facts'][0]['text'],scenario['shared_background'])
                env_text=render_public_background(scenario)
                if case['scenario_id']=='GPT50_003':
                    self.assertNotIn('off-hours consulting fees',rendered)
                    self.assertIn('consulting fees',env_text)
                if case['candidate'].endswith('claude_044.json'):
                    self.assertNotIn('nine attended sessions',rendered)
                    self.assertNotIn('recent missed appointment',rendered)
                    self.assertIn('nine attended sessions',env_text)
                    self.assertNotIn('workplace-training language',env_text)
                if case['candidate'].endswith('gpt_026.json'):
                    self.assertIn('private reconciliation',rendered)
                    self.assertNotIn('reconciliation',env_text)
                    self.assertIn('handwritten amendment',env_text)
                    self.assertNotIn('handwritten amendment',rendered)
                if case['candidate'].endswith('claude_014.json'):
                    self.assertIn('exclude Mara from management',rendered)
                    self.assertNotIn('exclude Mara',env_text)
                    self.assertIn('owner plans to sell',env_text)
                    self.assertNotIn('owner plans to sell',rendered)

    def test_independent_interaction_call_is_counted(self):
        def provider(n):
            return SimpleNamespace(metrics={'request_count':n,'request_duration_seconds':n,'usage':{'total_tokens':n}})
        environment=SimpleNamespace(state_updater=SimpleNamespace(provider=provider(3),interaction_appraiser=SimpleNamespace(provider=provider(5))),response_generator=SimpleNamespace(provider=provider(7)))
        policy=SimpleNamespace(provider=provider(2))
        counts=_actual_request_counts(environment,policy)
        self.assertEqual(counts['total'],17)
        self.assertEqual(counts['environment_stage_count_per_turn'],3)
        self.assertEqual(_provider_run_metrics(environment,policy)['totals']['usage']['total_tokens'],17)

    def test_natural_early_stop_is_allowed_without_loosening_component_contract(self):
        env=load_rollout_config(v.CONFIG)['environment']
        env['minimum_natural_turns']=1
        self.assertIsNotNone(validate_state_transition_environment_config(env,explicit=True))
        for invalid in (0,2,True):
            env['minimum_natural_turns']=invalid
            with self.assertRaises(ValueError):
                validate_state_transition_environment_config(env,explicit=True)

    def test_shadow_preparation_has_six_first_pass_unpadded_slots(self):
        from scripts.run_role_visible_shadow_pilot import assemble
        plans=assemble()
        self.assertEqual(len(plans),6)
        self.assertEqual(sum(p['case']['policy']=='gpt' for p in plans),3)
        for plan in plans:
            self.assertEqual(plan['environment']['minimum_natural_turns'],1)
            self.assertEqual(plan['policy']['minimum_natural_turns'],1)
            self.assertEqual(plan['scenario']['max_turns'],20)
            self.assertEqual(plan['policy']['runs'],1)
            self.assertFalse(plan['environment']['response_opportunity_guidance'])

    def test_role_aware_actual_requests_do_not_reintroduce_author_secrets(self):
        scenario=v.load(v.BASE/'observed_evidence_v6_pilot_preparation/scenarios/claude_014.json')
        class ResponseCapture:
            prompt_id='environment_response_v31_contrastive_event_driven'
            def generate(self,context):
                self.context=deepcopy(context)
                self.messages=ModelResponseGenerator(object(),prompt_id=self.prompt_id)._build_request(context)[1]
                raise v.Captured()
        response=ResponseCapture()
        env=StatefulEnvironment(scenario,state_updater=object(),response_generator=response,response_opportunity_guidance=False)
        env.reset()
        action={'text':'请说明你目前考虑的可行安排。'}
        kwargs=dict(action=action,previous_state=scenario['initial_state'],previous_dynamics=scenario['initial_dynamics'],
                    memory={'relevant_turn_ids':[]},interaction_ledger=env.session['interaction_ledger'],
                    appraisal_context=build_appraisal_context(history=[],turns=[],action=action,current_turn_id=1,interaction_ledger=env.session['interaction_ledger']))
        for appraiser_class,prompt in [(ModelStateAppraiser,'environment_state_appraisal_v6_observed_evidence'),(ModelInteractionAppraiser,'environment_interaction_appraisal_v1')]:
            capture=v.Capture()
            with self.assertRaises(v.Captured):
                appraiser_class(scenario,capture,prompt_id=prompt).appraise(**kwargs)
            text=json.dumps(capture.request,ensure_ascii=False)
            self.assertNotIn('scenario_initialization_rationale',text)
            self.assertNotIn('scenario_transition_evidence',text)
            self.assertNotIn('excludes Mara from governance',text)
            self.assertIn('owner plans to sell',text)
        transition={'transition':{'appraisal':{}},'response_ledger':env.session['interaction_ledger'],
                    'memory_view':{},'state_after':scenario['initial_state'],'dynamics_after':scenario['initial_dynamics']}
        with self.assertRaises(v.Captured):
            env._run_response_stage({'turn_id':1,'action':action},transition,None)
        self.assertNotIn('state_transition_opportunity',response.context)
        text=json.dumps(response.messages,ensure_ascii=False)
        self.assertNotIn('excluding Mara from governance',text)
        self.assertIn('owner plans to sell',text)

    def test_v6_removes_hypothetical_targets_without_changing_definitions_or_history(self):
        saved=v.load(v.OUTPUT / 'prepared_requests.json')
        env=load_rollout_config(v.CONFIG)['environment']
        for item in saved[:10]:
            with self.subTest(case=item['case']['case_id']):
                with patch.object(v,'PROMPT','environment_state_appraisal_v6_observed_evidence'):
                    current=v.prepare_case(item['case'],env)['payload']
                old=deepcopy(item['payload'])
                for entry in old['state_semantics']['variables'].values():
                    entry.pop('scenario_transition_evidence',None)
                old['state_semantics']['interpretation']=current['state_semantics']['interpretation']
                self.assertEqual(current,old)
                self.assertNotIn('scenario_transition_evidence',json.dumps(current))


if __name__=='__main__':
    unittest.main()
