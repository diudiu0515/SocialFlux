"""Pair source videos with unchanged, visible history; never infer a new cue."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from offline.choice_builder import public_turn, save, save_text, sha
from evaluation.t4_media import extract_frames
from tasks.offline_choice import public_instance, validate_item

ROOT = Path(__file__).resolve().parents[1]


def history_turns(item):
    """Only pre-ending history is reusable in a controlled T2 comparison."""
    if item['task'] == 'T2':
        return [(turn, side + ':') for key, side in (('history_a', 'A'), ('history_b', 'B'))
                for turn in item['input'][key][:-1]]
    return [(turn, '') for turn in item['input']['history']]


def turn_matches(turn, source_turn, prefix):
    expected = public_turn(source_turn, prefix)
    actual = {**turn, 'observable_expression': turn.get('observable_expression') or {},
              'public_events': turn.get('public_events', [])}
    return actual == expected


def pair_assets(items, manifest_path, output, *, frames=True, frame_root=None):
    manifest_path = Path(manifest_path)
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    manifest_binding = {'path': str(manifest_path),
                        'sha256': hashlib.sha256(manifest_raw).hexdigest()}
    by_id = {r['media_asset_id']: r for r in manifest['requests']}
    if len(by_id) != len(manifest['requests']):
        raise ValueError('duplicate source media asset ID')
    batch = ROOT / manifest['batch_root']
    output = Path(output)
    frame_root = Path(frame_root) if frame_root is not None else output / 'frames'
    paired, media, gaps, coverage = [], {}, [], []
    cache, sources = {}, {}
    for item in items:
        validate_item(item)
        source = item['authoring']['construction_source']
        source_path = ROOT / source['trajectory_path']
        if source_path not in sources:
            raw = source_path.read_bytes()
            sources[source_path] = (json.loads(raw), hashlib.sha256(raw).hexdigest())
        trajectory, source_sha = sources[source_path]
        if source.get('trajectory_sha256') and source['trajectory_sha256'] != source_sha:
            raise ValueError('source trajectory checksum mismatch')
        if trajectory.get('scenario_id', item['story_id']) != item['story_id']:
            raise ValueError('source trajectory scenario mismatch')
        wanted, covered = [], set()
        visible = history_turns(item)
        required = [turn['turn_id'] for turn, _ in visible]
        if item['task'] == 'T2':
            required.append(item['input']['shared_ending']['turn_id'])
        for turn in trajectory['turns']:
            turn_id = 't' + str(turn['turn_id']).removeprefix('t')
            locations = [(t, prefix) for t, prefix in visible if t['turn_id'] == prefix + turn_id]
            if not locations:
                continue  # Future branches and controlled endings are never attached.
            ids = [t['turn_id'] for t, _ in locations]
            if any(not turn_matches(t, turn, prefix) for t, prefix in locations):
                if turn.get('media'):
                    gaps.append({'instance_id': item['instance_id'], 'evidence_ids': ids,
                                 'reason': 'public_history_changed'})
                continue
            if item['task'] == 'T2' and set(ids) != {'A:' + turn_id, 'B:' + turn_id}:
                continue
            for ref in turn.get('media', []):
                asset_id = ref.get('media_asset_id')
                record = by_id.get(asset_id)
                if record is None or record.get('status') != 'generated_structural_pass':
                    gaps.append({'instance_id': item['instance_id'], 'asset_id': asset_id,
                                 'evidence_ids': ids, 'reason': 'exact_source_asset_missing',
                                 'source_status': (record or {}).get('status', 'not_in_manifest')})
                    continue
                if record.get('scenario_id', item['story_id']) != item['story_id']:
                    raise ValueError('source media scenario mismatch')
                path = batch / record['video_file']
                expected = record['video_sha256']
                key = (str(path), expected)
                if key not in cache:
                    if not path.is_file() or sha(path) != expected:
                        raise ValueError('existing asset missing or hash changed')
                    asset = {'path': str(path), 'sha256': expected, 'human_review': 'pending'}
                    if frames:
                        asset['frames'] = extract_frames(path, frame_root / expected,
                                                         timestamps=(.25, 1.25, 2.25, 3.25))
                    cache[key] = asset
                wanted.append({**deepcopy(cache[key]), 'source_asset_id': asset_id,
                               'response_neutral': record.get('response_neutral', False),
                               'evidence_ids': ids,
                               'source_binding': {'trajectory_sha256': source_sha, 'turn_id': turn_id}})
                covered.update(ids)
        coverage.append({'instance_id': item['instance_id'], 'scenario_id': item['story_id'],
                         'task': item['task'], 'covered_evidence_ids': sorted(covered),
                         'uncovered_evidence_ids': sorted(set(required) - covered),
                         'status': 'partial' if covered and set(required) - covered else
                                   'complete' if covered else 'missing'})
        if not wanted:
            gaps.append({'instance_id': item['instance_id'], 'reason': 'no_matched_source_video'})
            continue
        text, video = deepcopy(item), deepcopy(item)
        for variant in (text, video):
            variant['metadata']['modality_pair_id'] = item['instance_id']
            variant['authoring']['media_manifest'] = manifest_binding
            variant['authoring']['media_human_review'] = 'pending'
        video['instance_id'] += '-video'
        video['modality'] = 'text+video'
        video['authoring']['matched_assets'] = [
            {'sha256': a['sha256'], 'evidence_ids': a['evidence_ids']} for a in wanted]
        validate_item(text)
        validate_item(video)
        paired.extend([text, video])
        media[video['instance_id']] = wanted
    for name, values in [('paired.items.jsonl', paired),
                         ('paired.public.jsonl', [public_instance(x) for x in paired])]:
        save_text(output / name, ''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in values))
    save(output / 'media.json', media)
    source_bytes = ''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in items).encode()
    report = {'input_item_count': len(items), 'items_sha256': hashlib.sha256(source_bytes).hexdigest(),
              'media_sha256': sha(output / 'media.json'), 'source_manifest': manifest_binding,
              'logical_pairs': len(paired) // 2, 'variants': len(paired), 'unique_videos': len(cache),
              'paired_by_task': dict(Counter(x['task'] for x in coverage if x['covered_evidence_ids'])),
              'coverage_counts': dict(Counter(x['status'] for x in coverage)),
              'coverage': coverage, 'gaps': gaps, 'human_media_review': 'pending',
              'frame_transport_ready': frames,
              'frame_transport_limit': 'sampled visual frames; no audio/prosody evaluation',
              'nonverbal_history_relation': 'exact source cues; T2 reuses unchanged shared-prefix clips on both sides; no controlled-ending video'}
    save(output / 'pairing_report.json', report)
    return report
