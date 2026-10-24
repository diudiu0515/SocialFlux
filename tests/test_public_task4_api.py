"""Wire-contract tests: synthetic engineering fixtures, no datasets or model calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from jsonschema import Draft202012Validator, ValidationError

from environment.observation import build_policy_observation
from scripts.serve_qwen_task4 import Handler, Task4Server
from environment.qwen_task4 import digest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schemas/task4_session.schema.json').read_text())
PRIVATE = 'author-only-test-sentinel'


class StubEnvironment:
    """Exercise the real session/HTTP/public projection with a model-free transition."""
    provenance = {'private_audit_marker': PRIVATE}

    def __init__(self, scenario):
        self.scenario = scenario
        self.calls = 0
        self.end_reason = None

    def reset(self, episode_id=None):
        self.session = {'turn_id': 0, 'status': 'active', 'ending': None,
                        'history': [], 'state': {'private': PRIVATE}, 'dynamics': {}}

    def observe(self):
        return build_policy_observation(self.scenario, self.session)

    def private_trajectory(self):
        return deepcopy(self.session)

    def step(self, action):
        self.calls += 1
        if action['text'] == 'fail':
            raise RuntimeError(PRIVATE)
        self.session['turn_id'] += 1
        self.session['current_response'] = 'A public response.'
        self.session['history'].append({'role': 'evaluated_agent', 'text': action['text']})
        if self.end_reason:
            self.session['ending'] = {'reason': self.end_reason}
            self.session['status'] = 'ended'


class PublicTask4APITests(unittest.TestCase):
    def setUp(self):
        Draft202012Validator.check_schema(SCHEMA)
        self.validator = Draft202012Validator(SCHEMA)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        scenario = {'scenario_id': 'synthetic-wire-fixture', 'policy_background': 'Two test actors speak.',
                    'environment_agent': {'hidden_intention': PRIVATE,
                                          'persona': {'name': 'Actor', 'role': 'colleague', 'temperament': PRIVATE}},
                    'evaluated_agent_role': {'name': 'Participant', 'role': 'colleague',
                                             'explicit_goal': 'Ask a question.', 'hidden_intention': PRIVATE}}
        source = root / 'scenario.json'
        source.write_text(json.dumps(scenario))
        catalog = root / 'catalog.json'
        catalog.write_text(json.dumps({'scenarios': {scenario['scenario_id']: {
            'path': str(source), 'sha256': digest(source)}}}))
        config = {'profile': 'test-only', 'model': 'stub',
                  'environment': {'provider': {'endpoint': 'http://127.0.0.1:9/v1/chat/completions'}}}
        for target, kwargs in [
            ('scripts.serve_qwen_task4.load_config', {'return_value': config}),
            ('scripts.serve_qwen_task4.QwenTask4EnvironmentFactory',
             {'side_effect': lambda scenario, _: lambda: StubEnvironment(scenario)}),
            ('environment.qwen_task4_session.request_providers', {'return_value': {}}),
        ]:
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        quiet = patch.object(Handler, 'log_message')
        quiet.start()
        self.addCleanup(quiet.stop)
        self.server = Task4Server(0, root / 'config.json', catalog, root / 'episodes')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.opener = build_opener(ProxyHandler({}))

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, value=None):
        data = json.dumps(value).encode() if value is not None else None
        request = Request(self.base + path, data=data, method=method,
                          headers={'Content-Type': 'application/json'})
        try:
            response = self.opener.open(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def create(self):
        code, body = self.request('POST', '/sessions', {'scenario_id': 'synthetic-wire-fixture'})
        self.assertEqual(code, 201)
        self.validator.validate(body)
        self.assertNotIn(PRIVATE, json.dumps(body))
        return body, self.server.sessions[body['episode_id']]

    def test_public_lifecycle_and_stale_turn_do_not_double_step(self):
        code, catalog = self.request('GET', '/scenarios')
        self.assertEqual((code, catalog), (200, {'scenario_ids': ['synthetic-wire-fixture']}))
        initial, session = self.create()
        path = '/sessions/' + initial['episode_id']
        code, result = self.request('POST', path + '/step', {'text': 'Hello', 'expected_turn_id': 0})
        self.assertEqual(code, 200)
        self.validator.validate(result)
        self.assertEqual(result['observation']['turn_id'], 1)
        self.assertNotIn(PRIVATE, json.dumps(result))
        code, error = self.request('POST', path + '/step', {'text': 'Hello', 'expected_turn_id': 0})
        self.assertEqual((code, error['error']), (409, 'episode_inactive_or_stale_turn'))
        self.assertEqual(session.environment.calls, 1)
        self.assertEqual(self.request('GET', path), (200, result))
        self.assertEqual(self.request('DELETE', path), (200, {'closed': True}))
        self.assertTrue((session.output / 'trajectory.json').exists())
        self.assertTrue((session.output / 'client_closed.json').exists())
        self.assertEqual(self.request('GET', path)[0], 404)

    def test_failure_is_distinct_and_private_evidence_is_retained(self):
        initial, session = self.create()
        path = '/sessions/' + initial['episode_id'] + '/step'
        code, failed = self.request('POST', path, {'text': 'fail', 'expected_turn_id': 0})
        self.assertEqual(code, 502)
        self.validator.validate(failed)
        self.assertTrue(failed['failed'])
        self.assertFalse(failed['terminated'] or failed['truncated'])
        self.assertIsNone(failed['reward'])
        self.assertNotIn(PRIVATE, json.dumps(failed))
        self.assertIn(PRIVATE, (session.output / 'failure.json').read_text())
        self.assertEqual(self.request('POST', path, {'text': 'retry', 'expected_turn_id': 0})[0], 409)
        self.assertEqual(session.environment.calls, 1)

    def test_invalid_requests_and_busy_server_do_not_call_environment(self):
        initial, session = self.create()
        path = '/sessions/' + initial['episode_id'] + '/step'
        for body in ({'text': ' ', 'expected_turn_id': 0},
                     {'text': 'Hi', 'expected_turn_id': True},
                     {'text': 'Hi', 'expected_turn_id': 0, 'state': {}},
                     {'text': 'Hi'}, []):
            with self.subTest(body=body):
                self.assertEqual(self.request('POST', path, body)[0], 400)
        self.server.generation_slot.acquire()
        try:
            self.assertEqual(self.request('POST', path, {'text': 'Hi', 'expected_turn_id': 0}),
                             (503, {'error': 'generation_busy'}))
        finally:
            self.server.generation_slot.release()
        self.assertEqual(session.environment.calls, 0)

    def test_natural_completion_and_budget_truncation_have_different_flags(self):
        for reason, flags in [('natural_completion', (True, False)), ('max_turns', (False, True))]:
            with self.subTest(reason=reason):
                initial, session = self.create()
                session.environment.end_reason = reason
                code, result = self.request('POST', '/sessions/' + initial['episode_id'] + '/step',
                                            {'text': 'Finish', 'expected_turn_id': 0})
                self.assertEqual(code, 200)
                self.validator.validate(result)
                self.assertEqual((result['terminated'], result['truncated']), flags)

    def test_schema_rejects_private_fields_and_fabricated_reward(self):
        initial, _ = self.create()
        for container, key, value in [('observation', 'state', {}),
                                      ('observation', 'hidden_intention', PRIVATE),
                                      ('target_character', 'persona', {}),
                                      ('role', 'hidden_intention', PRIVATE),
                                      ('session', 'reward', 0), ('session', 'private_trajectory', {})]:
            changed = deepcopy(initial)
            target = changed if container == 'session' else changed['observation']
            if container in ('target_character', 'role'):
                target = target[container]
            target[key] = value
            with self.subTest(container=container, key=key), self.assertRaises(ValidationError):
                self.validator.validate(changed)


if __name__ == '__main__':
    unittest.main()
