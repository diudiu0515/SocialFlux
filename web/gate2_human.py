"""Validate and summarize scene-bound human reviews from annotation receipts."""
from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path

from web.runtime_paths import DATA_ROOT as ROOT
RELEASE = ROOT / 'data/gate2_annotation_20261022/release.json'


@lru_cache(maxsize=8)
def frozen_packet(path, mtime):
    return json.loads(Path(path).read_text())


def read_packet(path):
    return frozen_packet(str(path), path.stat().st_mtime_ns)


def receipt_packet(dataset_sha256, packet_sha256):
    """Resolve legacy archives or an explicitly registered candidate packet."""
    if (not isinstance(packet_sha256, str) or len(packet_sha256) != 64
            or any(c not in '0123456789abcdef' for c in packet_sha256)):
        raise ValueError('环境核对版本哈希无效')
    if RELEASE.exists():
        current = read_packet(RELEASE)
        if packet_sha256 == current['sha256'] and dataset_sha256 == current['dataset_sha256']:
            return current
    archive = RELEASE.parent / 'versions' / (packet_sha256 + '.json')
    if archive.exists():
        data = read_packet(archive)
        if packet_sha256 == data['sha256'] and dataset_sha256 == data['dataset_sha256']:
            return data
    # Deferred import avoids a cycle: human_gt owns the explicit file registry.
    from web.human_gt import candidate_gate2_packet
    candidate = candidate_gate2_packet(dataset_sha256, packet_sha256)
    if candidate is not None:
        return candidate
    raise ValueError('环境核对版本未冻结，或与标注数据版本不匹配')


def assigned_tasks(data, assignment):
    """Use the same scene/track boundary as the participant site."""
    track = assignment['track']
    scenes = set(assignment['scene_ids'])
    result = {}
    for task in data['tasks']:
        if task['scene_id'] not in scenes:
            continue
        tracks = task.get('tracks')
        if tracks is not None:
            eligible = track in tracks
        elif task['kind'].startswith('T4-'):
            eligible = track == 't4'
        elif task['kind'] == 'media-quality':
            eligible = track == 'offline_video'
        else:
            eligible = track != 't4'
        if eligible:
            result[task['id']] = task
    return result


def review_issue(task, row):
    """Reject the same contradictory final judgments as the participant form."""
    values = row['values']
    if task['kind'] in ('media-quality', 'T4-video') and values.get('usability') == 'usable':
        if values.get('playback') != 'watched_listened':
            return '标记媒体可用前须完整观看并听完'
        if any(v in ('no', 'uncertain') for k, v in values.items() if k not in ('playback', 'usability')):
            return '存在缺陷或未确认项目的媒体不能同时标记可用'
    if task['kind'] == 'T4-trigger':
        coverage = task.get('evidence', {}).get('media_coverage')
        if coverage:
            if values.get('media_verifiability') == 'complete' and coverage.get('missing', 0) > 0:
                return '存在缺失片段，不能标记全部触发视频可核验'
            if values.get('media_verifiability') == 'partial' and not coverage.get('available_exact_bound'):
                return '没有精确绑定的成品视频，不能标记部分视频可核验'
    return ''


def validate_gate2(value):
    workflow = value.get('workflow', {})
    state = workflow.get('gate2')
    exported = value.get('gate2_human_review')
    if state is None:
        if exported is not None or workflow.get('phase') == 't4_review':
            raise ValueError('环境核对导出与阶段记录不一致')
        return
    if not isinstance(state, dict) or not isinstance(exported, dict):
        raise ValueError('环境核对记录格式无效')
    data = receipt_packet(value['dataset_sha256'], state.get('packet_sha256'))
    tasks = assigned_tasks(data, value['assignment'])
    sequence = workflow.get('sceneSequence')
    if sequence is not None:
        # Progressive receipts intentionally omit hashes for unopened scenes.
        # Validate the exact visible prefix, then apply the ordinary stage checks
        # separately to each completed scene and the current scene.
        scenes = sequence.get('scenes') if isinstance(sequence, dict) else None
        index = sequence.get('index') if isinstance(sequence, dict) else None
        complete = value['status'] == 'submitted'
        if (not isinstance(scenes, list) or not scenes
                or any(not isinstance(scene, dict) for scene in scenes)
                or [scene.get('id') for scene in scenes] != value['assignment']['scene_ids']
                or sequence.get('version') != 1 or type(index) is not int
                or not 0 <= index <= len(scenes)
                or complete != (index == len(scenes))
                or complete != (workflow.get('phase') == 'complete')):
            raise ValueError('逐场景进度与分配清单不一致')
        completed = sequence.get('completed')
        if (not isinstance(completed, dict)
                or set(completed) != {scene['id'] for scene in scenes[:index]}
                or any(not isinstance(lock, dict) or not lock.get('blindLockedAt')
                       or not lock.get('submittedAt') for lock in completed.values())):
            raise ValueError('逐场景完成记录不一致')
        visible = {scene['id'] for scene in scenes[:index + 1]}
        tasks = {key: task for key, task in tasks.items() if task['scene_id'] in visible}
    answers = state.get('answers')
    if not isinstance(answers, dict) or not set(answers) <= tasks.keys():
        raise ValueError('环境核对包含未分配任务')
    if (exported.get('packet_sha256') != data['sha256'] or exported.get('answers') != answers
            or exported.get('task_hashes') != {k: t['sha256'] for k, t in tasks.items()}
            or exported.get('independent_locked_at') != state.get('independentLockedAt')):
        raise ValueError('环境核对哈希或原始判断不一致')
    if sequence is not None:
        for scene in sequence['scenes'][:sequence['index'] + 1]:
            ident = scene['id']
            finished = ident in sequence['completed']
            selected = {key: task for key, task in tasks.items() if task['scene_id'] == ident}
            scoped_state = {**state, 'answers': {key: row for key, row in answers.items() if key in selected}}
            scoped_workflow = {key: row for key, row in workflow.items() if key != 'sceneSequence'}
            if finished:
                lock = sequence['completed'][ident]
                scoped_state['independentLockedAt'] = lock.get('independentLockedAt')
                scoped_workflow.update(phase='complete', attestedAt=lock['submittedAt'])
            scoped_workflow['gate2'] = scoped_state
            validate_gate2({**value, 'status': 'submitted' if finished else 'in_progress',
                           'assignment': {**value['assignment'], 'scene_ids': [ident]},
                           'workflow': scoped_workflow,
                           'gate2_human_review': {**exported, 'answers': scoped_state['answers'],
                               'task_hashes': {key: task['sha256'] for key, task in selected.items()},
                               'independent_locked_at': scoped_state.get('independentLockedAt')}})
        return
    complete = value['status'] == 'submitted'
    t4 = value['assignment']['track'] == 't4'
    locked = not t4 and workflow['phase'] in ('gt', 'complete')
    independent = {k for k, t in tasks.items() if t['stage'] == 'independent'}
    if t4:
        if workflow['phase'] not in ('blind', 't4_review', 'complete'):
            raise ValueError('T4 评分阶段无效')
        if workflow['phase'] in ('t4_review', 'complete') and not workflow.get('ratingsLockedAt'):
            raise ValueError('须先锁定独立 T4 评分再核对触发与视频')
        if workflow['phase'] == 'blind' and answers:
            raise ValueError('T4 评分锁定前不能填写触发与视频核对')
    if locked and (not state.get('independentLockedAt') or not independent <= answers.keys()):
        raise ValueError('缺少锁定的独立环境判断')
    if complete and set(answers) != tasks.keys():
        raise ValueError('环境核对尚未完成')
    if (workflow['phase'] == 'blind' and answers) or (workflow['phase'] == 'gate2' and not set(answers) <= independent):
        raise ValueError('环境核对包含未开放阶段的判断')
    for ident, row in answers.items():
        questions = {q['id']: q for q in tasks[ident]['questions']}
        if not isinstance(row, dict) or not isinstance(row.get('values'), dict) or not isinstance(row.get('rationale'), str) or len(row['rationale']) > 4000:
            raise ValueError('环境核对依据格式无效')
        if not set(row['values']) <= questions.keys() or any(not isinstance(v, str) or v and v not in questions[k]['choices'] for k, v in row['values'].items()):
            raise ValueError('环境核对选项无效')
        if (complete or locked and ident in independent) and (not row['rationale'].strip() or set(row['values']) != questions.keys() or not all(row['values'].values())):
            raise ValueError('环境核对缺少判断或依据')
        if complete:
            issue = review_issue(tasks[ident], row)
            if issue:
                raise ValueError(issue)


def gate2_coverage(receipts, data=None):
    if data is None:
        if not RELEASE.exists():
            return None
        data = read_packet(RELEASE)
    tasks = {t['id']: t for t in data['tasks']}
    groups = defaultdict(lambda: defaultdict(list))
    for record in receipts:
        if (record.get('dataset_sha256') != data['dataset_sha256']
                or record.get('status') != 'submitted' or record.get('import_conflict')
                or record.get('workflow', {}).get('phase') != 'complete' or not record['workflow'].get('attestedAt')):
            continue
        review = record.get('gate2_human_review')
        if not review:
            continue
        try:
            validate_gate2(record)
        except (ValueError, KeyError, TypeError):
            continue
        for ident, answer in review['answers'].items():
            if ident not in tasks or review.get('task_hashes', {}).get(ident) != tasks[ident]['sha256']:
                continue
            if tasks[ident]['stage'] == 'independent' and not record['workflow'].get('baselineEligible'):
                continue
            groups[ident][record['reviewer_alias'].strip()].append(answer)
    rows, status_rows = [], []
    two_reviewers = 0
    for kind in dict.fromkeys(t['kind'] for t in tasks.values()):
        selected = [t for t in tasks.values() if t['kind'] == kind]
        reviewed, votes, uncertain, conflicts, numerator, denominator = 0, 0, 0, 0, 0, 0
        for task in selected:
            valid = []
            task_conflicts = 0
            for values in groups[task['id']].values():
                if all(v == values[0] for v in values):
                    valid.append(values[0])
                else:
                    conflicts += 1; task_conflicts += 1
            reviewed += bool(valid); votes += len(valid)
            distributions = defaultdict(lambda: defaultdict(int))
            for answer in valid:
                for key, vote in answer['values'].items():
                    distributions[key][vote] += 1
            disagreement = any(len(votes_for_question) > 1 for votes_for_question in distributions.values())
            unsure = any(vote in ('uncertain', 'unavailable', 'unverifiable') for votes_for_question in distributions.values() for vote in votes_for_question)
            two_reviewers += len(valid) >= 2
            status = ('待复核：同人重复冲突' if task_conflicts else '待审核' if not valid else '待第二人' if len(valid) < 2 else
                      '待复核：分歧或无法判断' if disagreement or unsure else '至少两人已核对（非准入结论）')
            summary = '; '.join(f'{key}: ' + ', '.join(f'{vote}={count}' for vote, count in sorted(votes_for_question.items()))
                                for key, votes_for_question in distributions.items())
            status_rows.append([task['id'], kind, task['scene_id'], len(valid), status, summary or '—'])
            for answer in valid:
                uncertain += any(v in ('uncertain', 'unavailable', 'unverifiable') for v in answer['values'].values())
                if kind == 'E1':
                    for key, vote in answer['values'].items():
                        if vote != 'uncertain':
                            denominator += 1; numerator += vote == task['machine'][key]
                elif kind == 'E4':
                    vote = answer['values']['equivalent']
                    if vote != 'uncertain':
                        denominator += 1; numerator += vote == 'yes'
                elif kind == 'E9':
                    vote = answer['values']['observed_timescale']
                    if vote != 'uncertain':
                        denominator += 1; numerator += vote == task['machine']['expected_timescale_prior']
        metric = f'{numerator}/{denominator} ({100*numerator/denominator:.1f}%)' if denominator else 'N/A'
        rows.append([kind, len(selected), reviewed, votes, uncertain, conflicts, metric])
    return dict(packet_sha256=data['sha256'], rows=rows, status_rows=status_rows, total=len(tasks),
                reviewed=sum(r[2] for r in rows), two_reviewers=two_reviewers, formal_admission=False)
