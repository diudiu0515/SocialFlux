from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from environment.unified_appraisal import UnifiedStateAppraiser, SchemaBoundInteractionAppraiser, UnifiedEnvironmentFactory, trust_policy
from environment.actor_bound_appraisal import BASE_PROMPT
from environment.interaction_wire_schema import interaction_wire_schema, validate_wire, validate_event_pairs
from environment.ledger_events import semantic_ledger_wire_contract, validate_semantic_ledger_events
from pipeline.runtime import build_environment_factory
from rollout.configuration import load_rollout_config
from scripts import validate_state_context_samples as v


class UnifiedAppraisalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = load_rollout_config(v.ROOT / 'configs/gpt50_experiment/rollout.state_observed_evidence_v6_candidate.json')['environment']
        cls.saved = v.load(v.BASE / 'actor_bound_v1_fixed/prepared_requests.json')

    def test_only_trust_evidence_entry_changes_in_state_actual_request(self):
        policy = trust_policy()
        for item in self.saved:
            with self.subTest(case=item['case']['case_id']), patch.object(v, 'PROMPT', BASE_PROMPT), patch.object(v, 'ModelStateAppraiser', UnifiedStateAppraiser):
                now = v.prepare_case(item['case'], self.env)
            restored = deepcopy(now['payload'])
            entry = restored['state_semantics']['variables'].get('relationship.trust')
            if entry is not None:
                for key in ('increase_evidence', 'decrease_evidence', 'non_evidence', 'rationale_requirement'):
                    self.assertEqual(entry[key], policy[key])
                restored['state_semantics']['variables']['relationship.trust'] = deepcopy(item['payload']['state_semantics']['variables']['relationship.trust'])
            self.assertEqual(restored, item['payload'])
            self.assertEqual(now['request']['generation'], item['request']['generation'])

    def test_schema_prompt_and_validator_share_enum_registry(self):
        schema = interaction_wire_schema()
        event = schema['properties']['appraisal']['properties']['ledger_events']['items']
        registry = semantic_ledger_wire_contract()
        self.assertEqual(event['properties']['assertion_mode']['enum'], registry['assertion_modes'])
        self.assertEqual(event['properties']['action_owner']['enum'], registry['action_owners'])
        bad = {'event_type': 'claim', 'owner': 'evaluated_agent', 'action_owner': 'A person name',
               'evidence_span': 'Test claim', 'status': 'reported', 'assertion_mode': 'asserted'}
        with self.assertRaisesRegex(ValueError, 'allowed=.*evaluated_agent'):
            validate_wire(bad, event)
        with self.assertRaisesRegex(ValueError, 'use role IDs, not names'):
            validate_semantic_ledger_events([bad], 'Test claim', 'evaluated_agent', require_assertion_mode=True)
        bad['action_owner'] = 'evaluated_agent'; bad['assertion_mode'] = 'speaker_report'
        with self.assertRaisesRegex(ValueError, 'allowed=.*asserted'):
            validate_wire(bad, event)

    def test_event_status_pairs_not_just_union(self):
        with self.assertRaisesRegex(ValueError, 'allowed for claim'):
            validate_event_pairs([{'event_type': 'claim', 'status': 'firm'}])

    def test_malformed_impact_domain_is_not_silently_dropped(self):
        schema = interaction_wire_schema()
        claim = schema['properties']['appraisal']['properties']['dialogue_diagnostics']['properties']['consequential_claims']['items']
        with self.assertRaisesRegex(ValueError, 'impact_domains.*allowed='):
            validate_wire({'claim_span': 'a fact', 'impact_domains': ['自由写的领域'], 'grounding': 'speaker_report'}, claim)

    def test_actual_interaction_request_contains_schema_and_names_separately(self):
        item = self.saved[12]
        scenario = v.load(v.ROOT / item['case']['scenario'])
        with patch.object(v, 'PROMPT', BASE_PROMPT):
            prepared = v.prepare_case(item['case'], self.env)
        capture = v.Capture()
        with self.assertRaises(v.Captured):
            SchemaBoundInteractionAppraiser(scenario, capture).appraise(**prepared['kwargs'])
        payload = json.loads(capture.request['messages'][1]['content'].split('## Input\n', 1)[1])
        self.assertIn('output_schema', payload)
        self.assertEqual(payload['actor_identities']['evaluated_agent']['name'], 'Sera Dastan')
        self.assertEqual(payload['previous_state'], prepared['kwargs']['previous_state'])
        self.assertEqual(payload['state_semantics']['variables']['relationship.trust']['increase_evidence'], trust_policy()['increase_evidence'])

    def test_bounded_schema_repair_uses_precise_field_and_enum_feedback(self):
        item = self.saved[12]
        with patch.object(v, 'PROMPT', BASE_PROMPT):
            prepared = v.prepare_case(item['case'], self.env)
        source = prepared['kwargs']['action']['text']
        good = {'appraisal': {'speaker_intent': 'Sera Dastan confirms a time.', 'social_act': 'inform',
                'ledger_events': [{'event_type': 'claim', 'owner': 'evaluated_agent', 'action_owner': 'evaluated_agent',
                                  'evidence_span': source, 'status': 'reported', 'assertion_mode': 'asserted'}],
                'ledger_resolutions': [], 'dialogue_diagnostics': {
                    'substantive_novelty': {'label': 'necessary_confirmation', 'evidence_span': source},
                    'consequential_claims': [], 'continuation': {'status': 'can_close', 'evidence_span': '',
                    'after_direct_response': {'status': 'can_close', 'evidence_span': ''}}}}, 'evidence_turn_ids': []}
        bad = deepcopy(good); bad['appraisal']['ledger_events'][0]['assertion_mode'] = 'long_descriptive_enum'
        class Sequence:
            def __init__(self):
                self.messages = []
            def complete(self, messages, **generation):
                self.messages.append(deepcopy(messages))
                return json.dumps(bad if len(self.messages) == 1 else good)
        provider = Sequence()
        result = SchemaBoundInteractionAppraiser(prepared['scenario'], provider).appraise(**prepared['kwargs'])
        self.assertEqual(len(provider.messages), 2)
        feedback = provider.messages[1][-1]['content']
        self.assertIn('$.appraisal.ledger_events[0].assertion_mode', feedback)
        self.assertIn('allowed=', feedback)
        self.assertEqual(len(result['request_retry_diagnostics']), 1)

    def test_real_environment_uses_both_new_components_without_extra_state_update(self):
        scenario = v.load(v.ROOT / self.saved[12]['case']['scenario'])
        environment = UnifiedEnvironmentFactory(build_environment_factory(scenario, self.env))()
        self.assertIsInstance(environment.state_updater.state_appraiser, UnifiedStateAppraiser)
        self.assertIsInstance(environment.state_updater.interaction_appraiser, SchemaBoundInteractionAppraiser)
        self.assertEqual(environment.state_updater.calibrator.profile, self.env['state_calibration_profile'])
        self.assertEqual(environment.provenance['llm_calls_per_step'], 3)


if __name__ == '__main__':
    unittest.main()
