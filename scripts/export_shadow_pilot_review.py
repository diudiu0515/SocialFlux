#!/usr/bin/env python3
"""Read-only semantic inputs: export readable evidence and plots, never rerun models."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from environment.delta_mapper import flatten_state

BASE = ROOT / 'data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/observed_evidence_v6_shadow_six'
WORDS = {'ordinary_new_evidence': '普通新增', 'decisive_new_evidence': '决定性新增',
         'no_relevant_evidence': '无相关证据', 'repeated_evidence_only': '重复证据'}


def load(path):
    return json.loads(path.read_text())


def export_one(directory, plan):
    source = next((directory / name for name in ['trajectory.json', 'partial_trajectory.json', 'checkpoint.json']
                   if (directory / name).exists()), None)
    if source is None:
        return {'case': directory.name, 'status': 'not_yet_available', 'turns': 0}
    trajectory = load(source)
    turns = trajectory.get('turns', [])
    result = load(directory / 'result.json') if (directory / 'result.json').exists() else {'status': 'running'}
    lines = [directory.name, '仅供人工审核，未进入正式数据。',
             '记录状态：' + result['status'], '数据来源：' + source.name,
             '初始背景（被测方可见）：' + plan['initial_observation']['background'], '']
    dialogue = lines.copy()
    records, findings = [], []
    for turn in turns:
        dialogue += ['=== ' + turn['turn_id'] + ' ===', '被测方：' + turn['policy_action']['text'],
                     '环境方：' + turn['environment_response'], '']
        lines += ['=== ' + turn['turn_id'] + ' ===', '被测方：' + turn['policy_action']['text'],
                  '环境方：' + turn['environment_response'], '', '状态证据（不变也完整保留）：']
        for kind in ('state', 'dynamics'):
            before = flatten_state(turn.get(kind + '_before', {}))
            after = flatten_state(turn.get(kind + '_after', {}))
            delta = flatten_state(turn.get('numeric_' + kind + '_delta', {}))
            judgments = {j['variable']: j for j in turn.get(kind + '_judgments', [])}
            for variable, value in before.items():
                judgment = judgments.get(variable, {})
                change = after[variable] - value
                if delta.get(variable) != change:
                    findings.append(turn['turn_id'] + ':' + variable + ':numeric_delta_mismatch')
                if judgment.get('judgment') in ('no_relevant_evidence', 'repeated_evidence_only') and change:
                    findings.append(turn['turn_id'] + ':' + variable + ':no_new_evidence_but_changed')
                records.append({'turn': turn['turn_id'], 'kind': kind, 'variable': variable,
                                'before': value, 'after': after[variable], 'delta': change,
                                'judgment': judgment.get('judgment', 'missing'),
                                'evidence': judgment.get('evidence_span', ''),
                                'rationale': judgment.get('rationale', '')})
                lines += [f"{kind}/{variable}: {value} → {after[variable]} ({change:+g})；"
                          + WORDS.get(judgment.get('judgment'), '判断缺失'),
                          '  引用：' + judgment.get('evidence_span', ''),
                          '  理由：' + judgment.get('rationale', '')]
        for item in turn.get('calibration', {}).get('state_impacts', []):
            if not item.get('selected'):
                lines.append('校准未选中：' + json.dumps(item, ensure_ascii=False))
        rejected = turn.get('rejected_policy_action_attempts', [])
        if rejected:
            lines.append('本轮有被拒绝的动作草稿，完整记录保留在原轨迹；次数：' + str(len(rejected)))
        lines += ['']
    lines += ['结束记录：' + json.dumps(trajectory.get('ending'), ensure_ascii=False),
              '调用/验证错误：' + json.dumps(trajectory.get('generation_error'), ensure_ascii=False),
              '自动检查仅查算术和明确的无证据更新；不代替语义人工审核。',
              '自动检查发现：' + (', '.join(findings) or '未发现上述两类矛盾'),
              '人工仍需检查：新增/重复、动作归属、私有事实披露时序、自然度、历史连续性。']
    (directory / 'evidence_review.txt').write_text('\n'.join(lines) + '\n')
    dialogue += ['结束记录：' + json.dumps(trajectory.get('ending'), ensure_ascii=False),
                 '错误记录：' + json.dumps(trajectory.get('generation_error'), ensure_ascii=False),
                 '每个变量的完整依据见 evidence_review.txt；曲线见 state_curves.png。']
    (directory / 'dialogue.txt').write_text('\n'.join(dialogue) + '\n')
    with (directory / 'state_changes.csv').open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=['turn', 'kind', 'variable', 'before', 'after', 'delta',
                                                  'judgment', 'evidence', 'rationale'])
        writer.writeheader()
        writer.writerows(records)
    if turns:
        plot(directory, trajectory)
    return {'case': directory.name, 'status': result['status'], 'turns': len(turns),
            'findings': findings, 'review': str((directory / 'evidence_review.txt').relative_to(ROOT)),
            'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}


def plot(directory, trajectory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    turns = trajectory['turns']
    families = list(turns[0]['state_before'])
    fig, axes = plt.subplots(len(families) + 1, 1, figsize=(12, 3.2 * (len(families) + 1)), squeeze=False)
    for ax, family in zip(axes[:, 0], families):
        for variable, initial in turns[0]['state_before'][family].items():
            values = [initial] + [turn['state_after'][family][variable] for turn in turns]
            ax.plot(range(len(values)), values, marker='o', markersize=3, label=variable)
        ax.set_title(family)
        ax.set_ylim(-0.3, 10.3)
        ax.set_xticks(range(len(turns) + 1))
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8, loc='upper left', bbox_to_anchor=(1, 1))
    ax = axes[-1, 0]
    initial = flatten_state(turns[0].get('dynamics_before', {}))
    for variable, value in initial.items():
        values = [value] + [flatten_state(turn.get('dynamics_after', {}))[variable] for turn in turns]
        ax.plot(range(len(values)), values, marker='o', markersize=3, label=variable)
    ax.set_title('Interaction dynamics')
    ax.set_ylim(-0.3, 10.3)
    ax.set_xticks(range(len(turns) + 1))
    ax.grid(alpha=0.2)
    if initial:
        ax.legend(fontsize=8, loc='upper left', bbox_to_anchor=(1, 1))
    ax.set_xlabel('Completed turn (0 = initial); no padding')
    fig.suptitle(directory.name + ' | review only; change count is not a quality score')
    fig.tight_layout()
    fig.savefig(directory / 'state_curves.png', dpi=130, bbox_inches='tight')
    plt.close(fig)


def main():
    prereg = load(BASE / 'preregistration.json')
    entries = []
    for index, plan in enumerate(prereg['plans']):
        case = plan['case']
        directory = BASE / f"{index:02d}_{case['scenario_id']}_{case['policy']}"
        entries.append(export_one(directory, plan))
    changed = [path for path, expected in prereg['code_sha256'].items()
               if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected]
    report = {'human_review_status': 'pending', 'formal_admission': False,
              'frozen_files_changed': changed, 'entries': entries}
    (BASE / 'review_index.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    lines = ['六条审核用轨迹：全文、证据与曲线', '未人工通过，不进入正式数据。',
             '冻结文件变化：' + (', '.join(changed) or '无'), '']
    for row in entries:
        lines += [f"{row['case']}：{row['status']}，{row['turns']} 个已完成轮次",
                  '纯对话全文：同目录 dialogue.txt（有轨迹记录时生成）',
                  '正文与所有变量判断：' + row.get('review', '尚无已完成轮次记录'),
                  '状态曲线：同目录 state_curves.png（有已完成轮次时生成）', '']
    (BASE / 'review_index.txt').write_text('\n'.join(lines) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


def watch(runner_pid):
    previous = None
    while True:
        watched = [BASE / 'results.json'] + sorted(BASE.glob('*/checkpoint.json')) + sorted(BASE.glob('*/result.json'))
        signature = [(str(path), path.stat().st_mtime_ns) for path in watched if path.exists()]
        if signature != previous:
            main()
            previous = signature
        result = load(BASE / 'results.json')
        if result.get('status') == 'completed':
            print('All scheduled attempts ended; review remains pending.', flush=True)
            return
        if not Path('/proc/' + str(runner_pid)).exists():
            print('Runner exited without a completed batch; retain partial outputs, no reruns.', flush=True)
            return
        time.sleep(20)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--runner-pid', type=int)
    args = parser.parse_args()
    if args.watch:
        if not args.runner_pid or args.runner_pid <= 0:
            parser.error('--watch requires the existing runner PID')
        watch(args.runner_pid)
    else:
        main()
