"""Protect evidence scope and paid-task resumability without network calls."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch, Mock

import tempfile
import unittest

from scripts import seedance_state_batch as batch


def fixture_inputs():
    items = [json.loads(s) for s in batch.BANK.read_text().splitlines() if s.strip()]
    by_id = {i['instance_id']: i for i in items}
    nodes = batch.public_nodes(items)
    requests = {n['node_id']: batch.load(n['request_path']) for n in batch.load(batch.BASELINE)['nodes']}
    return by_id, nodes, requests


def test_current_state_scope_never_contains_future_or_answers():
    by_id, nodes, requests = fixture_inputs()
    for node in nodes:
        inputs, evidence = batch.inputs_for(node, requests[node['node_id']], by_id)
        serialized = json.dumps(inputs)
        assert not any(k in inputs for k in ('ground_truth', 'question', 'options', 'oracle_reference'))
        if node['location'] == 'ending':
            assert inputs['mode'] == 'shared_public_ending'
            assert 'state_after' not in serialized
            assert 'history_a' not in serialized and 'history_b' not in serialized
        else:
            assert inputs['public_prefix'][-1]['turn_id'] == node['location']
            assert all(int(t['turn_id'][1:]) <= int(node['location'][1:]) for t in inputs['public_prefix'])
            assert evidence['state_sha256']


def test_shared_ending_independent_of_branch_state_and_answers():
    by_id, nodes, requests = fixture_inputs()
    node = next(n for n in nodes if n['location'] == 'ending')
    before, _ = batch.inputs_for(node, requests[node['node_id']], by_id)
    changed = deepcopy(by_id)
    for binding in node['bindings']:
        item = changed[binding['instance_id']]
        item['ground_truth'] = {'answer': 'FORBIDDEN_ANSWER'}
        item['input']['history_a'][-1]['evaluated_agent'] = 'FORBIDDEN_BRANCH'
        item['authoring']['oracle_reference'] = {'state_after': 'FORBIDDEN_STATE'}
    after, _ = batch.inputs_for(node, requests[node['node_id']], changed)
    assert before == after


def test_ambiguous_paid_submission_never_resubmitted(tmp_path):
    directory = tmp_path / 'node'
    directory.mkdir()
    batch.save(directory / 'provider-state.json', {'status': 'submitting'})
    with patch.object(batch, 'ROOT', tmp_path), patch.object(batch, 'SeedanceClient') as client:
        with unittest.TestCase().assertRaisesRegex(ValueError, 'never auto-resubmit'):
            batch.generate({'directory': 'node'}, {}, submit_new=True)
        client.assert_not_called()


def test_downloaded_video_verified_before_reuse(tmp_path):
    directory = tmp_path / 'node'
    directory.mkdir()
    (directory / 'native.mp4').write_bytes(b'changed')
    batch.save(directory / 'provider-state.json', {'status': 'downloaded', 'video_sha256': 'wrong'})
    with patch.object(batch, 'ROOT', tmp_path), patch.object(batch, 'SeedanceClient') as client:
        with unittest.TestCase().assertRaisesRegex(ValueError, 'integrity'):
            batch.generate({'directory': 'node'}, {}, submit_new=True)
        client.assert_not_called()


def test_existing_task_resumes_without_a_new_post(tmp_path):
    directory = tmp_path / 'node'
    directory.mkdir()
    key = tmp_path / 'test-key'
    key.write_text('dummy-test-only')
    batch.save(tmp_path / 'configs/gpt50_experiment/video_completion.active.json', {'key_file': str(key)})
    batch.save(directory / 'provider-state.json', {'status': 'running', 'task_id': 'existing-task'})
    client = Mock()
    client.query.return_value = {'status': 'failed'}
    with patch.object(batch, 'ROOT', tmp_path), patch.object(batch, 'SeedanceClient', return_value=client):
        with unittest.TestCase().assertRaisesRegex(ValueError, 'terminal status'):
            batch.generate({'directory': 'node'}, {}, submit_new=True)
    client.submit.assert_not_called()
    client.query.assert_called_once_with('existing-task')


def test_native_video_only_reference_binds_provider_setting_and_file_hash(tmp_path):
    directory = tmp_path / 'reference'
    directory.mkdir()
    (directory / 'native.mp4').write_bytes(b'original-provider-video')
    digest = batch.sha(directory / 'native.mp4')
    state = dict(status='downloaded', request=dict(generate_audio=False), video_sha256=digest)
    receipt = dict(version='provider_native_video_only_v1', audio_stream_count=0,
                   provider_generate_audio=False, source_native_sha256=digest)
    batch.save(directory / 'provider-state.json', state)
    batch.save(directory / 'reference-screen.json', receipt)
    assert batch.native_video_only_reference(directory)
    state['request']['generate_audio'] = True
    batch.save(directory / 'provider-state.json', state)
    assert not batch.native_video_only_reference(directory)
    state['request']['generate_audio'] = False
    batch.save(directory / 'provider-state.json', state)
    (directory / 'native.mp4').write_bytes(b'changed-reference')
    assert not batch.native_video_only_reference(directory)


def test_render_includes_exact_line_once_and_reference_voice():
    direction = {k: k + ' prose' for k in ('cast', 'situation', 'psychology', 'objective', 'voice', 'avoid')}
    direction['beats'] = ['listen', 'speak', 'think', 'finish']
    line = 'Is placement confirmed?'
    prompt = batch.render_prompt(direction, line, True)
    assert prompt.count(line) == 1
    assert 'five-second' in prompt
    assert 'voice timbre' in prompt
    assert 'Do not replay its words' in prompt


def test_identity_frame_requires_original_provider_output(tmp_path):
    (tmp_path / 'native.mp4').write_bytes(b'provider-video')
    frame = tmp_path / 'native-last-frame.jpg'
    frame.write_bytes(b'provider-frame')
    state = dict(status='downloaded', video_sha256=batch.sha(tmp_path / 'native.mp4'),
        request=dict(return_last_frame=True),
        latest_query_response=dict(content=dict(last_frame_url='https://example.invalid/original.jpg')))
    batch.save(tmp_path / 'provider-state.json', state)
    batch.save(tmp_path / 'frame-receipt.json', dict(version='provider_native_last_frame_v1',
        source_native_sha256=state['video_sha256'], frame_sha256=batch.sha(frame), provider_return_last_frame=True))
    assert batch.native_frame_reference(tmp_path) == 'https://example.invalid/original.jpg'
    frame.write_bytes(b'changed-or-extracted-frame')
    with unittest.TestCase().assertRaisesRegex(ValueError, 'provenance or integrity'):
        batch.native_frame_reference(tmp_path)


def test_still_reference_generation_sends_no_video_motion(tmp_path):
    node, reference = tmp_path / 'node', tmp_path / 'reference'
    node.mkdir(); reference.mkdir()
    (reference / 'native.mp4').write_bytes(b'provider-video')
    (reference / 'native-last-frame.jpg').write_bytes(b'provider-frame')
    batch.save(reference / 'provider-state.json', dict(status='downloaded',
        video_sha256=batch.sha(reference / 'native.mp4'), request=dict(return_last_frame=True),
        latest_query_response=dict(content=dict(last_frame_url='https://example.invalid/original.jpg'))))
    batch.save(reference / 'frame-receipt.json', dict(version='provider_native_last_frame_v1',
        source_native_sha256=batch.sha(reference / 'native.mp4'),
        frame_sha256=batch.sha(reference / 'native-last-frame.jpg'), provider_return_last_frame=True))
    (node / 'prompt.en.txt').write_text('Act from the current direction.')
    batch.save(node / 'prompt-audit.json', dict(prompt_sha256=batch.sha(node / 'prompt.en.txt')))
    batch.save(node / 'request.json', dict(reference_video_file='obsolete-reference.mp4'))
    key = tmp_path / 'test-key'; key.write_text('dummy-test-only')
    batch.save(tmp_path / 'configs/gpt50_experiment/video_completion.active.json',
        dict(key_file=str(key), model='doubao-seedance-2-0-260128'))
    client = Mock(); client.submit.return_value = dict(id='one-new-task'); client.query.return_value = dict(status='failed')
    with patch.object(batch, 'ROOT', tmp_path), patch.object(batch, 'SeedanceClient', return_value=client):
        with unittest.TestCase().assertRaisesRegex(ValueError, 'terminal status'):
            batch.generate(dict(node_id='test', directory='node', location='online', duration_seconds=4,
                reference_image_directory='reference'), {}, submit_new=True)
    payload = client.submit.call_args.args[0]
    assert [c['type'] for c in payload['content']] == ['text', 'image_url']
    assert payload['content'][1]['image_url']['url'] == 'https://example.invalid/original.jpg'
    assert 'reference_video_file' not in batch.load(node / 'request.json')


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for name, function in sorted(globals().copy().items()):
        if not name.startswith('test_'):
            continue
        def run(function=function):
            if 'tmp_path' in function.__code__.co_varnames[:function.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as path:
                    function(Path(path))
            else:
                function()
        suite.addTest(unittest.FunctionTestCase(run, description=name))
    return suite


if __name__ == '__main__':
    unittest.main()
