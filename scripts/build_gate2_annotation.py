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


def unpack(value):
    return json.loads(gzip.decompress(base64.b64decode(value)))


REGISTRY_FORMAT = 'socialflux_gate2_registry_v2'


def expand_registry(registry):
    """Recover the original version bundles, preserving task order and hashes."""
    if registry.get('format') != REGISTRY_FORMAT:
        return registry
    pool = registry['task_pool']
    versions = []
    for version in registry['versions']:
        if 'tasks' in version:
            raise ValueError('Compact Gate2 version contains inline tasks')
        tasks = []
        for sha in version['task_refs']:
            if sha not in pool or pool[sha].get('sha256') != sha:
                raise ValueError('Missing or mismatched Gate2 task reference: ' + sha)
            tasks.append(pool[sha])
        versions.append({k: v for k, v in version.items() if k != 'task_refs'} | {'tasks': tasks})
    return dict(current=registry['current'], versions=versions)


def compact_registry(registry):
    """Deduplicate storage only; frozen bundles and task identities never change."""
    legacy = expand_registry(registry)
    pool, versions = {}, []
    for version in legacy['versions']:
        refs = []
        for task in version['tasks']:
            sha = task['sha256']
            content_sha = digest({k: v for k, v in task.items() if k != 'sha256'})
            if sha in pool and (pool[sha] != task or content_sha != sha):
                raise ValueError('Conflicting Gate2 task content for SHA: ' + sha)
            if sha not in pool:
                if content_sha != sha:
                    raise ValueError('Gate2 task content hash mismatch: ' + sha)
                pool[sha] = task
            refs.append(sha)
        versions.append({k: v for k, v in version.items() if k != 'tasks'} | {'task_refs': refs})
    if legacy['current'] not in {v['sha256'] for v in versions}:
        raise ValueError('Current Gate2 bundle is not in registry')
    return dict(format=REGISTRY_FORMAT, current=legacy['current'], task_pool=pool, versions=versions)


def write_registry(path, registry):
    storage = compact_registry(registry)
    raw = json.dumps(storage, ensure_ascii=False, separators=(',', ':')).encode()
    packed = base64.b64encode(gzip.compress(raw, mtime=0)).decode()
    path.write_text(json.dumps(dict(gzip_base64=packed), separators=(',', ':')) + '\n')
    return dict(uncompressed_bytes=len(raw), encoded_bytes=path.stat().st_size,
                versions=len(storage['versions']), unique_tasks=len(storage['task_pool']),
                task_references=sum(len(v['task_refs']) for v in storage['versions']))


def compact_existing_registry(site):
    """Repack existing materials without executing build or touching archives."""
    path = site / 'data/gate2-review-server.json'
    raw = gzip.decompress(base64.b64decode(read(path)['gzip_base64']))
    original = json.loads(raw)
    legacy = expand_registry(original)
    compact = compact_registry(original)
    if expand_registry(compact) != legacy:
        raise ValueError('Gate2 registry conversion changed frozen materials')
    stats = write_registry(path, compact)
    print(json.dumps(dict(previous_uncompressed_bytes=len(raw), **stats,
                          current=compact['current'], expanded_versions_unchanged=True)))


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_source(path, expected):
    path = ROOT / path
    if file_sha(path) != expected:
        raise ValueError('Frozen source changed: ' + str(path))
    return path, read(path)


def copy_video(site, path, sha, url=None):
    if file_sha(path) != sha:
        raise ValueError('Video changed: ' + str(path))
    url = url or '/media/review-' + sha + '.mp4'
    target = site / 'public' / url.lstrip('/')
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    if file_sha(target) != sha:
        raise ValueError('Published video mismatch: ' + str(target))
    return dict(url=url, sha256=sha)


def current_source(research, item):
    """Read the exact authoring packet and immutable trajectory, never a live retry."""
    private = unpack(research['private'][item['id']])
    oracle = private['machine']['oracle_reference']
    packet_path, packet = checked_source(oracle['packet_path'], oracle['packet_sha256'])
    source = packet['sources']
    path, trajectory = checked_source(source['trajectory_path'], source['trajectory_sha256'])
    if trajectory['scenario_id'] != item['scene_id']:
        raise ValueError('Current rollout scene mismatch: ' + item['id'])
    return path, trajectory, dict(source, packet_path=str(packet_path.relative_to(ROOT)),
                                 packet_sha256=oracle['packet_sha256'])


def public_turns(value):
    if isinstance(value, dict):
        if 'turn_id' in value and any(k in value for k in ('environment_character', 'environment_response', 'current_response')):
            yield value
        for child in value.values():
            yield from public_turns(child)
    elif isinstance(value, list):
        for child in value:
            yield from public_turns(child)


def quality_questions(nonverbal=False):
    checks = {'yes': '一致 / 可接受', 'no': '不一致 / 有缺陷', 'uncertain': '证据不足 / 无法判断',
              'not_applicable': '不适用（请在理由中说明）'}
    return [
        question('playback', '是否完整播放并听完本片段？',
                 {'watched_listened': '已完整观看并听音频', 'video_only': '仅看画面 / 未能听音频',
                  'partial': '仅播放部分', 'unavailable': '无法播放'}),
        question('dialogue', '是否保持无额外台词？' if nonverbal else '听到的台词是否与下方完整 spoken_text 一致（无漏句、增句、截断）？', checks),
        question('lipsync', '口型与发声/静默是否一致，无明显错位？', checks),
        question('expression', '表情、视线及动作是否自然，并符合公开可观察线索？', checks),
        question('identity', '人物身份、外观与同场景参考片段是否一致？无其他片段时检查本片段内连续性，并在理由中说明范围。', checks),
        question('context', '人物、场景和表达是否与本轮公开对话及角色相容？', checks),
        question('audio', '音频是否清晰、无异常，且语义/静默与预期一致？', checks),
        question('usability', '本片段最终可用性（不能播放或未听完时选无法判断）',
                 {'usable': '可用', 'revise': '需修订后复核', 'unusable': '不可用', 'uncertain': '无法判断'}),
    ]


def add_current_media(research, site, add):
    """One audit per current content hash; legacy multimodal.json is not current."""
    assets = {}
    for item in research['items']:
        packet = item.get('public_video') or item['public_text']
        for media in item.get('media', []):
            sha = media['sha256']
            checkpoint = media.get('spoken_scope') == 'checkpoint_sentence'
            full_response = media.get('full_public_response') if checkpoint else media.get('spoken_text')
            if checkpoint and (not isinstance(full_response, str) or not full_response
                    or not isinstance(media.get('source_quote'), str) or not media['source_quote']
                    or media['source_quote'] not in full_response or not media.get('node_id')
                    or not isinstance(media.get('spoken_text'), str) or not media['spoken_text']):
                raise ValueError('Invalid checkpoint public source binding: ' + sha)
            entry = assets.setdefault(sha, dict(scene_id=item['scene_id'], media=media,
                context=packet.get('input', {}).get('context'),
                target_character=packet.get('input', {}).get('target_character'), bindings=[], public_turns=[]))
            binding_fields = ['spoken_text', 'spoken_scope', 'full_public_response', 'source_quote', 'node_id']
            if entry['scene_id'] != item['scene_id'] or any(entry['media'].get(k) != media.get(k) for k in binding_fields):
                raise ValueError('Conflicting current-media binding: ' + sha)
            entry['bindings'].append(dict(item_id=item['id'], evidence_ids=media.get('evidence_ids', [])))
            # Match dialogue as well as turn labels: T2 A/B histories share labels.
            matched_ids = set()
            for turn in public_turns(packet):
                if (turn.get('environment_character', turn.get('environment_response', turn.get('current_response'))) == full_response
                        and (not checkpoint or turn['turn_id'] in media.get('evidence_ids', []))):
                    matched_ids.add(turn['turn_id'])
                    projected = select(turn, ['turn_id', 'evaluated_agent', 'environment_character',
                        'environment_response', 'current_response', 'observable_expression', 'public_events'])
                    if projected not in entry['public_turns']:
                        entry['public_turns'].append(projected)
            if checkpoint and (not matched_ids or matched_ids != set(media.get('evidence_ids', []))):
                raise ValueError('Checkpoint full response/turn mismatch: ' + sha)
    for sha, entry in sorted(assets.items(), key=lambda pair: (pair[1]['scene_id'], pair[0])):
        media, sid = entry['media'], entry['scene_id']
        if not media.get('spoken_text') or not entry['public_turns']:
            raise ValueError('Missing current spoken-text/public-cue binding: ' + sha)
        video = copy_video(site, site / 'public' / media['url'].lstrip('/'), sha, media['url'])
        peers = [dict(asset_id=e['media']['asset_id'], url=e['media']['url'], sha256=key)
                 for key, e in assets.items() if e['scene_id'] == sid and key != sha]
        add('media-quality:' + sha, sid, 'media-quality', '当前英文音视频逐片段质量审核',
            dict(note='在盲答结束后审核；同一文件只审核一次。说明具体轮次、时间点与问题；不要把机器生成状态当人工结论。',
                 asset_id=media['asset_id'], spoken_text=media['spoken_text'],
                 context=entry['context'], target_character=entry['target_character'],
                 public_turns=entry['public_turns'], bindings=entry['bindings'], identity_reference_clips=peers,
                 **select(media, ['duration_seconds', 'speech_language', 'spec_sha256', 'method',
                                  'spoken_scope', 'full_public_response', 'source_quote', 'node_id'])),
            quality_questions(), video=video, tracks=['offline_video'])
    return dict(expected_assets=len(assets), review_tasks=len(assets),
                scene_count=len({e['scene_id'] for e in assets.values()}),
                asset_sha256=sorted(assets), human_review='pending')


def bind_t4_event(row, trajectory, turn, event, assets, manifest_path, site):
    """Use the same rendering-input compatibility rule as audit_gate_media.py."""
    from environment.online_video_assets import build_online_asset_request
    asset = assets.get(event.get('media_asset_id'))
    if not asset:
        return None, 'asset_not_registered'
    batch = ROOT / 'data/gpt50/experiment'
    path = batch / asset['video_file']
    if not path.is_file() or not asset.get('video_sha256'):
        return None, 'missing_or_unbound_video'
    if file_sha(path) != asset['video_sha256']:
        raise ValueError('T4 registered video changed: ' + str(path))
    request_path = batch / asset['request_file']
    request = read(request_path)
    scenario_path = ROOT / row['scenario_path']
    scenario = read(scenario_path)
    if scenario['scenario_id'] != row['id'] or request.get('scenario_id') != row['id']:
        raise ValueError('T4 media scene mismatch')
    current = build_online_asset_request(scenario, event['event_family'],
        duration_seconds=request['duration_seconds'], reference_video_file=request.get('reference_video_file'))
    comparison = {key: request.get(key) == current.get(key) for key in (
        'scenario_id', 'event_family', 'identity', 'duration_seconds', 'audio', 'safety_check', 'prompt')}
    if not all(comparison.values()):
        return None, 'rendering_inputs_changed'
    return dict(video=copy_video(site, path, asset['video_sha256']),
                binding=dict(trajectory_sha256=row['trajectory_sha256'], source_path=row['source_path'],
                    source_trajectory_id=trajectory['trajectory_id'], turn_id=turn['turn_id'],
                    media_event_id=event.get('media_event_id'), media_asset_id=event.get('media_asset_id'),
                    video_path=str(path.relative_to(ROOT)), video_sha256=asset['video_sha256'],
                    scenario_path=row['scenario_path'], scenario_sha256=file_sha(scenario_path),
                    manifest_path=str(manifest_path.relative_to(ROOT)), manifest_sha256=file_sha(manifest_path),
                    request_path=str(request_path.relative_to(ROOT)), request_sha256=file_sha(request_path),
                    rendering_comparison=comparison, profile_binding='exact_render_request_compatible'),
                render_request=request), None


def add_t4_reviews(research, site, add):
    manifest_path = ROOT / 'data/gpt50/experiment/multimodal_delivery_v1/online_multimodal/manifest.json'
    assets = {x['media_asset_id']: x for x in read(manifest_path)['requests']}
    coverage = []
    for row in research['t4']:
        original_path = ROOT / row['source_path']
        resolved = row['source_path']
        if not original_path.exists() or file_sha(original_path) != row['trajectory_sha256']:
            # Localization/retries may update active paths. Only the exact frozen
            # content-addressed copy is acceptable for a score-locked sample.
            resolved = 'data/offline_annotation400_en_20261022/sources/' + row['trajectory_sha256'] + '.json'
        path, trajectory = checked_source(resolved, row['trajectory_sha256'])
        row = dict(row, original_source_path=row['source_path'], source_path=str(path.relative_to(ROOT)))
        current_item = next((x for x in research['items'] if x['scene_id'] == row['id']), None)
        if current_item:
            _, _, provenance = current_source(research, current_item)
            if provenance['trajectory_sha256'] == row['trajectory_sha256']:
                checked_source(provenance['scenario_path'], provenance['scenario_sha256'])
                row['scenario_path'] = provenance['scenario_path']
        if trajectory['scenario_id'] != row['id']:
            raise ValueError('T4 trajectory scene mismatch: ' + row['id'])
        turns, gaps, videos, video_tasks = [], [], [], []
        public = {t['turn_id']: t for t in row['packet']['observable_trajectory']}
        for turn in trajectory['turns']:
            event_views = []
            for index, event in enumerate(turn.get('trigger_events', [])):
                bound, reason = bind_t4_event(row, trajectory, turn, event, assets, manifest_path, site)
                view = dict(event, media_availability='available_exact_render_binding' if bound else reason)
                event_views.append(view)
                if not bound:
                    gaps.append(dict(turn_id=turn['turn_id'], media_event_id=event.get('media_event_id'),
                                     media_asset_id=event.get('media_asset_id'), reason=reason))
                    continue
                videos.append(bound['binding'])
                video_task = add('T4-video:' + row['id'] + ':' + turn['turn_id'] + ':' + str(index), row['id'],
                    'T4-video', 'T4 触发节点视频核对',
                    dict(trajectory_id=row['id'], source_trajectory_id=trajectory['trajectory_id'],
                         note='仅在五维评分锁定后展示。此片段与本轨迹节点的渲染请求精确相容；不代表原 text_only 策略看过视频。',
                         public_context=select(row['packet'], ['public_background', 'public_situation', 'target_character']),
                         turn=public[turn['turn_id']], trigger_event=event,
                         state_before=turn.get('state_before'), state_after=turn.get('state_after'),
                         binding=bound['binding'], render_request=bound['render_request']),
                    [question('turn_binding', '片段与所示轮次、触发事件及角色是否对应？'), *quality_questions(nonverbal=True)],
                    video=bound['video'], source_sha256=row['trajectory_sha256'], tracks=['t4'])
                video_tasks.append(video_task)
            turns.append(dict(public[turn['turn_id']], trigger_events=event_views,
                state_before=turn.get('state_before'), state_after=turn.get('state_after'),
                last_trigger_turns=turn.get('environment_snapshot_before', {}).get('last_trigger_turns', {}),
                observable_expression=turn.get('observable_expression'),
                video_availability='no_trigger' if not event_views else
                    ('available' if all(e['media_availability'] == 'available_exact_render_binding' for e in event_views)
                     else 'missing_or_partial')))
        for video_task in video_tasks:
            peers = {t['video']['sha256']: dict(t['video'], asset_id=t['evidence']['binding']['media_asset_id'])
                     for t in video_tasks if t['video']['sha256'] != video_task['video']['sha256']}
            video_task['evidence']['identity_reference_clips'] = list(peers.values())
            video_task['sha256'] = digest({k: v for k, v in video_task.items() if k != 'sha256'})
        add('T4-trigger:' + row['id'], row['id'], 'T4-trigger', 'T4 全轨迹触发时机与频率审核',
            dict(trajectory_id=row['id'], source_trajectory_id=trajectory['trajectory_id'], source_path=row['source_path'],
                 source_sha256=row['trajectory_sha256'], original_source_path=row['original_source_path'],
                 trigger_policy=trajectory.get('environment_provenance', {}).get('multimodal_trigger_policy', {}),
                 note='五维评分已锁定后才可见。逐轮检查触发和无触发位置；请在理由注明误触发、漏触发及应提前/延后的 turn_id。未生成视频不能判断实际画面，不等于无触发或质量合格。',
                 public_context=select(row['packet'], ['public_background', 'public_situation', 'target_character', 'evaluated_agent_role']),
                 ending=trajectory.get('ending'), turns=turns,
                 media_coverage=dict(trigger_events=sum(len(t['trigger_events']) for t in turns),
                     available_exact_bound=len(videos), missing=len(gaps), gaps=gaps)),
            [question('trigger_coverage', '记录是否足以判断哪些轮次触发、哪些未触发？'),
             question('false_positive', '是否有不应触发的节点？（理由逐项列 turn_id）',
                      {'none': '未发现', 'present': '发现误触发', 'uncertain': '无法判断'}),
             question('false_negative', '是否有应触发却未触发的轮次？（理由列 turn_id）',
                      {'none': '未发现', 'present': '发现漏触发', 'uncertain': '无法判断'}),
             question('timing', '触发时间是否合适？', {'appropriate': '合适', 'early': '偏早', 'late': '偏晚', 'mixed': '同时有早/晚', 'uncertain': '无法判断'}),
             question('frequency', '触发频率是否合适？', {'appropriate': '合适', 'excessive': '过多/重复', 'insufficient': '不足', 'mixed': '过多与不足并存', 'uncertain': '无法判断'}),
             question('media_verifiability', '本轨迹实际视频材料的可核验程度',
                      {'complete': '所有触发片段可核验', 'partial': '只有部分片段可核验', 'missing': '无实际视频可核验', 'unverifiable': '无法判断绑定/播放'})],
            source_sha256=row['trajectory_sha256'], tracks=['t4'])
        coverage.append(dict(scene_id=row['id'], trajectory_sha256=row['trajectory_sha256'],
            turn_count=len(turns), trigger_events=sum(len(t['trigger_events']) for t in turns),
            exact_bound_videos=len(videos), missing_media=len(gaps), gaps=gaps, video_bindings=videos))
    return dict(sample_count=len(coverage), trigger_review_tasks=len(coverage),
        trigger_events=sum(x['trigger_events'] for x in coverage),
        video_review_tasks=sum(x['exact_bound_videos'] for x in coverage),
        missing_media=sum(x['missing_media'] for x in coverage),
        scenes_with_actual_media=sum(bool(x['exact_bound_videos']) for x in coverage),
        missing_reason_counts=dict(Counter(g['reason'] for x in coverage for g in x['gaps'])),
        scope='Fixed historical 50-trajectory sample; no new experimental result substituted.', records=coverage)


def build(site):
    research = json.loads(gzip.decompress(base64.b64decode(read(site / 'data/research-server.json')['gzip_base64'])))
    scenes = sorted({x['scene_id'] for x in research['items']})
    review_scenes = set(scenes) | {x['id'] for x in research['t4']}
    trajectories = {v['scenario_id']: (p, v) for p in (SOURCE / 'rollouts').glob('*/trajectory.json') for v in [read(p)]}
    scenarios = {v['scenario_id']: v for p in (SOURCE / 'scenarios').glob('*/*.json') for v in [read(p)]}
    tasks = []

    def add(ident, sid, kind, title, evidence, questions, stage='review', **extra):
        if sid not in review_scenes:
            return
        task = dict(id=ident, scene_id=sid, kind=kind, title=title, stage=stage, evidence=evidence, questions=questions, **extra)
        task['sha256'] = digest(task)
        tasks.append(task)
        return task

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
            source_status = trj.get('gate2_audit_input', {}).get('source_status', 'unknown')
            add('rollout:' + sid, sid, 'rollout', 'Rollout 核对（部分轨迹，仅诊断）' if source_status == 'generation_error' else '完整 rollout 核对',
                dict(note='这是 Gate2 冻结轨迹。请按实际保存的轮次判断；部分轨迹不能当作完整 E2 样本。',
                     **(dict(source_status=source_status) if source_status == 'generation_error' else {}),
                     trajectory_id=trj['trajectory_id'], ending=trj.get('ending'), initial_state=trj['initial_state'],
                     turns=[turn_view(t) for t in trj['turns']]),
                [question('plausible', '对话发展、状态变化与角色行为是否合理？')], source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            item = next(x for x in research['items'] if x['scene_id'] == sid)
            path, trj, provenance = current_source(research, item)
            complete = provenance.get('source_complete') is True
            add('rollout:' + sid, sid, 'rollout', '当前题库 rollout 核对' if complete else '当前题库 rollout 前缀核对（部分轨迹，仅诊断）',
                dict(note='当前题库冻结来源；原生成失败保留。部分轨迹只能审核已保存轮次，不能当作完整 E2 或 T4 样本。',
                     source_status='completed' if complete else 'partial_source_prefix', source_complete=complete,
                     provenance=provenance, trajectory_id=trj['trajectory_id'], ending=trj.get('ending'),
                     initial_state=trj['initial_state'], turns=[turn_view(t) for t in trj['turns']]),
                [question('plausible', '已保存轮次的对话发展、状态变化与角色行为是否合理？')],
                source_sha256=file_sha(path))

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
    # Availability-only human sampling; the machine result denominator keeps all
    # 46 sources and failures. Never select these packets by effect direction.
    recent_reviewed = 0
    final_run = ROOT / 'data/gate2_followup_final_20261022'
    for path in sorted((final_run / 'results').glob('*.json')):
        r = read(path)
        if 'recent3' not in r.get('comparisons', {}) or recent_reviewed >= 10:
            continue
        sid = r['scenario_id']; t = checkpoint(sid, r['checkpoint_turn_id'])
        history = t['environment_snapshot_before'].get('history', [])
        from scripts.run_gate2_followup import recent_snapshot
        recent = recent_snapshot(t['environment_snapshot_before'])['history']
        add('E3-recent3:' + sid, sid, 'E3-recent3', '近三轮历史的影响（补测）',
            dict(sampling='按场景 ID 取前 10 个有完整配对的样本；未按差异大小选样，失败仍留在机器实验分母。',
                 action=t['policy_action'], state_before=t['state_before'], full_history=history, recent3_history=recent,
                 full_output=output(read(final_run / 'outputs' / sid / 'original.json')),
                 recent3_output=output(read(final_run / 'outputs' / sid / 'recent3.json'))),
            [question('plausible', '仅保留最后三轮后，状态差异（或不变）是否有上下文依据？')])
        recent_reviewed += 1
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
    current_media = add_current_media(research, site, add)
    t4_coverage = add_t4_reviews(research, site, add)
    if len({t['id'] for t in tasks}) != len(tasks):
        raise ValueError('Duplicate review task id')
    coverage = dict(format='socialflux_annotation_human_coverage_v1',
        dataset_sha256=research['dataset_sha256'],
        rollout=dict(expected_scenes=scenes, prepared_scenes=[t['scene_id'] for t in tasks if t['kind'] == 'rollout'],
            partial_scenes=[t['scene_id'] for t in tasks if t['kind'] == 'rollout' and
                            t['evidence'].get('source_status') in ('generation_error', 'partial_source_prefix')]),
        current_media=current_media, t4=t4_coverage,
        excluded_from_human_scope=['S1 ablation', 'S2 ablation', 'unrun caption comparison'],
        human_review='pending')
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
    write_registry(site / 'data/gate2-review-server.json', server)
    summary = dict(sha256=bundle['sha256'], dataset_sha256=bundle['dataset_sha256'], counts=dict(Counter(t['kind'] for t in tasks)), scene_count=len(scenes), human_review='pending')
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    coverage['release_sha256'] = bundle['sha256']
    (OUT / 'coverage_manifest.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--compact-registry-only', action='store_true',
                        help='Repack existing registry; do not regenerate or modify frozen materials')
    args = parser.parse_args()
    (compact_existing_registry if args.compact_registry_only else build)(args.site)
