"""Bind frozen Gate2 human review packets to the existing annotation scenes.

This is a presentation/export adapter, not another environment execution path.
Private packets stay in the server bundle; independent votes omit outcomes.
"""
import argparse
import base64
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import shutil

from environment.state_ontology import STATE_VARIABLE_ONTOLOGY

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/gate2_machine_20261020_complete'
OUT = ROOT / 'data/gate2_annotation_20261022'


def read(path):
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def select(value, keys):
    return {k: value[k] for k in keys if k in value}


def output(value):
    return select(value, ['numeric_state_delta', 'numeric_dynamics_delta', 'state_delta', 'dynamics_delta', 'appraisal', 'state_judgments'])


VERDICTS = {'yes': '合理 / 是', 'no': '不合理 / 否', 'uncertain': '证据不足 / 无法判断'}


def question(key, label, choices=None):
    return dict(id=key, label=label, choices=choices or VERDICTS)


def build(site):
    research = json.loads(gzip.decompress(base64.b64decode(read(site / 'data/research-server.json')['gzip_base64'])))
    scenes = sorted({x['scene_id'] for x in research['items']})
    trajectories = {v['scenario_id']: (p, v) for p in (SOURCE / 'rollouts').glob('*/trajectory.json') for v in [read(p)]}
    scenarios = {v['scenario_id']: v for p in (SOURCE / 'scenarios').glob('*/*.json') for v in [read(p)]}
    tasks = []

    def add(ident, sid, kind, title, evidence, questions, stage='review', **extra):
        if sid not in scenes:
            return
        task = dict(id=ident, scene_id=sid, kind=kind, title=title, stage=stage, evidence=evidence, questions=questions, **extra)
        task['sha256'] = digest(task)
        tasks.append(task)

    def rows(name):
        d = read(SOURCE / 'gate2' / (name + '.json'))
        return d.get('review_items', d.get('records', []))

    def checkpoint(sid, turn_id):
        return next(t for t in trajectories[sid][1]['turns'] if t['turn_id'] == turn_id)

    def turn_view(t):
        return select(t, ['turn_id', 'segment_id', 'elapsed_time_before', 'policy_action', 'environment_response', 'state_before', 'numeric_state_delta', 'state_after', 'trigger_events'])

    for sid in scenes:
        if sid in scenarios:
            scenario = select(scenarios[sid], ['title', 'background', 'environment_background', 'environment_visible_narrative', 'environment_agent', 'evaluated_agent_role', 'initial_state', 'selected_state_variables'])
        else:
            item = next(x for x in research['items'] if x['scene_id'] == sid)
            private = json.loads(gzip.decompress(base64.b64decode(research['private'][item['id']])))
            scenario = private['evidence']['scenario']
            if '$ref' in scenario:
                scenario = json.loads(gzip.decompress(base64.b64decode(research['evidence_blobs'][scenario['$ref']])))
        add('scenario:' + sid, sid, 'scenario', '场景设定是否合理', scenario,
            [question('plausible', '角色动机、背景约束与初始状态是否相互一致？')])
        if sid in trajectories:
            path, trj = trajectories[sid]
            add('rollout:' + sid, sid, 'rollout', '完整 rollout 核对',
                dict(note='这是 Gate2 冻结轨迹。请按实际保存的轮次判断；部分轨迹不能当作完整 E2 样本。',
                     trajectory_id=trj['trajectory_id'], ending=trj.get('ending'), initial_state=trj['initial_state'],
                     turns=[turn_view(t) for t in trj['turns']]),
                [question('plausible', '对话发展、状态变化与角色行为是否合理？')], source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    for r in rows('state_transition_agreement'):
        sid = r['scenario_id']; t = checkpoint(sid, r['turn_id'])
        add(r['review_id'], sid, 'E1', '独立判断状态更新方向',
            dict(scenario=select(scenarios[sid], ['background', 'environment_background', 'environment_agent', 'evaluated_agent_role']),
                 persona=r['persona'], history=t['environment_snapshot_before'].get('history', []),
                 variable_definitions={k: STATE_VARIABLE_ONTOLOGY.get(k, {}).get('definition', k) for k in r['human_directions']},
                 state_before=t['state_before'], latest_action=r['latest_action']),
            [question(k, k, {'increase': '增加', 'similar': '基本不变', 'decrease': '减少', 'uncertain': '无法判断'}) for k in r['human_directions']],
            stage='independent', machine=r['machine_directions_after_vote'])
    for r in rows('trajectory_plausibility'):
        labels = dict(persona_consistency='人格一致性', history_sensitivity='历史敏感性', state_continuity='状态连续性', response_state_consistency='回复与状态一致性', overall='整体合理性')
        add(r['review_id'], r['scenario_id'], 'E2', '轨迹合理性五维评分' + ('（部分轨迹，仅诊断）' if r['source_status'] == 'generation_error' else ''),
            dict(source_status=r['source_status'], turn_count=r['turn_count'], turns=r['turns']),
            [question(k, v + '（1 很差 → 5 很好）', {str(i): str(i) for i in range(1, 6)} | {'uncertain': '无法判断'}) for k, v in labels.items()])
    for r in sorted(rows('history_intervention'), key=lambda x: x['scenario_id'])[:10]:
        add('E3:' + r['scenario_id'], r['scenario_id'], 'E3', '历史干预是否符合上下文',
            dict(action=r['action'], full_history=r['full_history'], critical_removed_history=r['critical_removed_history'],
                 full_output=output(r['full_output']), critical_removed_output=output(r['critical_removed_output'])),
            [question('plausible', '删除关键历史后，差异（或不变）是否有合理依据？')])
    pairs = {(r['scenario_id'], r['original_action'], r['paraphrase']): r for r in rows('paraphrase_robustness')}
    followup_paths = sorted((ROOT / 'data/gate2_followup_20261022/results').glob('*.json'))
    followup_paths += sorted((ROOT / 'data/gate2_followup_budget_20261022/results').glob('*.json'))
    followup_paths += sorted((ROOT / 'data/gate2_followup_final_20261022/results').glob('*.json'))
    for path in followup_paths:
        r = read(path)
        if r.get('paraphrase'):
            pairs[(r['scenario_id'], r['original_action'], r['paraphrase'])] = r
    for (sid, original, paraphrase), r in pairs.items():
        t = checkpoint(sid, r['checkpoint_turn_id'])
        add('E4:' + sid + ':' + digest([original, paraphrase])[:12], sid, 'E4', '释义是否保持原意',
            dict(history=t['environment_snapshot_before'].get('history', []), original_action=original, paraphrase=paraphrase),
            [question('equivalent', '语言、事实、承诺、立场和语气强度是否保持一致？', {'yes': '等价', 'no': '不等价', 'uncertain': '无法判断'})], stage='independent')
    for r in sorted(rows('local_counterfactual'), key=lambda x: x['scenario_id'])[:10]:
        add('E5:' + r['scenario_id'], r['scenario_id'], 'E5', '同一状态下不同行动的后果',
            dict(history=r['checkpoint_history'], state_before=r['state_before'], branches=[dict(action=b['candidate_action'], output=output(b['output'])) for b in r['branches']]),
            [question('plausible', '各行动产生的状态差异是否社会合理，而非仅仅不同？')])
    for r in sorted(rows('persona_intervention'), key=lambda x: x['scenario_id'])[:10]:
        add('E7:' + r['scenario_id'], r['scenario_id'], 'E7', '人格干预后的变化是否合理',
            dict(**select(r, ['action', 'fixed_checkpoint', 'original_persona', 'counterfactual_persona']),
                 original_output=output(r['original_output']), counterfactual_output=output(r['counterfactual_output'])),
            [question('plausible', '固定状态、历史与行动后，评估和状态变化是否符合人格差异？')])
    videos = {v['sha256']: v['url'] for v in read(site / 'data/multimodal.json')['videos']}
    for r in read(ROOT / 'data/gate_media_machine_20261020/video_state_consistency.json')['review_items']:
        n = r['node']; sha = n['video_sha256']; path = ROOT / n['video_path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError('Gate2 video changed: ' + str(path))
        url = videos.get(sha, '/media/gate2-' + sha[:20] + '.mp4')
        target = site / 'public' / url.lstrip('/')
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        add('E8:' + r['binding'], n['scenario_id'], 'E8', '状态与视频表达核对',
            select(n, ['trajectory_id', 'turn_id', 'state_context', 'observable_expression', 'profile_binding']),
            [question('expression', '视频表情是否与给定状态和变化方向一致？'),
             question('audio', '音轨是否有不一致或无法理解的表达？', {'consistent': '听过，表达一致 / 无语义冲突', 'inconsistent': '存在冲突或异常', 'no_speech': '听过，无可辨语义语音', 'unavailable': '无法播放 / 未能判断'})],
            video=dict(url=url, sha256=sha), source_sha256=n['trajectory_sha256'])
    for r in rows('timescale_validity'):
        sid = r['scenario_id']; family, key = r['state_id'].split('.')
        series = [dict(turn_id=t['turn_id'], action=t['policy_action'], response=t['environment_response'],
                       before=t['state_before'].get(family, {}).get(key), after=t['state_after'].get(family, {}).get(key)) for t in trajectories[sid][1]['turns']]
        add(r['review_id'], sid, 'E9', '变量变化的时间尺度', dict(variable=r['state_id'], definition=STATE_VARIABLE_ONTOLOGY.get(r['state_id'], {}).get('definition'), turns=series),
            [question('observed_timescale', '结合证据判断变化尺度', {'fast': '快', 'medium': '中', 'slow': '慢', 'uncertain': '无法判断'}),
             question('contextually_valid', '变化速度在该上下文中是否合理？'), question('direction_consistent', '方向是否与事件一致？')],
            machine=dict(expected_timescale_prior=r['expected_timescale_prior']))
    bundle = dict(format='socialflux_gate2_review_v1', dataset_sha256=research['dataset_sha256'], tasks=tasks)
    bundle['sha256'] = digest(bundle)
    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / 'versions'
    archive.mkdir(exist_ok=True)
    if (OUT / 'release.json').exists():
        previous = read(OUT / 'release.json')
        (archive / (previous['sha256'] + '.json')).write_text(json.dumps(previous, ensure_ascii=False) + '\n')
    (OUT / 'release.json').write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + '\n')
    (archive / (bundle['sha256'] + '.json')).write_text(json.dumps(bundle, ensure_ascii=False) + '\n')
    server = dict(current=bundle['sha256'], versions=[read(p) for p in sorted(archive.glob('*.json'))])
    packed = base64.b64encode(gzip.compress(json.dumps(server, ensure_ascii=False).encode(), mtime=0)).decode()
    (site / 'data/gate2-review-server.json').write_text(json.dumps(dict(gzip_base64=packed)) + '\n')
    summary = dict(sha256=bundle['sha256'], dataset_sha256=bundle['dataset_sha256'], counts=dict(Counter(t['kind'] for t in tasks)), scene_count=len(scenes), human_review='pending')
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--site', type=Path, required=True)
    build(parser.parse_args().site)
