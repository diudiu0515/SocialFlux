"""Current source population and offline inventory, without private evidence."""
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from evaluation.t4_evaluation import assert_t4_trajectory

GPT_BASE = Path('data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary')
GPT_SCENARIOS = GPT_BASE / 'unified_current_trust_v1_gpt50'
GPT_ACTIVE = GPT_BASE / 'unified_current_trust_v1_gpt50_active'
CF_SCENARIOS = Path('data/claude150_v1/scenarios_state_v3')
CF_ROLLOUTS = Path('data/claude150_v1/state_v3_validation/full_rollout_state_repair_v31/sources')
BANK = Path('tasks/examples/offline_scenarios_v2')
ANNOTATION_BANK = Path('data/offline_annotation400_en_20261022')
FAILED_STATUSES = {'call_or_validation_failure', 'generation_error', 'failed'}


@lru_cache(maxsize=512)
def inspect_trajectory(path, modified_ns, size, scenario_id):
    """Cache only small public counts; revalidate whenever the artifact changes."""
    value = json.loads(Path(path).read_text())
    if value.get('scenario_id') != scenario_id:
        return 'invalid', '场景编号不匹配'
    if value.get('generation_error'):
        return 'failed', '生成失败，保留的前缀不计完整 rollout'
    try:
        assert_t4_trajectory(value)
    except (ValueError, TypeError, AttributeError):
        return 'invalid', '轨迹轮次或终止标记未通过完整性校验'
    return 'usable', ''


def summarize_offline(items, variants):
    by_id = {x['instance_id']: x for x in items}
    if len(by_id) != len(items):
        raise ValueError('duplicate offline instance_id')
    pairs = defaultdict(Counter)
    for item in variants:
        identity = item.get('metadata', {}).get('modality_pair_id')
        if identity in by_id:
            pairs[identity][item.get('modality')] += 1
    paired_ids = {key for key, counts in pairs.items()
                  if counts['text'] == 1 and counts['text+video'] == 1}
    def count(rows):
        difficulties = Counter(x.get('analysis', {}).get('design_difficulty') for x in rows)
        return dict(total=len(rows), ordinary=difficulties['ordinary'], hard=difficulties['hard'],
                    unknown=len(rows) - difficulties['ordinary'] - difficulties['hard'],
                    scenarios=len({x['story_id'] for x in rows}),
                    pairs=sum(x['instance_id'] in paired_ids for x in rows))
    return dict(count(items), tasks={task: count([x for x in items if x['task'] == task])
                                    for task in ('T1', 'T2', 'T3')},
                cohorts={family: count([x for x in items if x['story_id'].startswith(family + '_')])
                         for family in ('GPT50', 'CF150')})


def load_dataset_counts(root):
    root = Path(root)
    errors, sources, cohorts, candidates = [], [], [], []
    def read(relative, lines=False):
        path = root / relative
        try:
            raw = path.read_bytes()
            value = ([json.loads(line) for line in raw.splitlines() if line.strip()]
                     if lines else json.loads(raw))
            sources.append({'path': str(relative), 'sha256': hashlib.sha256(raw).hexdigest()})
            return value
        except (OSError, ValueError) as exc:
            errors.append({'path': str(relative), 'error': type(exc).__name__})
            return None

    for family, manifest_path in [('GPT50', GPT_SCENARIOS / 'manifest.json'),
                                  ('CF150', CF_SCENARIOS / 'manifest.json')]:
        manifest = read(manifest_path)
        if manifest is None:
            cohorts.append(dict(id=family, scenarios=None, usable=None, failed=None, invalid=None,
                                pending=None, t4hard_candidates=None))
            continue
        members = manifest.get('cases' if family == 'GPT50' else 'results', [])
        seen, counts = set(), Counter()
        for index, member in enumerate(members):
            identity = member['scenario_id']
            if identity in seen:
                continue
            seen.add(identity)
            ordinal = int(identity.rsplit('_', 1)[-1])
            scenario = (Path(member['candidate']) if family == 'GPT50' else
                        CF_SCENARIOS / f'scenario_{ordinal:03}/scenario_{ordinal:03}.json')
            directory = (GPT_ACTIVE / f'{index:02}_{identity}_gpt' if family == 'GPT50' else
                         CF_ROLLOUTS / f'scenario_{ordinal:03}')
            path = root / directory / 'trajectory.json'
            reason = ''
            try:
                scenario_data = json.loads((root / scenario).read_text())
                if scenario_data.get('scenario_id') != identity:
                    raise ValueError('scenario identity mismatch')
                counts['scenarios'] += 1
                if path.exists():
                    stat = path.stat()
                    state, reason = inspect_trajectory(str(path), stat.st_mtime_ns, stat.st_size, identity)
                else:
                    result_path = root / directory / 'result.json'
                    result = json.loads(result_path.read_text()) if result_path.exists() else {}
                    state = 'failed' if result.get('status') in FAILED_STATUSES else 'pending'
                    reason = '生成失败，未形成完整 rollout' if state == 'failed' else '尚无完整 rollout'
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                state, reason = 'unreadable', '来源暂不可读，未计为失败'
                errors.append({'path': str(directory), 'error': type(exc).__name__})
            counts[state] += 1
            if state in ('failed', 'invalid'):
                candidates.append(dict(scenario_id=identity, cohort=family, status=state, reason=reason,
                                       source=str(directory / 'trajectory.json')))
        cohorts.append(dict(id=family, expected=len(seen), **{key: counts[key] for key in
            ('scenarios', 'usable', 'failed', 'invalid', 'pending', 'unreadable')},
            t4hard_candidates=counts['failed'] + counts['invalid']))

    # The released annotation bank supersedes the 300-question development bank.
    # Once its manifest exists, an unreadable or stale release is an error,
    # rather than a silent return to the older question count.
    bank = ANNOTATION_BANK if (root / ANNOTATION_BANK / 'manifest.json').exists() else BANK
    manifest = read(bank / 'manifest.json') if bank == ANNOTATION_BANK else None
    items = read(bank / 'items.jsonl', lines=True)
    variants = read(bank / 'paired.items.jsonl', lines=True)
    pairing = read(bank / 'pairing_report.json')
    offline = None
    if items is not None:
        bank_hash = next(s['sha256'] for s in sources if s['path'] == str(bank / 'items.jsonl'))
        if bank == ANNOTATION_BANK and (not manifest or manifest.get('items_sha256') != bank_hash):
            errors.append({'path': str(bank / 'manifest.json'), 'error': 'AnnotationBankHashMismatch'})
            items = None
    if items is not None:
        offline = summarize_offline(items, variants or [])
        offline['bank_path'] = str(bank)
        offline['release'] = (manifest or {}).get('release')
        if variants is None or not pairing or pairing.get('items_sha256') != bank_hash:
            offline['pairs'] = None
            for row in [*offline['tasks'].values(), *offline['cohorts'].values()]:
                row['pairs'] = None
            errors.append({'path': str(bank / 'pairing_report.json'), 'error': 'PairingSourceUnavailableOrChanged'})
        offline['media_coverage'] = (pairing or {}).get('coverage_counts', {})
    return dict(generated_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                cohorts=cohorts, offline=offline, t4hard_candidates=candidates,
                sources=sources, read_errors=errors)
