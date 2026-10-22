from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from environment.actor_bound_appraisal import (
    ActorBoundEnvironmentFactory, ActorBoundStateAppraiser, BASE_PROMPT,
    RELATIONSHIP_DEFINITIONS, bind_messages, binding_context,
)
from environment.delta_mapper import apply_semantic_deltas
from pipeline.runtime import build_environment_factory
from scripts import validate_state_context_samples as v
from rollout.configuration import load_rollout_config


class ActorBoundAppraisalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = load_rollout_config(v.ROOT / 'configs/gpt50_experiment/rollout.state_observed_evidence_v6_candidate.json')['environment']
        cls.fixed = v.load(v.BASE / 'observed_evidence_v6_fixed/prepared_requests.json')
        cls.scenario = v.load(v.ROOT / cls.fixed[0]['case']['scenario'])

    def test_actual_wire_payload_binds_people_without_changing_evidence_rules(self):
        with patch.object(v, 'PROMPT', BASE_PROMPT):
            prepared = v.prepare_case(self.fixed[0]['case'], self.env)
        capture = v.Capture()
        with self.assertRaises(v.Captured):
            ActorBoundStateAppraiser(prepared['scenario'], capture, self.env['state_appraisal_sampling']).appraise(**prepared['kwargs'])
        actual = capture.request
        payload = json.loads(actual['messages'][1]['content'].split('## Input\n', 1)[1])
        old = deepcopy(prepared['payload'])
        binding = payload['state_semantics'].pop('actor_binding')
        self.assertEqual(binding['state_owner']['name'], 'Maren Quill')
        self.assertEqual(binding['relationship_target']['name'], 'Sera Dastan')
        for path, entry in payload['state_semantics']['variables'].items():
            prior = old['state_semantics']['variables'][path]
            self.assertIn('Maren Quill', entry['definition'])
            if path.startswith('relationship.'):
                self.assertIn('Sera Dastan', entry['definition'])
                self.assertEqual(entry['perspective']['relationship_target']['role_id'], 'evaluated_agent')
            else:
                self.assertIsNone(entry['perspective']['relationship_target'])
            entry.pop('perspective')
            entry['definition'] = prior['definition']
        self.assertEqual(payload, old)
        self.assertEqual(actual['generation'], prepared['request']['generation'])

    def test_every_relationship_construct_has_an_explicit_target(self):
        from environment.state_ontology import build_state_semantics
        scenario = deepcopy(self.scenario)
        scenario['initial_state']['relationship'] = {key: 5 for key in RELATIONSHIP_DEFINITIONS}
        scenario['selected_state_variables']['relationship'] = list(RELATIONSHIP_DEFINITIONS)
        # Build a minimal wire input while preserving production metadata.
        payload = {'state_semantics': build_state_semantics(scenario),
                   'state_variable_paths': ['relationship.' + key for key in RELATIONSHIP_DEFINITIONS]}
        request = [{'role': 'system', 'content': 'state'}, {'role': 'user', 'content': 'prompt\n## Input\n' + json.dumps(payload)}]
        bound = json.loads(bind_messages(request, scenario)[1]['content'].split('## Input\n')[1])
        for key in RELATIONSHIP_DEFINITIONS:
            entry = bound['state_semantics']['variables']['relationship.' + key]
            self.assertIn('Maren Quill', entry['definition'])
            self.assertIn('Sera Dastan', entry['definition'])

    def test_names_not_hardcoded_and_missing_identity_fails(self):
        scenario = deepcopy(self.scenario)
        scenario['environment_agent']['persona']['name'] = 'Different owner'
        scenario['evaluated_agent_role']['name'] = 'Different target'
        context = binding_context(scenario)
        self.assertEqual(context['state_owner']['name'], 'Different owner')
        self.assertEqual(context['relationship_target']['name'], 'Different target')
        scenario['environment_agent']['persona']['name'] = ''
        with self.assertRaises(ValueError):
            binding_context(scenario)

    def test_legacy_input_and_factory_remain_unchanged(self):
        before = deepcopy(self.fixed[0]['request']['messages'])
        bind_messages(before, self.scenario)
        self.assertEqual(before, self.fixed[0]['request']['messages'])
        factory = build_environment_factory(self.scenario, self.env)
        bound_factory = ActorBoundEnvironmentFactory(factory)
        env = bound_factory()
        self.assertIsInstance(env.state_updater.state_appraiser, ActorBoundStateAppraiser)
        self.assertEqual(env.provenance['actor_binding_profile'], 'state_actor_binding_v1')
        self.assertNotIn('actor_binding_profile', factory.provenance)
        self.assertEqual(env.state_updater.calibrator.profile, self.env['state_calibration_profile'])

    def test_strength_does_not_turn_update_off_and_mapping_is_deterministic(self):
        for value in (1, 4, 5, 8):
            for label, amount in [('mild_increase', 1), ('moderate_increase', 2), ('mild_decrease', -1)]:
                before = {'trust': value}
                expected = min(10, max(0, value + amount))
                results = [apply_semantic_deltas(before, {'trust': label}) for _ in range(2)]
                self.assertEqual(results[0], results[1])
                self.assertEqual(results[0][0]['trust'], expected)

    def test_real_reversed_rationale_is_preserved_for_review_not_silently_rewritten(self):
        from scripts.validate_actor_bound_state import cases
        with patch.object(v, 'PROMPT', BASE_PROMPT):
            prepared = v.prepare_case(cases()[12], self.env)
        calls = v.load(v.BASE / 'observed_evidence_v6_shadow_six/00_GPT50_002_gpt/calls/state_appraisal/requests.json')
        class SavedOutput:
            def complete(self, messages, **generation):
                self.messages = deepcopy(messages)
                return calls[1]['raw_output']
        provider = SavedOutput()
        result = ActorBoundStateAppraiser(prepared['scenario'], provider, self.env['state_appraisal_sampling']).appraise(**prepared['kwargs'])
        self.assertEqual(result['request_messages'], provider.messages)
        trust = next(j for j in result['state_judgments'] if j['variable'] == 'relationship.trust')
        self.assertIn('环境角色已被验证为可靠', trust['rationale'])
        self.assertEqual(trust['judgment'], 'no_relevant_evidence')
        self.assertTrue(all(x['semantic_orientation_status'] == 'requires_review' for x in result['perspective_review']))


if __name__ == '__main__':
    unittest.main()
