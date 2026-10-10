"""Opt-in actor binding over the unchanged v6 appraisal and v7 calibrator.

An isolated adapter allows frozen older runs to finish without editing their
prompt registry, factory, definitions, or request construction.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .independent_appraisal import ModelStateAppraiser

PROFILE = 'state_actor_binding_v1'
BASE_PROMPT = 'environment_state_appraisal_v6_observed_evidence'
RULES = Path(__file__).resolve().parents[1] / 'prompts/state_actor_binding_v1.txt'

RELATIONSHIP_DEFINITIONS = {
    'trust': '{owner} believes {target} is reliable and will act as represented.',
    'hostility': "{owner}'s adversarial orientation toward {target}.",
    'respect': "{owner}'s regard for {target}'s standing, agency, competence, or dignity.",
    'perceived_safety': '{owner} believes engagement with {target} is interpersonally safe.',
    'affiliation': "{owner}'s felt relational closeness, solidarity, or sense of being on the same side with {target}.",
    'perceived_fairness': '{owner} believes treatment, process, and burden allocation in dealings with {target} are fair.',
    'perceived_responsiveness': "{owner} believes {target} is hearing and substantively addressing {owner}'s concerns.",
    'role_legitimacy': '{owner} believes {target} is exercising their role, authority, or mandate appropriately.',
}


def binding_context(scenario):
    persona = scenario['environment_agent']['persona']
    evaluated = scenario.get('evaluated_agent_role', {})
    target_persona = evaluated.get('persona', {})
    owner = {'role_id': 'environment_agent', 'name': persona.get('name'), 'role': persona.get('role')}
    target = {'role_id': 'evaluated_agent', 'name': evaluated.get('name') or target_persona.get('name'),
              'role': evaluated.get('role') or target_persona.get('role')}
    for person in (owner, target):
        if not all(isinstance(person[key], str) and person[key].strip() for key in ('name', 'role')):
            raise ValueError('Actor binding requires concrete names and roles for both people')
    return {'profile': PROFILE, 'state_owner': owner, 'relationship_target': target,
            'latest_action_speaker': deepcopy(target)}


def bind_messages(messages, scenario):
    """Return actual wire messages; preserve history/action/evidence criteria."""
    result = deepcopy(messages)
    if len(result) < 2 or result[1]['role'] != 'user':
        raise ValueError('Expected the independent state appraisal input message')
    prefix, separator, encoded = result[1]['content'].partition('## Input\n')
    if not separator:
        raise ValueError('Missing state input boundary')
    payload = json.loads(encoded)
    semantics = payload['state_semantics']
    if 'actor_binding' in semantics:
        raise ValueError('Actor binding must be applied exactly once')
    binding = binding_context(scenario)
    owner, target = binding['state_owner']['name'], binding['relationship_target']['name']
    semantics['actor_binding'] = binding
    state_paths = set(payload['state_variable_paths'])
    for path, entry in semantics['variables'].items():
        canonical = entry['definition']
        perspective = {'state_owner': deepcopy(binding['state_owner']), 'relationship_target': None}
        if path.startswith('relationship.'):
            key = path.split('.', 1)[1]
            if key not in RELATIONSHIP_DEFINITIONS:
                raise ValueError('Missing actor-bound relationship definition: ' + path)
            entry['definition'] = RELATIONSHIP_DEFINITIONS[key].format(owner=owner, target=target)
            perspective['relationship_target'] = deepcopy(binding['relationship_target'])
        else:
            concrete = canonical.replace("the character's", owner + "'s").replace("the environment character's", owner + "'s")
            entry['definition'] = f"{owner}'s {'state' if path in state_paths else 'interaction context'}: {concrete}"
        entry['perspective'] = perspective
    rules = RULES.read_text()
    result[0]['content'] += (f"\nState owner: {owner} ({binding['state_owner']['role']}). "
                              f"Relationship target and latest-action speaker: {target} ({binding['relationship_target']['role']}). "
                              'Do not reverse who evaluates whom.')
    result[1]['content'] = prefix + '\n## ' + rules + '\n## Input\n' + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return result


class _ActorBindingProvider:
    def __init__(self, provider, scenario):
        self.provider, self.scenario = provider, deepcopy(scenario)
        self.actual_requests = []

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def complete(self, messages, **generation):
        bound = bind_messages(messages, self.scenario)
        self.actual_requests.append({'messages': deepcopy(bound), 'generation': deepcopy(generation)})
        return self.provider.complete(bound, **generation)


class ActorBoundStateAppraiser(ModelStateAppraiser):
    def __init__(self, scenario, provider, sampling=None, *, prompt_id=BASE_PROMPT):
        if prompt_id != BASE_PROMPT:
            raise ValueError('This candidate only binds the frozen observed-evidence v6 prompt')
        binding_context(scenario)
        super().__init__(scenario, _ActorBindingProvider(provider, scenario), sampling, prompt_id=prompt_id)

    @property
    def provenance(self):
        return {**super().provenance, 'actor_binding_profile': PROFILE,
                'actor_binding_rules_sha256': hashlib.sha256(RULES.read_bytes()).hexdigest()}

    def appraise(self, **kwargs):
        first = len(self.provider.actual_requests)
        result = super().appraise(**kwargs)
        actual = self.provider.actual_requests[first:]
        result['request_messages'] = deepcopy(actual[0]['messages'])
        result['actor_binding_requests'] = deepcopy(actual)
        result['actor_binding'] = binding_context(self.scenario)
        # Name presence is only a review aid, never a semantic pass or update gate.
        owner = result['actor_binding']['state_owner']['name']
        target = result['actor_binding']['relationship_target']['name']
        result['perspective_review'] = [
            {'variable': item['variable'], 'rationale': item['rationale'],
             'owner_name_present': owner in item['rationale'],
             'target_name_present': target in item['rationale'] if item['variable'].startswith('relationship.') else None,
             'semantic_orientation_status': 'requires_review'}
            for item in result['state_judgments'] + result['dynamics_judgments']]
        return result


class ActorBoundEnvironmentFactory:
    """Explicit rollout integration; never changes a baseline factory instance."""
    def __init__(self, base_factory):
        if not base_factory.independent_appraisals or base_factory.state_appraisal_prompt_id != BASE_PROMPT:
            raise ValueError('Actor-bound candidate requires the independent v6 base factory')
        self.base_factory = base_factory

    @property
    def provenance(self):
        return {**self.base_factory.provenance, 'actor_binding_profile': PROFILE,
                'actor_binding_rules_sha256': hashlib.sha256(RULES.read_bytes()).hexdigest()}

    def __call__(self):
        environment = self.base_factory()
        updater = environment.state_updater
        original = updater.state_appraiser
        updater.state_appraiser = ActorBoundStateAppraiser(original.scenario, original.provider,
                                                           original.sampling, prompt_id=original.prompt_id)
        updater.provider = updater.state_appraiser.provider
        environment.provenance = self.provenance
        return environment
