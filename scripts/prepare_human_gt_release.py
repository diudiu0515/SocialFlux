"""Freeze participant-matched T1–3 inputs and a score-blind 50/200 T4 sample.

Private packets are gzip encoded for server-only loading, never static assets.
No model calls, source repair, or quality-score-based selection is performed.
"""
import argparse
import base64
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

from evaluation.t4_evaluation import assert_t4_trajectory, public_t4_judge_packet
from evaluation.t4_rubric import T4_RUBRIC
from tasks.offline_choice import public_instance
from web.annotation_sessions import current_items, private_evidence
from web.live_rollouts import ACTIVE, SCENARIOS, ROOT
from web.offline_review import bound_video_materials, item_digest

RELEASE = 'human-gt-20261022-v1'
SEED = 'socialflux-human-t4-20261022-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def packed(value):
    return base64.b64encode(gzip.compress(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0)).decode()


def prepare(site):
    original, bank_sha = current_items('scenarios-v2')
    bound = bound_video_materials(original, 'scenarios-v2')
    output = {'release': RELEASE, 'source_bank_sha256': bank_sha, 'items': [], 'assignments': [],
              'rubric': T4_RUBRIC, 'private': {}, 'evidence_blobs': {}, 't4': [], 'sampling': {}}
    media = json.loads((site / 'data/multimodal.json').read_text())
    media_by_sha = {x['sha256']: x for x in media['videos']}
    for item in original:
        ident = item['instance_id']
        videos = []
        if bound[ident]['ready']:
            for a in bound[ident]['media']:
                asset = media_by_sha[a['sha256']]
                file = site / 'public' / asset['url'].lstrip('/')
                if hashlib.sha256(file.read_bytes()).hexdigest() != a['sha256']:
                    raise ValueError('Video content mismatch: ' + ident)
                videos.append({k: a[k] for k in ('asset_id', 'sha256', 'evidence_ids')} | {'url': asset['url']})
        output['items'].append({'id': ident, 'scene_id': item['story_id'], 'task': item['task'],
            'item_sha256': item_digest(item), 'public_text': public_instance(item),
            'public_video': bound[ident]['public'] if videos else None, 'media': videos,
            'coverage': bound[ident]['media_coverage'] if videos else None})
        a = item['authoring']
        machine = {k: a[k] for k in ('answer', 'rationale', 'evidence_ids', 'option_errors',
                    'option_variable_map', 'oracle_reference', 'api_screening') if k in a}
        evidence = private_evidence(item, bank_sha)
        for key, value in list(evidence.items()):
            if isinstance(value, (dict, list)):
                sha = digest(value)
                output['evidence_blobs'].setdefault(sha, packed(value))
                evidence[key] = {'$ref': sha}
        output['private'][ident] = packed({'evidence': evidence,
            'machine': machine, 'machine_status': 'machine_candidates_not_human_GT'})
    for mode in ['offline_video', 'offline_text']:
        scenes = sorted({x['scene_id'] for x in output['items'] if mode == 'offline_text' or x['media']})
        for index in range(0, len(scenes), 5):
            group = scenes[index:index + 5]
            output['assignments'].append({'id': f'{mode}-{index // 5 + 1:02}', 'track': mode,
                'label': f'T1–3 · {"文字＋视频" if mode == "offline_video" else "文字"} · 第 {index // 5 + 1} 组',
                'scene_ids': group, 'item_ids': [x['id'] for x in output['items'] if x['scene_id'] in group]})

    cf_root = ROOT / 'data/claude150_v1/state_v3_validation/full_rollout_state_repair_v31/sources'
    rows, eligible, excluded = [], {'CF150': [], 'GPT50': []}, []
    for family, total in [('CF150', 150), ('GPT50', 50)]:
        for i in range(1, total + 1):
            ident = f'{family}_{i:03}'
            trajectory_path = (cf_root / f'scenario_{i:03}/trajectory.json' if family == 'CF150'
                               else ACTIVE / f'{i - 1:02}_{ident}_gpt/trajectory.json')
            scenario_path = (ROOT / f'data/claude150_v1/scenarios_state_v3/scenario_{i:03}/scenario_{i:03}.json'
                             if family == 'CF150' else SCENARIOS / f'scenarios/gpt_{i:03}.json')
            try:
                raw = trajectory_path.read_bytes()
                trajectory = assert_t4_trajectory(json.loads(raw))
                scenario = json.loads(scenario_path.read_text())
                if trajectory['scenario_id'] != ident or scenario['scenario_id'] != ident:
                    raise ValueError('scenario identity mismatch')
                packet = public_t4_judge_packet(trajectory, scenario)
                # Retain the exact public context frozen with the generated trajectory.
                frozen = trajectory.get('public_scenario_context') or {}
                for target, source in [('public_background', 'background'), ('public_situation', 'public_situation'),
                                       ('evaluated_agent_role', 'evaluated_agent_role'), ('target_character', 'environment_role')]:
                    if source in frozen:
                        packet[target] = frozen[source]
                eligible[family].append({'id': ident, 'family': family, 'packet': packet,
                    'trajectory_sha256': hashlib.sha256(raw).hexdigest(), 'packet_sha256': digest(packet),
                    'source_path': str(trajectory_path.relative_to(ROOT)), 'scenario_path': str(scenario_path.relative_to(ROOT)),
                    'policy_condition': trajectory.get('policy_provenance', {}).get('observation_condition', 'unrecorded'),
                    'policy_model': trajectory.get('policy_provenance', {}).get('model'),
                    'judge_condition': 'text_only', 'machine': None})
            except (OSError, ValueError, KeyError) as exc:
                excluded.append({'id': ident, 'reason': str(exc), 'source_path': str(trajectory_path.relative_to(ROOT))})
    for family, count in [('CF150', 38), ('GPT50', 12)]:
        pool = sorted(eligible[family], key=lambda x: hashlib.sha256((SEED + ':' + x['id']).encode()).hexdigest())
        if len(pool) < count:
            raise ValueError('Insufficient complete trajectories: ' + family)
        rows.extend(pool[:count])
    # Scores are attached only AFTER selection, with exact packet matching.
    judge_root = ROOT / 'build/t4_gpt50_20261008_multimodel/judges/claude'
    judge_manifest = json.loads((judge_root / 'manifest.json').read_text())
    for row in rows:
        for r in judge_manifest['records']:
            if r['scenario_id'] != row['id'] or r.get('observation_condition') != 'text_only':
                continue
            path = judge_root / 'results' / (r['record_id'] + '.json')
            if not path.exists():
                continue
            value = json.loads(path.read_text())
            if value.get('status') == 'completed' and digest(value.get('judge_packet')) == row['packet_sha256']:
                row['machine'] = {'model': judge_manifest['identity']['judge']['provider']['model'],
                    'judgment': value['judgment'], 'packet_sha256': row['packet_sha256'],
                    'result_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        output['t4'].append(row)
    for index in range(0, 50, 5):
        group = rows[index:index + 5]
        output['assignments'].append({'id': f't4-{index // 5 + 1:02}', 'track': 't4',
            'label': f'T4 · 轨迹五维评分 · 第 {index // 5 + 1} 组',
            'scene_ids': [x['id'] for x in group], 'item_ids': [x['id'] for x in group]})
    output['sampling'] = {'seed': SEED, 'population': 200, 'eligible': {k: len(v) for k, v in eligible.items()},
        'sample': {'CF150': 38, 'GPT50': 12}, 'selected': [x['id'] for x in rows], 'excluded': excluded,
        'claude_available': sum(x['machine'] is not None for x in rows),
        'rule': 'Hash-ranked within source strata; eligibility requires a coherent completed trajectory, before consulting scores. No score filtering or best-of-run selection.',
        'scope': 'Retrospective calibration of existing generated trajectories; not a new text/video policy experiment.'}
    output['dataset_sha256'] = digest(output)
    # Pack the server-only data to keep the Worker bounded. This file is never imported by client components.
    (site / 'data/research-server.json').write_text(json.dumps({'gzip_base64': packed(output)}, separators=(',', ':')) + '\n')
    report = ROOT / 'reports/experiments/2026-10-22_human_gt_release.json'
    report.write_text(json.dumps({k: output[k] for k in ('release', 'dataset_sha256', 'sampling', 'assignments')}, ensure_ascii=False, indent=2) + '\n')
    target = ROOT / 'data/human_gt_20261022'
    target.mkdir(exist_ok=True)
    (target / 'release.json').write_text(json.dumps(output, ensure_ascii=False))
    print(json.dumps({'release': RELEASE, 'items': len(output['items']), 'video_items': sum(bool(x['media']) for x in output['items']),
        't4': len(rows), 'sampling': output['sampling'] | {'excluded': len(excluded), 'selected': 'frozen in report'},
        'server_bytes': (site / 'data/research-server.json').stat().st_size}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--site-dir', type=Path, default=Path('build/annotation-demo-site'))
    prepare(parser.parse_args().site_dir)
