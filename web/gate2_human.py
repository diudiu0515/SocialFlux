"""Validate and summarize scene-bound human reviews from annotation receipts."""
from collections import defaultdict
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'data/gate2_annotation_20261022/release.json'


def validate_gate2(value):
    workflow = value.get('workflow', {})
    state = workflow.get('gate2')
    exported = value.get('gate2_human_review')
    if state is None:
        if exported is not None:
            raise ValueError('环境核对导出与阶段记录不一致')
        return
    if value['assignment']['track'] == 't4' or not isinstance(state, dict) or not isinstance(exported, dict):
        raise ValueError('环境核对记录格式无效')
    data = json.loads(RELEASE.read_text())
    if state.get('packet_sha256') != data['sha256']:
        digest = state.get('packet_sha256', '')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('环境核对版本哈希无效')
        archive = RELEASE.parent / 'versions' / (digest + '.json')
        if not archive.exists():
            raise ValueError('环境核对版本未冻结')
        data = json.loads(archive.read_text())
    if state.get('packet_sha256') != data['sha256'] or value['dataset_sha256'] != data['dataset_sha256']:
        raise ValueError('环境核对与冻结材料版本不匹配')
    tasks = {t['id']: t for t in data['tasks'] if t['scene_id'] in value['assignment']['scene_ids']}
    answers = state.get('answers')
    if not isinstance(answers, dict) or not set(answers) <= tasks.keys():
        raise ValueError('环境核对包含未分配任务')
    if (exported.get('packet_sha256') != data['sha256'] or exported.get('answers') != answers
            or exported.get('task_hashes') != {k: t['sha256'] for k, t in tasks.items()}
            or exported.get('independent_locked_at') != state.get('independentLockedAt')):
        raise ValueError('环境核对哈希或原始判断不一致')
    complete = value['status'] == 'submitted'
    locked = workflow['phase'] in ('gt', 'complete')
    independent = {k for k, t in tasks.items() if t['stage'] == 'independent'}
    if locked and (not state.get('independentLockedAt') or not independent <= answers.keys()):
        raise ValueError('缺少锁定的独立环境判断')
    if complete and set(answers) != tasks.keys():
        raise ValueError('环境核对尚未完成')
    if workflow['phase'] == 'blind' and answers or workflow['phase'] == 'gate2' and not set(answers) <= independent:
        raise ValueError('环境核对包含未开放阶段的判断')
    for ident, row in answers.items():
        questions = {q['id']: q for q in tasks[ident]['questions']}
        if not isinstance(row, dict) or not isinstance(row.get('values'), dict) or not isinstance(row.get('rationale'), str) or len(row['rationale']) > 4000:
            raise ValueError('环境核对依据格式无效')
        if not set(row['values']) <= questions.keys() or any(not isinstance(v, str) or v and v not in questions[k]['choices'] for k, v in row['values'].items()):
            raise ValueError('环境核对选项无效')
        if (complete or locked and ident in independent) and (not row['rationale'].strip() or set(row['values']) != questions.keys() or not all(row['values'].values())):
            raise ValueError('环境核对缺少判断或依据')


def gate2_coverage(receipts):
    if not RELEASE.exists():
        return None
    data = json.loads(RELEASE.read_text())
    tasks = {t['id']: t for t in data['tasks']}
    groups = defaultdict(lambda: defaultdict(list))
    for record in receipts:
        if record.get('status') != 'submitted' or record.get('import_conflict') or not record.get('workflow', {}).get('attestedAt'):
            continue
        review = record.get('gate2_human_review')
        if not review:
            continue
        for ident, answer in review['answers'].items():
            if ident not in tasks or review.get('task_hashes', {}).get(ident) != tasks[ident]['sha256']:
                continue
            if tasks[ident]['stage'] == 'independent' and not record['workflow'].get('baselineEligible'):
                continue
            groups[ident][record['reviewer_alias']].append(answer)
    rows = []
    for kind in dict.fromkeys(t['kind'] for t in tasks.values()):
        selected = [t for t in tasks.values() if t['kind'] == kind]
        reviewed, votes, uncertain, conflicts, numerator, denominator = 0, 0, 0, 0, 0, 0
        for task in selected:
            valid = []
            for values in groups[task['id']].values():
                if all(v == values[0] for v in values):
                    valid.append(values[0])
                else:
                    conflicts += 1
            reviewed += bool(valid); votes += len(valid)
            for answer in valid:
                uncertain += any(v in ('uncertain', 'unavailable') for v in answer['values'].values())
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
    return dict(packet_sha256=data['sha256'], rows=rows, total=len(tasks), reviewed=sum(r[2] for r in rows), formal_admission=False)
