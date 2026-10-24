"""Publish aggregate counts only; never publish sessions, answers, or recovery codes."""
import json
from pathlib import Path
from web.experiment_hub import load_hub


def build(output):
    hub = load_hub()
    human = hub['human_annotation']
    allowed_tables = {'dataset-overview', 'offline-counts', 't4-counts', 'gate-overview',
                      'gate2-methods', 'gate2-results', 'offline-results', 'human-release-cohorts'}
    snapshot = {key: hub[key] for key in ('schema', 'generated_at', 'categories', 'statuses')}
    snapshot.update(public_snapshot=True, records=[], reports=[], live=None,
                    matrix=None, paper_tables=[t for t in hub['paper_tables'] if t['id'] in allowed_tables],
                    catalog_errors=[], live_error=None,
                    scope='公开页面展示已发布汇总；登录后查看实时报告和研究记录。')
    snapshot['human_annotation'] = {key: human[key] for key in (
        'release', 'sessions', 'total_sessions', 'submitted', 'gt_consensus', 'gt_disputed',
        'claude_available', 'claude_status', 'dataset_cohorts')}
    snapshot['human_annotation'].update(disputes=[], tables=[], errors=[])
    # Counts only: no per-question identifiers, reviewer aliases or free-text answers.
    snapshot['live'] = {'offline': {k: v for k, v in hub['live']['offline'].items()
        if k in {'item_count', 'scenario_count', 'human_labeled', 'formal_admitted', 't2_replay_pending_scenes'}},
        'gates': [], 't4_runs': []}
    Path(output).write_text('window.SOCIALFLUX_PUBLIC_SNAPSHOT = ' + json.dumps(snapshot, ensure_ascii=False) + ';\n')

if __name__ == '__main__':
    import sys
    build(sys.argv[1])
