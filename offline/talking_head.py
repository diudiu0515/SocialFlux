"""Source-bound talking heads with English production speech."""
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from copy import deepcopy
import hashlib
import fcntl
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from environment.online_video_assets import online_identity_spec
from offline.choice_builder import load, save, save_text, sha
from evaluation.t4_media import extract_frames
from prompts.loader import get_prompt, render_prompt
from tasks.offline_choice import public_instance, validate_item

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / 'tasks/examples/offline_scenarios_v2'
ASSET_ROOT = ROOT / 'data/offline_talking_head_v1'
PROMPT_ID = 'offline_talking_head_exact_v1'
PROFILE = 'offline_exact_dialogue_v1'
SOURCE_MANIFEST = ROOT / 'data/gpt50/experiment/multimodal_delivery_v1/online_multimodal/manifest.json'
TOKEN = re.compile(r"[A-Za-z0-9]+(?:[.'’-][A-Za-z0-9]+)*|[\u3400-\u9fff]|.", re.S)


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def spoken_units(text):
    return sum(1 if re.match(r'[\u3400-\u9fff]', token) else 1.6
               if re.match(r'[A-Za-z0-9]', token) else 0 for token in TOKEN.findall(text))


def split_line(text, max_units=42):
    """Lossless phrase splitting; no translated or compressed speech substitute."""
    if not text.strip():
        raise ValueError('empty source dialogue')
    tokens = TOKEN.findall(text)
    parts, pending = [], tokens
    while pending:
        units, end, boundary = 0, 0, None
        for index, token in enumerate(pending):
            cost = spoken_units(token)
            if units + cost > max_units and index:
                break
            units += cost
            end = index + 1
            if token in '。！？；，、—：!?;,:\n':
                boundary = end
        if end < len(pending) and boundary:
            end = boundary
        parts.append(''.join(pending[:end]))
        pending = pending[end:]
    if ''.join(parts) != text or any(not part.strip() for part in parts):
        raise ValueError('dialogue segmentation changed the source line')
    return parts


def public_nodes(items):
    nodes = {}
    for item in items:
        validate_item(item)
        occurrences = []
        if item['task'] == 'T2':
            for key in ('history_a', 'history_b'):
                occurrences.extend((t['turn_id'].split(':')[-1], t['turn_id'],
                                    t['environment_character'], t.get('observable_expression', {}))
                                   for t in item['input'][key][:-1])
            ending = item['input']['shared_ending']
            occurrences.append(('ending', ending['turn_id'], ending['current_response'],
                                ending.get('observable_expression', {})))
        else:
            occurrences.extend((t['turn_id'], t['turn_id'], t['environment_character'],
                                t.get('observable_expression', {})) for t in item['input']['history'])
        for location, evidence_id, line, expression in occurrences:
            public = {'scenario_id': item['story_id'], 'speaker': item['input']['target_character'],
                      'location': location, 'source_public_response': line,
                      'source_observable_expression': expression}
            node_id = item['story_id'] + '-' + location + '-' + canonical_sha(public)[:16]
            if node_id not in nodes:
                nodes[node_id] = {**deepcopy(public), 'node_id': node_id, 'bindings': [],
                                  'scenario_source': deepcopy(item['authoring']['construction_source'])}
            bindings = nodes[node_id]['bindings']
            binding = next((b for b in bindings if b['instance_id'] == item['instance_id']), None)
            if binding is None:
                binding = {'instance_id': item['instance_id'], 'item_sha256': canonical_sha(item), 'evidence_ids': []}
                bindings.append(binding)
            binding['evidence_ids'].append(evidence_id)
    return list(nodes.values())


def continuity_references(manifest_path):
    manifest = load(manifest_path)
    batch = ROOT / manifest['batch_root']
    references = {}
    for row in sorted(manifest['requests'], key=lambda x: (x.get('dependency_phase', 1), x['request_id'])):
        if row.get('status') != 'generated_structural_pass' or row['scenario_id'] in references:
            continue
        path = batch / row['video_file']
        if path.is_file() and sha(path) == row.get('video_sha256'):
            references[row['scenario_id']] = {'path': str(path.relative_to(ROOT)),
                                              'sha256': row['video_sha256'], 'identity_id': row.get('identity_id')}
    return references


def prepare(bank=BANK, output=None, source_manifest=SOURCE_MANIFEST):
    bank = Path(bank)
    bank_sha = sha(bank / 'items.jsonl')
    output = Path(output or ASSET_ROOT / bank_sha[:16])
    if (output / 'manifest.json').exists():
        previous = load(output / 'manifest.json')
        if previous['items_sha256'] != bank_sha or previous['prompt_sha256'] != hashlib.sha256(get_prompt(PROMPT_ID).encode()).hexdigest():
            raise ValueError('existing talking-head queue belongs to a different bank or prompt')
        return previous
    items = [json.loads(line) for line in (bank / 'items.jsonl').read_text().splitlines() if line.strip()]
    nodes = public_nodes(items)
    if any(re.search(r'[\u3400-\u9fff]', n['source_public_response']) for n in nodes):
        raise ValueError('English speech required; prepare a source-bound English localization first')
    references = continuity_references(source_manifest)
    requests = []
    for node in nodes:
        source = node['scenario_source']
        scenario_path = ROOT / source['scenario_path']
        if sha(scenario_path) != source['scenario_sha256']:
            raise ValueError('frozen scenario changed')
        identity = online_identity_spec(load(scenario_path))
        reference = references.get(node['scenario_id'])
        node['continuity_reference'] = reference
        node['human_review'] = 'pending'
        node['status'] = 'request_ready'
        parts = split_line(node['source_public_response'])
        node['segment_request_ids'] = []
        for index, part in enumerate(parts, 1):
            request_id = node['node_id'] + f'-s{index:02d}'
            prompt = render_prompt(PROMPT_ID, identity_json=identity,
                language='Mandarin Chinese with any original English terms preserved' if re.search(r'[\u3400-\u9fff]', part) else 'English',
                spoken_line=part, expression_json=node['source_observable_expression'],
                part_number=index, part_count=len(parts))
            request = {'profile': PROFILE, 'prompt_id': PROMPT_ID, 'prompt': prompt,
                       'duration_seconds': max(4, min(15, math.ceil(1.5 + spoken_units(part) / 3.3))),
                       'generate_audio': True, 'ratio': '16:9', 'identity': identity,
                       'reference_video_file': reference['path'] if reference else None,
                       'audio': {'required': True, 'spoken_content': True, 'exact_line': part,
                                 'mode': 'exact_source_language_with_lip_sync'}}
            request_file = output / 'requests' / (request_id + '.json')
            save(request_file, request)
            requests.append({'request_id': request_id, 'scenario_id': node['scenario_id'],
                             'node_id': node['node_id'], 'segment_index': index, 'segment_count': len(parts),
                             'request_file': str(request_file.relative_to(ROOT)),
                             'video_file': str((output / 'segments' / (request_id + '.mp4')).relative_to(ROOT)),
                             'source_public_response': part, 'status': 'request_ready'})
            node['segment_request_ids'].append(request_id)
    manifest = {'format': 'socialflux_offline_talking_head_v1', 'profile': PROFILE,
                'batch_root': str(ROOT), 'bank_path': str(bank.relative_to(ROOT)),
                'items_sha256': bank_sha, 'prompt_id': PROMPT_ID,
                'prompt_sha256': hashlib.sha256(get_prompt(PROMPT_ID).encode()).hexdigest(),
                'provider': {'model': 'doubao-seedance-2-0-260128', 'resolution': '720p'},
                'item_count': len(items), 'node_count': len(nodes), 'request_count': len(requests),
                'scenario_count': len({n['scenario_id'] for n in nodes}),
                'missing_reference_scenes': sorted({n['scenario_id'] for n in nodes if not n['continuity_reference']}),
                'human_review': 'pending', 'nodes': nodes, 'requests': requests}
    save(output / 'manifest.json', manifest)
    return manifest


def summary(manifest):
    return {k: manifest[k] for k in ('items_sha256', 'item_count', 'node_count', 'request_count',
                                    'scenario_count', 'missing_reference_scenes')}


def current_bank(manifest):
    bank = ROOT / manifest['bank_path']
    if sha(bank / 'items.jsonl') != manifest['items_sha256']:
        raise ValueError('offline bank changed since this talking-head queue was frozen')
    return bank


def progress(manifest_path):
    manifest_path = Path(manifest_path)
    manifest = load(manifest_path)
    counts = Counter()
    completed = set()
    for record in manifest['requests']:
        state_path = manifest_path.parent / 'provider_states' / (record['request_id'] + '.json')
        state = load(state_path) if state_path.is_file() else {}
        status = state.get('status', 'not_submitted')
        if status == 'downloaded':
            path = ROOT / record['video_file']
            if not path.is_file() or sha(path) != state.get('video_sha256'):
                status = 'asset_integrity_failure'
            else:
                completed.add(record['request_id'])
        counts[status] += 1
    result = {**summary(manifest), 'format': 'socialflux_offline_talking_head_progress_v1',
              'preview_only': manifest.get('preview_only', False),
              'speech_language': manifest.get('speech_language'),
              'segment_statuses': dict(counts), 'downloaded_segments': len(completed),
              'downloaded_nodes': sum(set(n['segment_request_ids']) <= completed for n in manifest['nodes']),
              'human_review': 'pending', 'speech_verified': False}
    save(manifest_path.parent / 'progress.json', result)
    if not manifest.get('preview_only'):
        save(current_bank(manifest) / 'talking_head_status.json', result)
    return result


def generate(manifest_path, *, submit_new=False, workers=4, request_ids=None):
    """Use the existing resumable provider queue; bootstrap missing identities first."""
    from scripts.run_multimodal_video_queue import DEFAULT_KEY_FILE, run_record
    manifest_path = Path(manifest_path)
    manifest = load(manifest_path)
    current_bank(manifest)
    selected = [r for r in manifest['requests'] if request_ids is None or r['request_id'] in request_ids]
    if request_ids is not None and set(request_ids) != {r['request_id'] for r in selected}:
        raise ValueError('unknown talking-head request ID')
    if not 1 <= workers <= 4:
        raise ValueError('video workers must be in 1..4')
    def priority(record):
        path = manifest_path.parent / 'provider_states' / (record['request_id'] + '.json')
        state = load(path) if path.exists() else {}
        active = bool(state.get('task_id') and state.get('status') not in
                      {'downloaded', 'succeeded', 'failed', 'expired', 'cancelled'})
        return (0 if active else 1 if '-ending-' in record['request_id'] or record.get('quality_retry') else 2,
                record.get('segment_index', 1), record['scenario_id'], record['request_id'])
    selected.sort(key=priority)
    def run(record):
        return run_record(ROOT, record, key_file=DEFAULT_KEY_FILE,
                          model=manifest['provider']['model'], resolution=manifest['provider']['resolution'],
                          submit_new=submit_new, poll_seconds=15, max_wait_seconds=1800)
    blocked_scenes, bootstrapped = set(), set()
    bootstrap_scenes = set(manifest['missing_reference_scenes']) | set(manifest.get('preview_identity_bootstraps', {}))
    anchors = []
    for scene in sorted(bootstrap_scenes):
        if not any(r['scenario_id'] == scene for r in selected):
            continue
        records = [r for r in manifest['requests'] if r['scenario_id'] == scene]
        anchor_id = manifest.get('preview_identity_bootstraps', {}).get(scene)
        anchor = next((r for r in records if r['request_id'] == anchor_id), records[0])
        if anchor not in selected:
            state_path = manifest_path.parent / 'provider_states' / (anchor['request_id'] + '.json')
            state = load(state_path) if state_path.is_file() else {}
            if state.get('status') != 'downloaded':
                raise ValueError('selection must include the ungenerated identity anchor')
        anchors.append(anchor)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run, anchor): anchor for anchor in anchors}
        anchor_results = []
        for future in as_completed(futures):
            anchor_results.append((futures[future], future.result()))
    for anchor, result in anchor_results:
        scene = anchor['scenario_id']
        records = [r for r in manifest['requests'] if r['scenario_id'] == scene]
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result['status'] != 'downloaded':
            blocked_scenes.add(scene)
            continue
        bootstrapped.add(anchor['request_id'])
        reference = {'path': anchor['video_file'], 'sha256': sha(ROOT / anchor['video_file']),
                     'origin': 'first_exact_dialogue_segment'}
        for record in records:
            if record['request_id'] == anchor['request_id']:
                continue
            path = ROOT / record['request_file']
            request = load(path)
            if request.get('reference_video_file') == reference['path']:
                continue
            if (manifest_path.parent / 'provider_states' / (record['request_id'] + '.json')).exists():
                raise ValueError('cannot replace continuity reference after provider state was created')
            original = path.with_suffix('.before_reference.json')
            if not original.exists():
                shutil.copyfile(path, original)
            request['reference_video_file'] = reference['path']
            save(path, request)
        for node in manifest['nodes']:
            if node['scenario_id'] == scene:
                node['continuity_reference'] = reference
        save(manifest_path, manifest)
    finalize(manifest_path)
    pending = iter(r for r in selected if r['scenario_id'] not in blocked_scenes and r['request_id'] not in bootstrapped)
    # Bound outstanding work and stop scheduling on account-wide failures.
    account_blocked = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        active = {}
        def schedule():
            while not account_blocked and len(active) < workers:
                record = next(pending, None)
                if record is None:
                    break
                if record['scenario_id'] in blocked_scenes:
                    continue
                active[pool.submit(run, record)] = record
        schedule()
        while active:
            ready, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in ready:
                record = active.pop(future)
                result = future.result()
                print(json.dumps(result, ensure_ascii=False), flush=True)
                error = json.dumps(result.get('error', {})).lower()
                if any(word in error for word in ('sensitivecontentdetected', 'policyviolation', 'copyright restrictions')):
                    blocked_scenes.add(record['scenario_id'])
                if any(word in error for word in ('insufficient', 'balance', 'unauthorized', 'invalid api key', 'status_code": 401')):
                    account_blocked = True
                finalize(manifest_path)
            schedule()
    return finalize(manifest_path)


def trim_boundary_silence(path, metadata, directory):
    """Shorten only long boundary silence, retaining the original provider file."""
    duration = metadata['duration_seconds_actual']
    target = directory / path.name
    sidecar = target.with_suffix('.json')
    source_sha = sha(path)
    previous = load(sidecar) if sidecar.is_file() else {}
    if previous.get('source_sha256') == source_sha and previous.get('version') == 1 and previous.get('trimmed') is False:
        return path, previous
    if (previous.get('source_sha256') == source_sha and previous.get('version') == 1
            and target.is_file() and previous.get('sha256') == sha(target)):
        return target, previous
    analysis = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', str(path),
        '-af', 'silencedetect=noise=-40dB:d=0.3', '-f', 'null', '-'],
        capture_output=True, text=True, check=True, timeout=120).stderr
    intervals, pending = [], None
    for line in analysis.splitlines():
        match = re.search(r'silence_start: ([\d.]+)', line)
        if match:
            pending = float(match[1])
        match = re.search(r'silence_end: ([\d.]+)', line)
        if match and pending is not None:
            intervals.append((pending, float(match[1])))
            pending = None
    start, end = 0, duration
    for left, right in intervals:
        if left <= .05 and right > 1.25:
            start = max(0, right - .35)
        if right >= duration - .1 and duration - left > 1.25:
            end = min(duration, left + .6)
    # All-silent or implausibly tiny detections are left intact for manual review.
    if end - start < 1 or (start == 0 and end == duration):
        record = {'source_sha256': source_sha, 'start_seconds': 0, 'end_seconds': duration,
                  'version': 1, 'trimmed': False}
        directory.mkdir(exist_ok=True)
        save(sidecar, record)
        return path, record
    directory.mkdir(exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
        '-ss', str(start), '-i', str(path), '-t', str(end - start),
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-threads', '4',
        '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(target)],
        check=True, timeout=180)
    record = {'source_sha256': source_sha, 'sha256': sha(target), 'start_seconds': start,
              'end_seconds': end, 'version': 1, 'trimmed': True}
    save(sidecar, record)
    return target, record


def finalize(manifest_path):
    """Assemble complete nodes, retain source speech, and screen local media streams."""
    manifest_path = Path(manifest_path).resolve()
    with (manifest_path.parent / 'finalize.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _finalize(manifest_path)


def concatenate_spoken_segments(paths, target):
    """Decode differing audio sample rates before joining spoken clips.

    Stream-copy concatenation changes the speed of later AAC segments when a
    provider returns mixed 32/44.1 kHz audio. Normalize timestamps and audio;
    retain the original generated files for provenance.
    """
    command=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
    for path in paths:command.extend(['-i',str(path)])
    filters=[];inputs=[]
    for i in range(len(paths)):
        filters.extend([f'[{i}:v]setpts=PTS-STARTPTS,fps=24,format=yuv420p[v{i}]',
                        f'[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[a{i}]'])
        inputs.extend([f'[v{i}]',f'[a{i}]'])
    filters.append(''.join(inputs)+f'concat=n={len(paths)}:v=1:a=1[v][a]')
    command.extend(['-filter_complex',';'.join(filters),'-map','[v]','-map','[a]',
                    '-c:v','libx264','-preset','fast','-crf','18','-threads','4',
                    '-c:a','aac','-ar','48000','-b:a','160k','-movflags','+faststart',str(target)])
    subprocess.run(command,check=True,timeout=300)


def _finalize(manifest_path):
    from scripts.finalize_multimodal_video_queue import probe as media_metadata
    from scripts.run_multimodal_video_queue import ensure_state
    manifest_path = Path(manifest_path)
    manifest = load(manifest_path)
    current_bank(manifest)
    records = {r['request_id']: r for r in manifest['requests']}
    completed = []
    for node in manifest['nodes']:
        segments = []
        edits = []
        for request_id in node['segment_request_ids']:
            record = records[request_id]
            path = ROOT / record['video_file']
            state_path = manifest_path.parent / 'provider_states' / (request_id + '.json')
            state = load(state_path) if state_path.exists() else {}
            if state.get('status') != 'downloaded':
                break
            ensure_state(ROOT, record, model=manifest['provider']['model'],
                         resolution=manifest['provider']['resolution'])
            if not path.is_file() or sha(path) != state['video_sha256']:
                raise ValueError('downloaded talking-head segment checksum mismatch')
            metadata = media_metadata(path)
            if (metadata.get('audio_stream_count', 0) < 1 or metadata.get('height') != 720
                    or not 3.5 <= metadata.get('duration_seconds_actual', 0) <= 15.5):
                raise ValueError('talking-head segment failed video/audio structural checks')
            edited_path, edit = trim_boundary_silence(path, metadata, manifest_path.parent / 'trimmed_segments')
            edits.append({'request_id': request_id, **edit})
            segments.append((edited_path, metadata, record))
        if len(segments) != len(node['segment_request_ids']):
            continue
        spoken_text = node.get('spoken_text', node['source_public_response'])
        if ''.join(record.get('spoken_text', record['source_public_response']) for _, _, record in segments) != spoken_text:
            raise ValueError('talking-head segment scripts do not reconstruct the public line')
        target = manifest_path.parent / 'assets' / (node['node_id'] + '.mp4')
        target.parent.mkdir(exist_ok=True)
        binding = canonical_sha([sha(path) for path, _, _ in segments])
        binding_path = target.with_suffix('.json')
        previous = load(binding_path) if binding_path.exists() else {}
        if (previous.get('assembly_version') != 2 or previous.get('segments_sha256') != binding or not target.exists()
                or previous.get('sha256') != sha(target)):
            if len(segments) == 1:
                shutil.copyfile(segments[0][0], target)
            else:
                concatenate_spoken_segments([path for path,_,_ in segments],target)
            save(binding_path, {'assembly_version':2,'segments_sha256': binding, 'sha256': sha(target)})
        metadata = media_metadata(target)
        duration = metadata['duration_seconds_actual']
        timestamps = tuple(round(duration * fraction, 3) for fraction in (.1, .35, .6, .85))
        asset = {'path': str(target), 'sha256': sha(target), 'source_asset_id': node['node_id'],
                 'media_kind': 'talking_head', 'response_neutral': False,
                 'spoken_text': spoken_text, 'human_review': 'pending',
                 'source_public_response': node['source_public_response'],
                 'speech_language': node.get('speech_language'),
                 'boundary_silence_edits': edits,
                 'speech_verified': False, 'structural_metadata': metadata,
                 'frames': extract_frames(target, manifest_path.parent / 'frames' / sha(target), timestamps)}
        completed.append({'node_id': node['node_id'], 'asset': asset, 'bindings': node['bindings']})
    save(manifest_path.parent / 'completed_nodes.json', completed)
    result = progress(manifest_path)
    result['assembled_nodes'] = len(completed)
    save(manifest_path.parent / 'progress.json', result)
    if not manifest.get('preview_only'):
        save(current_bank(manifest) / 'talking_head_status.json', result)
    return result


def publish(manifest_path):
    """Replace the derived video condition only once all 150 nodes are present."""
    manifest_path = Path(manifest_path)
    manifest = load(manifest_path)
    if manifest.get('preview_only'):
        raise ValueError('preview-only localized samples cannot be published as a complete question bank')
    bank = current_bank(manifest)
    result = finalize(manifest_path)
    if result['assembled_nodes'] != manifest['node_count']:
        raise ValueError('talking-head generation incomplete; existing media pairs retained')
    completed = load(manifest_path.parent / 'completed_nodes.json')
    items = [json.loads(line) for line in (bank / 'items.jsonl').read_text().splitlines() if line.strip()]
    by_id = {item['instance_id']: item for item in items}
    media = {}
    for node in completed:
        for binding in node['bindings']:
            item = by_id[binding['instance_id']]
            if canonical_sha(item) != binding['item_sha256']:
                raise ValueError('talking-head binding belongs to an earlier question version')
            media.setdefault(item['instance_id'] + '-video', []).append(
                {**node['asset'], 'evidence_ids': binding['evidence_ids']})
    if len(media) != len(items):
        raise ValueError('talking-head media does not cover the entire bank')
    pairs = []
    for item in items:
        text, video = deepcopy(item), deepcopy(item)
        for variant in (text, video):
            variant['metadata']['modality_pair_id'] = item['instance_id']
            variant['authoring']['media_manifest'] = {'path': str(manifest_path), 'sha256': sha(manifest_path)}
            variant['authoring']['media_human_review'] = 'pending'
        video.update(instance_id=item['instance_id'] + '-video', modality='text+video')
        video['authoring']['matched_assets'] = [
            {'sha256': a['sha256'], 'evidence_ids': a['evidence_ids']} for a in media[video['instance_id']]]
        validate_item(text)
        validate_item(video)
        pairs.extend([text, video])
    with tempfile.TemporaryDirectory(prefix='offline-talking-head-') as temporary:
        stage = Path(temporary)
        save(stage / 'media.json', media)
        for name, values in [('paired.items.jsonl', pairs),
                             ('paired.public.jsonl', [public_instance(x) for x in pairs])]:
            save_text(stage / name, ''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in values))
        report = {'items_sha256': manifest['items_sha256'], 'media_sha256': sha(stage / 'media.json'),
                  'source_manifest': {'path': str(manifest_path), 'sha256': sha(manifest_path)},
                  'input_item_count': len(items), 'logical_pairs': len(items), 'variants': len(pairs),
                  'unique_videos': len(completed), 'media_kind': 'talking_head',
                  'coverage_counts': {'complete': len(items)}, 'gaps': [], 'human_media_review': 'pending',
                  'speech_verified': False, 'frame_transport_ready': True,
                  'frame_transport_limit': 'sampled visual frames; no audio/prosody evaluation'}
        save(stage / 'pairing_report.json', report)
        bank_manifest = load(bank / 'manifest.json')
        bank_manifest.update(modality_pairs=len(items), media_missing=0,
                             media_pairing_report_sha256=sha(stage / 'pairing_report.json'))
        save(stage / 'manifest.json', bank_manifest)
        current_bank(manifest)
        backup = manifest_path.parent / 'previous_pairs'
        backup.mkdir(exist_ok=True)
        for path in stage.iterdir():
            if (bank / path.name).exists() and not (backup / path.name).exists():
                shutil.copyfile(bank / path.name, backup / path.name)
            target = bank / (path.name + '.publishing')
            shutil.copyfile(path, target)
            target.replace(bank / path.name)
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'run', 'status', 'finalize', 'publish'], default='prepare')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--submit-new', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--request-id', action='append', dest='request_ids')
    parser.add_argument('--preview', action='store_true', help='Run only the saved user-selected preview scope')
    args = parser.parse_args()
    if args.phase == 'prepare':
        result = summary(prepare())
    else:
        if args.manifest is None:
            parser.error('--manifest is required for this phase')
        if args.phase == 'run':
            if args.preview:
                if args.request_ids:
                    parser.error('--preview and --request-id are mutually exclusive')
                selection = load(args.manifest.parent / 'preview_selection.json')
                if selection['items_sha256'] != load(args.manifest)['items_sha256']:
                    raise ValueError('preview selection belongs to a different bank')
                args.request_ids = selection['request_ids']
            result = generate(args.manifest, submit_new=args.submit_new, workers=args.workers,
                              request_ids=args.request_ids)
        else:
            result = {'status': progress, 'finalize': finalize, 'publish': publish}[args.phase](args.manifest)
    print(json.dumps(result, ensure_ascii=False))
