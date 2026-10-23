"""Import participant receipts without overwrites; build paired human/Claude tables."""
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import mean

from evaluation.t4_evaluation import T4_DIMENSIONS, validate_t4_judgment
from web.experiment_tables import make_table
from web.gate2_human import validate_gate2, gate2_coverage

from web.runtime_paths import DATA_ROOT as ROOT
STORE = ROOT / 'data/human_gt_20261022/participant_exports'
RELEASE = ROOT / 'data/human_gt_20261022/release.json'
ANNOTATION400_RELEASE = ROOT / 'data/offline_annotation400_en_20261022/release.json'
ANNOTATION400_FIRST_RELEASE = ROOT / 'data/offline_annotation400_en_20261022/release.first-media.json'
MEDIA_HISTORY = ROOT / 'web/participant_demo/data/research-media-history.json'
CANDIDATE_RELEASE_REGISTRY = ROOT / 'data/human_gt_20261022/candidate-releases.json'
CANDIDATE_REGISTRY_FORMAT = 'socialflux_human_release_registry_v1'
SITE = 'https://socialflux-annotation-demo-20261021.junqiao24.chatgpt.site/'
NAMES = dict(zip(T4_DIMENSIONS, ['目标达成', '状态适应', '风险管理', '恢复', '关系结果']))


@lru_cache(maxsize=4)
def frozen_release(path, mtime):
    return json.loads(Path(path).read_text())


def legacy_release():
    path = ANNOTATION400_RELEASE if RELEASE == ROOT / 'data/human_gt_20261022/release.json' and ANNOTATION400_RELEASE.exists() else RELEASE
    return frozen_release(str(path), path.stat().st_mtime_ns)


def release():
    """A registered candidate becomes current only through explicit activation."""
    legacy = legacy_release()
    active = _candidate_registry().get('active_dataset_sha256')
    if active is None or active == legacy['dataset_sha256']:
        return legacy
    if not isinstance(active, str) or not re.fullmatch(r'[0-9a-f]{64}', active):
        raise ValueError('激活标注数据版本哈希无效')
    for _, candidate in registered_candidate_releases():
        if candidate['dataset_sha256'] == active:
            return candidate
    raise ValueError('激活标注版本未显式注册')


def _candidate_registry():
    if not CANDIDATE_RELEASE_REGISTRY.exists():
        return {'format': CANDIDATE_REGISTRY_FORMAT, 'releases': []}
    registry = json.loads(CANDIDATE_RELEASE_REGISTRY.read_text())
    if (not isinstance(registry, dict) or registry.get('format') != CANDIDATE_REGISTRY_FORMAT
            or not isinstance(registry.get('releases'), list)):
        raise ValueError('候选标注版本注册表格式无效')
    return registry


def _registered_file(entry, field):
    """Read only explicitly registered, byte-pinned JSON inside the data root."""
    relative = entry.get(field + '_path')
    expected = entry.get(field + '_sha256')
    if (not isinstance(relative, str) or not relative
            or not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected)):
        raise ValueError('候选注册缺少文件路径或 SHA256')
    path = (ROOT / relative).resolve()
    if not path.is_relative_to((ROOT / 'data').resolve()) or path.suffix != '.json':
        raise ValueError('候选文件必须位于研究 data 目录内')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('候选注册文件 SHA256 不匹配：' + path.name)
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('dataset_sha256') != entry['dataset_sha256']:
        raise ValueError('候选注册数据版本不匹配')
    return data


def registered_candidate_releases():
    """Registration permits receipt validation; it never promotes a release."""
    registry = _candidate_registry()
    result, seen = [], set()
    for entry in registry['releases']:
        if not isinstance(entry, dict) or not re.fullmatch(r'[0-9a-f]{64}', str(entry.get('dataset_sha256', ''))):
            raise ValueError('候选注册数据哈希无效')
        ident = entry['dataset_sha256']
        if ident in seen:
            raise ValueError('候选注册重复数据版本')
        seen.add(ident)
        data = _registered_file(entry, 'release')
        if not all(isinstance(data.get(key), list) for key in ('items', 'assignments', 't4')):
            raise ValueError('候选标注版本缺少题目、分配或轨迹清单')
        if bool(entry.get('gate2_release_path')) != bool(entry.get('gate2_release_sha256')):
            raise ValueError('候选 Gate2 注册须同时提供路径和文件 SHA256')
        result.append((entry, data))
    return result


def candidate_gate2_packet(dataset_sha256, packet_sha256=None):
    """Resolve a candidate Gate2 packet without writing to production archives."""
    for entry, _ in registered_candidate_releases():
        if entry['dataset_sha256'] != dataset_sha256:
            continue
        if not entry.get('gate2_release_path'):
            return None
        data = _registered_file(entry, 'gate2_release')
        if (not re.fullmatch(r'[0-9a-f]{64}', str(data.get('sha256', '')))
                or not isinstance(data.get('tasks'), list)
                or packet_sha256 is not None and data['sha256'] != packet_sha256):
            raise ValueError('候选环境核对与注册材料版本不匹配')
        return data
    return None


def media_snapshot_releases(current):
    """Restore the same frozen media overlays used by the participant site."""
    if not MEDIA_HISTORY.exists():
        return []
    restored = []
    for snapshot in frozen_release(str(MEDIA_HISTORY), MEDIA_HISTORY.stat().st_mtime_ns):
        if snapshot['source_bank_sha256'] != current.get('source_bank_sha256'):
            continue
        old = {x['id']: x for x in snapshot['items']}
        if len(old) != len(snapshot['items']) or len(old) != len(current['items']):
            raise ValueError('历史媒体快照题量与冻结题库不匹配')
        items = []
        for item in current['items']:
            previous = old.get(item['id'])
            if previous is None or previous['item_sha256'] != item['item_sha256']:
                raise ValueError('历史媒体快照题目哈希不匹配')
            items.append({**item, 'media': previous['media'], 'coverage': previous['coverage'],
                          'public_video': {**item['public_text'], 'modality': 'text+video'} if previous['has_video'] else None})
        restored.append({**current, 'release': snapshot['release'], 'dataset_sha256': snapshot['dataset_sha256'],
                         'assignments': snapshot['assignments'], 'items': items})
    return restored


def receipt_release(dataset_sha256):
    # Legacy receipts remain independently readable after candidate activation,
    # including when a candidate's registration needs repair.
    current = legacy_release()
    if dataset_sha256 == current['dataset_sha256']:
        return current
    for path in (RELEASE, ANNOTATION400_RELEASE, ANNOTATION400_FIRST_RELEASE):
        if not path.exists():continue
        previous = frozen_release(str(path), path.stat().st_mtime_ns)
        if dataset_sha256 == previous['dataset_sha256']:
            return previous
    for previous in media_snapshot_releases(current):
        if dataset_sha256 == previous['dataset_sha256']:
            return previous
    for _, candidate in registered_candidate_releases():
        if dataset_sha256 == candidate['dataset_sha256']:
            return candidate
    raise ValueError('标注版本不在已冻结批次中，请保留原文件并核对版本')


def validate_receipt(value):
    if not isinstance(value, dict) or value.get('format') != 'socialflux_human_gt_v1':
        raise ValueError('请导入新版标注站点下载的本人记录 JSON')
    data = receipt_release(value.get('dataset_sha256'))
    if not re.fullmatch(r'[a-zA-Z0-9-]{8,80}', str(value.get('receipt_id', ''))):
        raise ValueError('回执编号无效')
    if not isinstance(value.get('reviewer_alias'), str) or not 1 <= len(value['reviewer_alias'].strip()) <= 40:
        raise ValueError('标注人编号无效')
    assignment = next((a for a in data['assignments'] if a['id'] == value.get('assignment', {}).get('id')), None)
    if assignment != value.get('assignment'):
        raise ValueError('分配组别与冻结清单不匹配')
    rows = data['t4'] if assignment['track'] == 't4' else data['items']
    field = 'packet_sha256' if assignment['track'] == 't4' else 'item_sha256'
    hashes = {x['id']: x[field] for x in rows if x['id'] in assignment['item_ids']}
    if hashes != value.get('item_hashes'):
        raise ValueError('题目或轨迹哈希不匹配')
    if isinstance(value.get('revision'), bool) or not isinstance(value.get('revision'), int) or value['revision'] < 0:
        raise ValueError('回执版本无效')
    for name in ('blind_responses', 'machine_assisted_gt', 'independent_t4_ratings'):
        if not isinstance(value.get(name), dict) or not set(value[name]) <= hashes.keys():
            raise ValueError('回执包含未分配题目')
    workflow = value.get('workflow')
    if not isinstance(workflow, dict) or workflow.get('phase') not in ('blind', 'gate2', 'gt', 't4_review', 'complete'):
        raise ValueError('标注阶段无效')
    if value.get('status') not in ('submitted', 'in_progress'):
        raise ValueError('提交状态无效')
    complete = value['status'] == 'submitted'
    if complete and (workflow['phase'] != 'complete' or not workflow.get('attestedAt')):
        raise ValueError('最终回执缺少人工确认')
    selected = {x['id']: x for x in rows if x['id'] in hashes}
    if assignment['track'] != 't4':
        if workflow['phase'] == 't4_review':
            raise ValueError('选择题任务不能进入 T4 核对阶段')
        if value['independent_t4_ratings']:
            raise ValueError('T1–3 记录混入 T4 评分')
        if complete and (set(value['machine_assisted_gt']) != hashes.keys() or set(value['blind_responses']) != hashes.keys() or not workflow.get('blindLockedAt')):
            raise ValueError('完整 GT 须先锁定全部盲答，再完成整组审核')
        if value['blind_responses'] != workflow.get('blind', {}) or value['machine_assisted_gt'] != workflow.get('gt', {}):
            raise ValueError('回执中的原始判断与阶段记录不一致')
        for ident, row in value['blind_responses'].items():
            if not isinstance(row, dict) or row.get('answer') not in selected[ident]['public_text']['options']:
                raise ValueError('盲答选项无效')
        for ident, row in value['machine_assisted_gt'].items():
            options = selected[ident]['public_text']['options']
            accepted = row.get('acceptable_answers', [])
            if row.get('decision') not in ('usable', 'revise', 'reject') or not isinstance(accepted, list) or not set(accepted) <= options.keys():
                raise ValueError('GT 质量判断或选项无效')
            if complete and (not row.get('rationale', '').strip() or (row['decision'] != 'reject' and row.get('answer') not in options)
                             or (row['decision'] == 'usable' and (len(accepted) != 1 or row.get('answer') not in accepted))):
                raise ValueError('GT 缺少唯一答案或人工依据')
    else:
        if workflow['phase'] not in ('blind', 't4_review', 'complete'):
            raise ValueError('T4 评分阶段无效')
        if value['blind_responses'] or value['machine_assisted_gt']:
            raise ValueError('T4 记录混入选择题标签')
        if value['independent_t4_ratings'] != workflow.get('ratings', {}):
            raise ValueError('轨迹评分与阶段记录不一致')
        locked_ratings = complete or workflow['phase'] == 't4_review'
        if locked_ratings and set(value['independent_t4_ratings']) != hashes.keys():
            raise ValueError('完整回执须包含整组轨迹')
        for ident, scores in value['independent_t4_ratings'].items():
            valid_ids = {t['turn_id'] for t in selected[ident]['packet']['observable_trajectory']}
            if not isinstance(scores, dict) or (locked_ratings and set(scores) != set(T4_DIMENSIONS)):
                raise ValueError('评分维度不完整')
            for dim, row in scores.items():
                if dim not in T4_DIMENSIONS or not isinstance(row, dict):
                    raise ValueError('评分维度无效')
                score = row.get('score')
                if score is not None and (isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 10):
                    raise ValueError('T4 分数须为 0–10 整数')
                evidence = row.get('evidence_turn_ids', [])
                if not isinstance(evidence, list) or not set(evidence) <= valid_ids or len(evidence) != len(set(evidence)):
                    raise ValueError('评分引用了未观察到的轮次')
                if locked_ratings and (not 1 <= len(evidence) <= 3 or not row.get('rationale', '').strip()
                                 or (score is None and (dim != 'recovery' or row.get('insufficient_evidence') is not True))):
                    raise ValueError('评分依据不完整，或不适用使用错误')
    validate_gate2(value)
    # Imported files are participant-provided, not signed identity/authentication proofs.
    return value


def import_receipt(value):
    value = validate_receipt(value)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    digest = hashlib.sha256(raw).hexdigest()
    STORE.mkdir(parents=True, exist_ok=True)
    path = STORE / f'{value["receipt_id"]}-{value["revision"]}-{digest[:16]}.json'
    if not path.exists():
        path.write_bytes(raw + b'\n')
    return {'ok': True, 'receipt_id': value['receipt_id'], 'sha256': digest,
            'note': '原始导出已留存。按回执去重；同一标注人不会作为两个独立审核人计数。'}


def consensus(labels):
    if len(labels) < 2:
        return None, '待第二人'
    answers = {r.get('answer') for r in labels}
    if any(r.get('decision') != 'usable' or len(r.get('acceptable_answers', [])) != 1 for r in labels) or len(answers) != 1 or None in answers:
        return None, '待裁决'
    return next(iter(answers)), '共识 GT'


def adjudicate(value):
    if not isinstance(value, dict) or value.get('human_attestation') is not True:
        raise ValueError('须由裁决人确认已核对题面、私有证据和分歧')
    data = receipt_release(value['dataset_sha256']) if value.get('dataset_sha256') else release()
    item = next((x for x in data['items'] if x['id'] == value.get('instance_id')), None)
    if item is None or value.get('item_sha256') != item['item_sha256']:
        raise ValueError('裁决题目版本不匹配')
    who = str(value.get('reviewer', '')).strip()
    reason = str(value.get('rationale', '')).strip()
    pending = next((x for x in load_human_gt(data['dataset_sha256'])['disputes'] if x['instance_id'] == item['id']), None)
    if not pending or who in pending['reviewers'] or not 1 <= len(who) <= 40:
        raise ValueError('只有待裁决题可提交，裁决人须不同于已有审核人')
    if not reason or len(reason) > 4000:
        raise ValueError('请填写不超过 4000 字的裁决依据')
    if value.get('decision') not in ('usable', 'reject') or (value['decision'] == 'usable' and value.get('answer') not in item['public_text']['options']):
        raise ValueError('请选择最终答案或剔除题目')
    clean = {'dataset_sha256': data['dataset_sha256'], 'instance_id': item['id'], 'item_sha256': item['item_sha256'], 'reviewer': who, 'rationale': reason,
             'answer': value.get('answer') if value['decision'] == 'usable' else None, 'decision': value['decision'],
             'human_attestation': True, 'reviewers_at_decision': pending['reviewers']}
    raw = json.dumps(clean, ensure_ascii=False, sort_keys=True).encode()
    target = STORE / 'adjudications' / (hashlib.sha256(raw).hexdigest() + '.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw + b'\n')
    return {'ok': True, 'instance_id': item['id'], 'note': '裁决已保存，原始分歧与每个人的判断保持原样。'}


def claude_results(data, directory):
    machine, rows, counts = {}, [], Counter()
    for item in data['t4']:
        original = item['machine']
        path = directory / (item['id'] + '.json')
        result = json.loads(path.read_text()) if path.exists() else None
        candidate = result if result and result.get('status') == 'completed' else original
        status, reason = ('completed', '') if candidate else ('failed', '') if result else ('pending', '')
        if result and result.get('status') == 'failed' and not candidate:
            reason = '; '.join(x['reason'] for x in result.get('diagnostics', []) if x.get('reason')) or result.get('error', '评分失败')
        if candidate:
            try:
                if candidate.get('packet_sha256') != item['packet_sha256']:
                    raise ValueError('评分与冻结公开材料不匹配')
                validate_t4_judgment(candidate['judgment'], [x['turn_id'] for x in item['packet']['observable_trajectory']])
            except (ValueError, KeyError, TypeError) as exc:
                candidate, status, reason = None, 'failed', str(exc)
        machine[item['id']] = candidate
        counts[status] += 1
        rows.append([item['id'], '原有匹配评分' if original else '本次授权补评',
                     {'completed': '有效', 'failed': '失败，未纳入', 'pending': '待完成'}[status],
                     len(result.get('attempts', [])) if result else 0 if not original else '—', reason or '—'])
    return machine, rows, dict(counts)


def load_human_gt(dataset_sha256=None):
    if not RELEASE.exists():
        return {'site': SITE, 'tables': [], 'sessions': 0, 'error': '标注批次尚未准备'}
    current = release()
    data = receipt_release(dataset_sha256) if dataset_sha256 is not None else current
    receipts, errors = {}, []
    try:
        candidates = registered_candidate_releases()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        candidates = []
        errors.append('候选注册不可用：' + str(exc))
    candidate_versions = {entry['dataset_sha256'] for entry, _ in candidates}
    is_candidate = data['dataset_sha256'] in candidate_versions
    for path in sorted(STORE.glob('*.json')):
        try:
            value = validate_receipt(json.loads(path.read_text()))
            key = (value['dataset_sha256'], value['receipt_id'])
            previous = receipts.get(key)
            if previous is None or value['revision'] > previous['revision']:
                receipts[key] = value
            elif value['revision'] == previous['revision'] and value != previous:
                errors.append('同版本回执冲突：' + value['receipt_id'] + ' / ' + value['dataset_sha256'][:12])
                receipts[key]['import_conflict'] = True
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(path.name + ': ' + str(exc))
    compatible_versions={data['dataset_sha256']}
    if not is_candidate:
        compatible_versions.update(previous['dataset_sha256'] for previous in media_snapshot_releases(data))
        if ANNOTATION400_FIRST_RELEASE.exists():
            first=frozen_release(str(ANNOTATION400_FIRST_RELEASE),ANNOTATION400_FIRST_RELEASE.stat().st_mtime_ns)
            if first.get('source_bank_sha256')==data.get('source_bank_sha256'):
                compatible_versions.add(first['dataset_sha256'])
        compatible_versions -= candidate_versions
    selected_receipts = [v for v in receipts.values()
                         if v['dataset_sha256'] in compatible_versions
                         or not is_candidate and v['dataset_sha256'] not in candidate_versions and v['assignment']['track'] == 't4']
    submitted = [v for v in selected_receipts if v['status'] == 'submitted' and v.get('workflow', {}).get('phase') == 'complete'
                 and v['workflow'].get('attestedAt') and not v.get('import_conflict')]
    by_item = defaultdict(lambda: defaultdict(list))
    ratings = defaultdict(lambda: defaultdict(list))
    for record in submitted:
        reviewer = record['reviewer_alias'].strip()
        for ident, label in record['machine_assisted_gt'].items():
            by_item[(ident, record['item_hashes'][ident])][reviewer].append(label)
        for ident, value in record['independent_t4_ratings'].items():
            for dimension in T4_DIMENSIONS:
                row = value.get(dimension, {})
                score = row.get('score')
                if row.get('rationale', '').strip() and (score is None or (isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 10)):
                    ratings[(ident, record['item_hashes'][ident], dimension)][reviewer].append(score)
    # Conflicting repeated judgments by the same alias remain unresolved.
    labels = {}
    for key, reviewers in by_item.items():
        labels[key] = {who: values[0] if all(v == values[0] for v in values) else {'decision': 'conflict', 'answer': None}
                       for who, values in reviewers.items()}
    adjudications = defaultdict(list)
    for path in (STORE / 'adjudications').glob('*.json'):
        row = json.loads(path.read_text())
        matching_dataset = (row.get('dataset_sha256') == data['dataset_sha256']
                            or not is_candidate and not row.get('dataset_sha256'))
        if row.get('human_attestation') and matching_dataset:
            adjudications[(row['instance_id'], row['item_sha256'])].append(row)
    def resolve(key, group, excluding=None):
        results = [x for x in adjudications[key] if x['reviewer'] != excluding and x['reviewer'] not in group]
        if results:
            if len({(x['decision'], x['answer']) for x in results}) > 1:
                return None, '待裁决'
            return results[0]['answer'], '裁决 GT' if results[0]['decision'] == 'usable' else '已剔除'
        return consensus(list(group.values()))
    gt_rows, disputes = [], []
    for item in data['items']:
        group = labels.get((item['id'], item['item_sha256']), {})
        answer, status = resolve((item['id'], item['item_sha256']), group)
        gt_rows.append([item['id'], item['task'], len(group), answer or '—', status])
        if status == '待裁决':
            disputes.append({'dataset_sha256': data['dataset_sha256'], 'instance_id': item['id'], 'item_sha256': item['item_sha256'], 'reviewers': sorted(group),
                             'question': item['public_text']['question'], 'options': item['public_text']['options'], 'judgments': group})
    baseline = defaultdict(lambda: {'n': 0, 'correct': 0, 'people': set()})
    blind_by_reviewer = defaultdict(list)
    current_items = {item['id']: item for item in data['items']}
    for record in submitted:
        if not record['workflow'].get('baselineEligible'):
            continue
        original_items = {item['id']: item for item in receipt_release(record['dataset_sha256'])['items']}
        for ident, row in record['blind_responses'].items():
            if record['assignment']['track'] == 'offline_video':
                # A historical repaired/replaced video is not the current baseline condition.
                media_hashes = lambda item: [(m['asset_id'], m['sha256']) for m in item.get('media', [])]
                if ident not in current_items or media_hashes(original_items[ident]) != media_hashes(current_items[ident]):
                    continue
            blind_by_reviewer[(record['reviewer_alias'].strip(), ident, record['item_hashes'][ident], record['assignment']['track'])].append(row['answer'])
    for (reviewer, ident, item_hash, track), responses in blind_by_reviewer.items():
        if len(set(responses)) != 1:
            continue
        key = (ident, item_hash)
        other = {who: v for who, v in labels.get(key, {}).items() if who != reviewer}
        answer, _ = resolve(key, other, excluding=reviewer)
        if answer:
            task = re.search(r'T[123]', ident).group()
            entry = baseline[(task, track)]
            entry['n'] += 1; entry['correct'] += responses[0] == answer; entry['people'].add(reviewer)
    machine, judge_rows, judge_counts = claude_results(data, RELEASE.parent / 'claude_calibration/results')
    comparison, summary = [], []
    for dimension in T4_DIMENSIONS:
        pairs = []
        for item in data['t4']:
            # One value per distinct reviewer; conflicting repeats excluded, never last-write wins.
            values = [v[0] for v in ratings[(item['id'], item['packet_sha256'], dimension)].values() if len(set(v)) == 1 and v[0] is not None]
            human = mean(values) if values else None
            claude = (machine[item['id']] or {}).get('judgment', {}).get('dimensions', {}).get(dimension, {}).get('score')
            delta = human - claude if human is not None and claude is not None else None
            comparison.append([item['id'], NAMES[dimension], len(values), human, claude, delta])
            if delta is not None:
                pairs.append((human, claude, delta))
        n = len(pairs)
        summary.append([NAMES[dimension], n, mean(x[0] for x in pairs) if n else None, mean(x[1] for x in pairs) if n else None,
                        mean(x[2] for x in pairs) if n else None, mean(abs(x[2]) for x in pairs) if n else None,
                        math.sqrt(mean(x[2] ** 2 for x in pairs)) if n else None])
    sources = ['reports/experiments/2026-10-22_human_gt_release.json', 'data/human_gt_20261022/participant_exports', 'data/human_gt_20261022/claude_calibration']
    def fmt(rows):
        return [[('N/A' if v is None else round(v, 4) if isinstance(v, float) else v) for v in row] for row in rows]
    tables = [make_table('human-gt-coverage', 'T1–3 人工 GT 覆盖与分歧', ['题目', '任务', '审核人数', '答案', '状态'], gt_rows,
        ['共识要求至少两名不同匿名编号的人工审核人一致；任何质量问题或分歧进入裁决。', 'GT 为看过机器候选后的人工判断；原始盲答单独保存。共识不自动替代来源 Gate 准入。'], sources),
      make_table('human-blind-baseline', 'T1–3 人类盲答基线', ['任务', '条件', '人数', '可独立评分答题数', '正确数', '准确率'],
        [[task, mode, len(v['people']), v['n'], v['correct'], round(v['correct'] / v['n'], 4)] for (task, mode), v in sorted(baseline.items())],
        ['仅首次未接触记录；每个人的答案使用排除本人后、另外至少两人一致的 GT，或独立第三人裁决。未形成独立 GT 时不计算准确率。', '同一人同题同条件只计一次；重复且冲突的盲答不纳入。历史音视频回执仅在该题全部素材哈希与当前版本一致时纳入当前条件。匿名编号为自报身份，研究者须维护编号与真实受试者的一一对应。'], sources),
      make_table('human-t4-calibration', 'T4 人工与 Claude 五维校准', ['维度', '配对轨迹 n', '人工均分', 'Claude 均分', '偏差 人工−Claude', 'MAE', 'RMSE'], fmt(summary),
        ['从 200 场景的 182 条完整轨迹中固定分层抽取 50 条（CF150 38、GPT50 12）。未按评分选样。', '同一轨迹、同一公开文字证据、同一评分标准；每条轨迹先对不同人的评分取均值，再与 Claude 配对。', '恢复不适用和缺失机器/人工评分不填零，逐维报告 n；不是 text/video 策略效果估计。'], sources),
      make_table('human-t4-pairs', 'T4 逐轨迹逐维人工−Claude 差值', ['场景', '维度', '有效人工人数', '人工均分', 'Claude', '差值'], fmt(comparison),
        ['空值表示待评或恢复不适用；与汇总表共用同一组配对数据。'], sources),
      make_table('human-t4-judge-status', 'T4 固定样本 Claude 评分覆盖与失败', ['场景', '来源', '状态', '本次请求数', '未纳入原因'], judge_rows,
        ['50 条样本保持冻结；失败不换样、不填零，原始输出与原因保留。', '本次补评每条最多 2 次调用，仅空响应或传输异常按原输入重试；不为提高通过率重采样。',
         '恢复不适用仍须引用 1–3 个代表性轮次；遗漏引用不满足原始评分协议，整条暂不纳入校准。'], sources)]
    if is_candidate:
        try:
            packet = candidate_gate2_packet(data['dataset_sha256'])
            gate2 = gate2_coverage(selected_receipts, data=packet) if packet is not None else None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            gate2 = None
            errors.append('候选环境核对注册不可用：' + str(exc))
    else:
        gate2 = gate2_coverage(selected_receipts)
    if gate2:
        tables.append(make_table('gate2-human-coverage', 'Gate2 随题人工核对覆盖', ['类型', '冻结任务', '已审核任务', '不同人有效判断', '无法判断', '同人重复冲突', '方向/等价/尺度一致率'], gate2['rows'],
            ['同一任务只填一次；E1 方向与 E4 等价性先锁定，之后开放私有材料及其他核对。音视频质量按唯一媒体审核；T4 先锁定评分，再核对触发与视频。', '只计最终提交、材料哈希匹配的记录；按任务和匿名编号去重，冲突重复排除。E1/E4 排除自报既往接触及重复场景。自报编号仍需研究者核实身份。',
             '一致率仅展示 E1 人机方向、E4 人工等价、E9 尺度先验；无法判断不填零。此表不自动触发 Gate2 正式通过。'], ['data/gate2_annotation_20261022/release.json', 'data/human_gt_20261022/participant_exports']))
        tables.append(make_table('gate2-human-review-status', '人工核对逐任务覆盖与原始判断分布', ['任务', '类型', '场景', '有效审核人数', '覆盖状态', '选项分布'], gate2['status_rows'],
            ['至少两人已核对只表示覆盖，不代表素材合格或实验通过；需结合原始判断与依据决定修订、剔除或准入。',
             '分歧、无法判断及同人冲突须复核。旧版本仅在逐任务材料哈希相同时计入当前任务；旧记录不会补出新增审核。'],
            ['data/gate2_annotation_20261022/release.json', 'data/human_gt_20261022/participant_exports']))
    legacy = legacy_release()
    cohort_data = {legacy['dataset_sha256']: legacy, current['dataset_sha256']: current, data['dataset_sha256']: data}
    cohort_data.update({candidate['dataset_sha256']: candidate for _, candidate in candidates})
    for record in receipts.values():
        if record['dataset_sha256'] not in cohort_data:
            cohort_data[record['dataset_sha256']] = receipt_release(record['dataset_sha256'])
    cohorts = []
    for ident, cohort in cohort_data.items():
        records = [r for r in receipts.values() if r['dataset_sha256'] == ident]
        cohorts.append({'dataset_sha256': ident, 'release': cohort['release'],
                        'registered_candidate': ident in candidate_versions, 'current': ident == current['dataset_sha256'],
                        'selected': ident == data['dataset_sha256'], 'sessions': len(records),
                        'submitted': sum(r['status'] == 'submitted' and r['workflow']['phase'] == 'complete'
                                         and bool(r['workflow'].get('attestedAt')) and not r.get('import_conflict') for r in records)})
    tables.insert(0, make_table('human-release-cohorts', '标注版本与独立统计范围',
        ['版本', '数据 SHA256', '范围', '已导入会话', '最终提交'],
        [[c['release'], c['dataset_sha256'], '当前（显式激活）' if c['current'] and c['registered_candidate'] else '当前' if c['current'] else
          '候选（独立统计）' if c['registered_candidate'] else '历史',
          c['sessions'], c['submitted']] for c in cohorts],
        ['候选注册仅允许核验回执，不表示上线或已取得人工结果；零记录不生成 GT 或基线。',
         '下列表格的选择版本：' + data['dataset_sha256'] + '。短片候选与旧版的盲答、GT、T4及裁决分别统计；文字相同也不自动跨候选合并。'], sources))
    return {'gate2': gate2, 'site': SITE, 'release': data['release'], 'dataset_sha256': data['dataset_sha256'],
        'current_dataset_sha256': current['dataset_sha256'], 'registered_candidate': is_candidate, 'dataset_cohorts': cohorts,
        'sessions': len(selected_receipts), 'total_sessions': len(receipts), 'submitted': len(submitted), 'sampling': data['sampling'],
        'claude_available': sum(x is not None for x in machine.values()), 'claude_status': judge_counts,
        'gt_consensus': sum(x[-1] in ('共识 GT', '裁决 GT') for x in gt_rows),
        'gt_disputed': len(disputes), 'disputes': disputes, 'tables': tables, 'errors': errors}
