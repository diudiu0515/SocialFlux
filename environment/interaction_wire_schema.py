"""One machine-readable interaction schema used in requests and validation."""
from .appraisal import SOCIAL_ACTS, NOVELTY_LABELS, CLAIM_IMPACT_DOMAINS, CLAIM_GROUNDING, CONTINUATION_STATUS
from .ledger_events import semantic_ledger_wire_contract


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def text(enum=None, nonempty=False):
    return {'type': 'string', **({'enum': sorted(enum)} if enum is not None else {}), **({'minLength': 1} if nonempty else {})}


def array(items, maximum=None, minimum=None, unique=False):
    return {'type': 'array', 'items': items, **({'maxItems': maximum} if maximum is not None else {}),
            **({'minItems': minimum} if minimum is not None else {}), **({'uniqueItems': True} if unique else {})}


def interaction_wire_schema(active_proposals=(), evidence_turn_ids=()):
    ledger = semantic_ledger_wire_contract()
    statuses = {status for values in ledger['event_status_pairs'].values() for status in values}
    event = obj({'event_type': text(ledger['event_status_pairs']), 'owner': text(['evaluated_agent']),
                 'action_owner': text(ledger['action_owners']), 'evidence_span': text(nonempty=True),
                 'status': text(statuses), 'assertion_mode': text(ledger['assertion_modes'])})
    assert set(event['required']) == set(ledger['required_fields'])
    ids = [p['id'] for p in active_proposals if p.get('speaker') != 'evaluated_agent' and p.get('status') in {'open', 'tentative'}]
    return obj({'appraisal': obj({
        'speaker_intent': text(nonempty=True), 'social_act': text(SOCIAL_ACTS),
        'ledger_events': array(event),
        'ledger_resolutions': array(obj({'target_id': text(ids), 'resolution': text(['accepted', 'rejected', 'countered']), 'evidence_span': text(nonempty=True)}), maximum=3),
        'dialogue_diagnostics': obj({
            'substantive_novelty': obj({'label': text(NOVELTY_LABELS), 'evidence_span': text()}),
            'consequential_claims': array(obj({'claim_span': text(nonempty=True), 'impact_domains': array(text(CLAIM_IMPACT_DOMAINS), minimum=1, unique=True), 'grounding': text(CLAIM_GROUNDING)}), maximum=3),
            'continuation': obj({'status': text(CONTINUATION_STATUS), 'evidence_span': text(),
                                 'after_direct_response': obj({'status': text(['continue', 'can_close']), 'evidence_span': text()})})})}),
        'evidence_turn_ids': array(text(evidence_turn_ids), maximum=4, unique=True)})


def validate_wire(value, schema, path='$'):
    """Validate the deliberately small JSON-Schema subset emitted above."""
    kind = schema['type']
    expected = {'object': dict, 'array': list, 'string': str}[kind]
    if not isinstance(value, expected):
        raise ValueError(f'{path}: expected {kind}')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f"{path}: invalid {value!r}; allowed={schema['enum']!r}")
    if kind == 'object':
        if set(value) != set(schema['required']):
            raise ValueError(f"{path}: keys must be exactly {schema['required']!r}")
        for key, child in schema['properties'].items():
            validate_wire(value[key], child, path + '.' + key)
    elif kind == 'array':
        if len(value) > schema.get('maxItems', len(value)) or len(value) < schema.get('minItems', 0):
            raise ValueError(f'{path}: invalid number of items')
        if schema.get('uniqueItems') and any(item in value[:i] for i, item in enumerate(value)):
            raise ValueError(f'{path}: duplicate items')
        for i, item in enumerate(value):
            validate_wire(item, schema['items'], f'{path}[{i}]')
    elif len(value.strip()) < schema.get('minLength', 0):
        raise ValueError(f'{path}: must be nonempty')


def validate_event_pairs(events):
    pairs = semantic_ledger_wire_contract()['event_status_pairs']
    for i, event in enumerate(events):
        if event['status'] not in pairs[event['event_type']]:
            raise ValueError(f"$.appraisal.ledger_events[{i}].status: allowed for {event['event_type']}={pairs[event['event_type']]}")
