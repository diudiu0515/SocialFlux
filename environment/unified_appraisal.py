"""User-approved current trust evidence plus schema-bound interaction appraisal."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from providers.structured import complete_json
from .actor_bound_appraisal import ActorBoundStateAppraiser, ActorBoundEnvironmentFactory, BASE_PROMPT, bind_messages, binding_context
from .independent_appraisal import ModelStateAppraiser, ModelInteractionAppraiser, _base_messages, _provider_audit_records, _validate_evidence_ids
from .appraisal import _validate_ledger_resolutions, _validate_dialogue_diagnostics, appraisal_preserves_action_owner, _exact_span_or_empty
from .ledger_events import validate_semantic_ledger_events, semantic_ledger_wire_contract
from .interaction_wire_schema import interaction_wire_schema, validate_wire, validate_event_pairs
from .calibration import immediate_update_contract

ROOT = Path(__file__).resolve().parents[1]
TRUST_POLICY = ROOT / 'configs/state_trust_current_evidence_v1.json'
INTERACTION_RULES = ROOT / 'prompts/interaction_schema_bound_v1.txt'
PROFILE = 'unified_current_trust_schema_v1'


def trust_policy():
    return json.loads(TRUST_POLICY.read_text())


def align_trust_payload(payload, scenario):
    result = deepcopy(payload)
    semantics = result['state_semantics']
    policy = trust_policy()
    actors = binding_context(scenario)
    entry = semantics['variables'].get('relationship.trust')
    if entry is not None:
        entry['definition'] = policy['definition_template'].format(owner=actors['state_owner']['name'], target=actors['relationship_target']['name'])
        for key in ('increase_evidence', 'decrease_evidence', 'non_evidence', 'rationale_requirement'):
            entry[key] = policy[key]
        entry['evidence_policy_profile'] = policy['profile']
    semantics['update_policy'] = immediate_update_contract()
    for item in semantics['variables'].values():
        item['update_rule'] = 'Use state_semantics.update_policy; timescale does not gate an update.'
    return result


class _UnifiedStateProvider:
    def __init__(self, provider, scenario):
        self.provider, self.scenario = provider, deepcopy(scenario)
        self.actual_requests = []

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def complete(self, messages, **generation):
        bound = bind_messages(messages, self.scenario)
        prefix, _, encoded = bound[1]['content'].partition('## Input\n')
        payload = align_trust_payload(json.loads(encoded), self.scenario)
        bound[1]['content'] = prefix + '## Input\n' + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        self.actual_requests.append({'messages': deepcopy(bound), 'generation': deepcopy(generation)})
        return self.provider.complete(bound, **generation)


class UnifiedStateAppraiser(ActorBoundStateAppraiser):
    def __init__(self, scenario, provider, sampling=None, *, prompt_id=BASE_PROMPT):
        if prompt_id != BASE_PROMPT:
            raise ValueError('Unified candidate requires the frozen independent v6 base')
        binding_context(scenario)
        ModelStateAppraiser.__init__(self, scenario, _UnifiedStateProvider(provider, scenario), sampling, prompt_id=prompt_id)

    @property
    def provenance(self):
        return {**super().provenance, 'unified_profile': PROFILE,
                'trust_policy_sha256': hashlib.sha256(TRUST_POLICY.read_bytes()).hexdigest()}


class SchemaBoundInteractionAppraiser(ModelInteractionAppraiser):
    @property
    def provenance(self):
        return {**super().provenance, 'wire_schema_profile': 'interaction_wire_schema_v1',
                'wire_rules_sha256': hashlib.sha256(INTERACTION_RULES.read_bytes()).hexdigest()}

    def appraise(self, *, action, previous_state, previous_dynamics, memory,
                 longitudinal_context=None, interaction_ledger=None, appraisal_context=None):
        actors = binding_context(self.scenario)
        messages = _base_messages(self.scenario, self.prompt_id, action=action,
            previous_state=previous_state, previous_dynamics=previous_dynamics, memory=memory,
            longitudinal_context=longitudinal_context, interaction_ledger=interaction_ledger,
            appraisal_context=appraisal_context,
            system_prompt='You are the private interaction appraiser. The latest action speaker is evaluated_agent: '
                          + actors['latest_action_speaker']['name'] + '. Analyze that speaker\'s action, not the environment character\'s response. Return schema-conforming JSON only.')
        payload = align_trust_payload(json.loads(messages[1]['content'].split('## Input\n', 1)[1]), self.scenario)
        active = (interaction_ledger or {}).get('active_proposals', [])
        evidence_ids = memory.get('relevant_turn_ids', [])
        schema = interaction_wire_schema(active, evidence_ids)
        payload['output_schema'] = schema
        payload['event_status_pairs'] = semantic_ledger_wire_contract()['event_status_pairs']
        payload['actor_identities'] = {'evaluated_agent': actors['relationship_target'], 'environment_agent': actors['state_owner'],
                                       'collective': 'Jointly owned act; not a person name', 'unspecified': 'Actor not established or not one of the two participants'}
        messages[1]['content'] = INTERACTION_RULES.read_text() + '\n## Input\n' + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        audit_start = len(_provider_audit_records(self.provider))
        diagnostics = []

        def validate(result):
            validate_wire(result, schema)
            value = result['appraisal']
            validate_event_pairs(value['ledger_events'])
            if not appraisal_preserves_action_owner(value, self.scenario['environment_agent']['persona']):
                raise ValueError('speaker_intent assigned the latest action to environment_agent instead of evaluated_agent')
            normalizations = []
            value['ledger_events'] = validate_semantic_ledger_events(value['ledger_events'], action['text'].strip(),
                'evaluated_agent', drop_irrelevant=True, normalize_tentative_commitments=True,
                normalize_pending_commitments=True, drop_acceptance_commitments=True, drop_acceptance_events=True,
                active_proposals=active, normalization_log=normalizations, require_assertion_mode=True)
            _validate_ledger_resolutions(value['ledger_resolutions'], action['text'].strip(), active)
            for claim in value['dialogue_diagnostics']['consequential_claims']:
                claim['claim_span'] = _exact_span_or_empty(claim['claim_span'], action['text'].strip(), 'consequential claim')
            _validate_dialogue_diagnostics(value['dialogue_diagnostics'], action['text'].strip(),
                require_after_direct_response=True, live_questions=(longitudinal_context or {}).get('segment', {}).get('live_questions', []))
            if normalizations:
                value['ledger_event_normalizations'] = normalizations
            return {'appraisal': value, 'evidence_turn_ids': _validate_evidence_ids(result['evidence_turn_ids'], evidence_ids)}

        result = complete_json(self.provider, messages, self.sampling, validate, context='schema-bound interaction appraiser',
            diagnostics_sink=diagnostics, repair_unescaped_interior_quotes=True,
            retry_guidance='Use the supplied output_schema enum values and role IDs literally; person names belong only in speaker_intent or quoted evidence, not enum fields.')
        result.update(request_messages=messages, request_sampling=dict(self.sampling),
                      provider_audit_records=_provider_audit_records(self.provider)[audit_start:],
                      request_retry_diagnostics=diagnostics)
        return result


class UnifiedEnvironmentFactory(ActorBoundEnvironmentFactory):
    @property
    def provenance(self):
        return {**super().provenance, 'unified_profile': PROFILE,
                'trust_policy_sha256': hashlib.sha256(TRUST_POLICY.read_bytes()).hexdigest(),
                'interaction_wire_schema_profile': 'interaction_wire_schema_v1',
                'interaction_wire_rules_sha256': hashlib.sha256(INTERACTION_RULES.read_bytes()).hexdigest()}

    def __call__(self):
        environment = self.base_factory()
        updater = environment.state_updater
        state, interaction = updater.state_appraiser, updater.interaction_appraiser
        updater.state_appraiser = UnifiedStateAppraiser(state.scenario, state.provider, state.sampling, prompt_id=state.prompt_id)
        updater.interaction_appraiser = SchemaBoundInteractionAppraiser(interaction.scenario, interaction.provider,
                                                                       interaction.sampling, prompt_id=interaction.prompt_id)
        updater.provider = updater.state_appraiser.provider
        environment.provenance = self.provenance
        return environment
