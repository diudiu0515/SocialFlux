"""Snapshot the same read-only summary used by /experiments; no model requests."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from offline.choice_builder import save,save_text
from web.experiment_status import ROOT,METRICS,load_experiment_status


def main():
    data=load_experiment_status();out=ROOT/'reports/experiments/2026-10-20_gates_and_results'
    save(out.with_suffix('.json'),data)
    lines=['# 四个 Gate 与实验结果快照','',
        '读取时间（北京时间）：'+datetime.fromisoformat(data['generated_at']).astimezone(ZoneInfo('Asia/Shanghai')).isoformat()+'。运行中 T4 的最新进度以网站 `/experiments` 为准；本文件不启动、暂停或恢复任何实验。','',
        '| Gate | 作用 | 核验安排 |','|---|---|---|']
    for g in data['gates']:lines.append(f"| {g['id']} {g['name']} | {g['purpose']} | {g['review_setting']} |")
    c=data['rollouts']['counts'];g2=data['gates'][1];g3=data['gates'][2];o=data['offline']
    g1=data['gates'][0].get('machine_audit',{});secondary=g3.get('independent_audit',{})
    oracle=o.get('oracle_progress',{})
    current=data.get('dataset_counts',{}).get('offline') or {}
    current_tasks=' / '.join(str(current.get('tasks',{}).get(task,{}).get('total','N/A')) for task in ('T1','T2','T3'))
    lines+=['',f"当前 GPT50：完整 {c['completed']}，失败 {c['failed']}，有正文 {c['readable']}/50。Gate3 模型全审 {g3['machine_reviewed']} 条：{g3['machine_decisions']}；不是人工批准。",
        '',f"Gate1 当前场景结构检查 {g1.get('schema_passed',0)}/{g1.get('scenario_count',50)}；正式通过 {g1.get('formal_passed',0)}，人工冻结尚待完成。",
        '',f"Gate3 第二模型独立审计 {secondary.get('reviewed',0)}/{secondary.get('expected_audit_count',0)}：{secondary.get('decision_counts',{})}；与主审分歧 {len(secondary.get('disagreements') or [])} 条。抽样为固定 20% 加全部拒绝及边界项；分歧不自动取较高分。",
        '',f"Gate2 当前作业状态 `{g2['run_status']}`；来源合同 `{g2['source_contract_status']}`。当前干预组 {g2['raw_intervention_records']} 条、最新仍有执行错误 {g2['raw_execution_errors']} 条。E1/E2/E9 人工包为 40/20/40 项，尚未签署；历史失败与续跑缓存命中均保留。2026-09-26 旧批次结果独立展示，不能转移到当前环境。",
        '',f"当前离线题库：{current.get('scenarios','N/A')} 场景、{current.get('total','N/A')} 题；T1/T2/T3：{current_tasks}；文字／视频材料配对 {current.get('pairs','N/A')}。来源 `{current.get('bank_path','N/A')}`；独立模型能力评测尚未登记。材料配对不代表媒体质量或人工审核通过。",
        '',f"旧 v2 开发题库单列：{o['scenario_count']} 场景、{o['item_count']} 题；题面盲试答覆盖 {o['blind_reviewed_items']}，机器问题标记 {len(o['machine_flagged_ids'])}；文字／视频配对 {o['modality_pairs']}；T2 待回放 {o['t2_replay_pending_scenes']} 场景。此批人工真值 {o['human_labeled']}、正式准入 {o['formal_admitted']}，不移作当前题库结果。",
        '',data['score_note'],'',
        '每个 run 分开记录；`delegated_to_run` 是移交槽位，不是完成轨迹。不把跨 run 单边结果凑成配对。']
    lines+=['','## 当前 Gate 2 机器记录','','| 实验 | 执行/覆盖 | 机器结果 | 人工状态 |','|---|---|---|---|']
    for row in g2['experiments']:
        record=row.get('machine_record',{});partial=row.get('raw_partial')
        if partial:
            coverage=f"{partial['records']} 个节点"
            result=f"单项自动筛查通过 {partial['screen_passed']}"
            if row['id']=='E4':result+=f"；活跃变量方向一致率 {record.get('active_union_direction_agreement')}"
        elif row['id']=='E6':
            coverage=f"{row.get('machine_records',0)} 组双模型回放";result=str(record)
        elif row['id']=='E8':
            coverage=f"{record.get('machine_reviewed_nodes',0)}/{record.get('matched_node_count',0)} 个固定节点"
            result=f"可见检查全部通过 {record.get('visual_passed_nodes',0)}；四帧视觉输入，音频语义未评估"
        else:
            coverage=f"{row['review_items']} 项人工包";result="机器准备与来源绑定，不代签人工判断"
        human='机器判定' if row['id']=='E6' else '已签署' if row['human_attestation'] else '待人工'
        lines.append(f"| {row['id']} {row['name']} | {coverage} | {result} | {human} |")
    lines+=['',
        '本轮已执行全部 46 个可读来源；原始 50 场景分母保留，另 4 个无正文不能检验。E4 的 15 组释义构造未通过 JSON／措辞距离／语义约束检查，因此只有 31 组有效配对；保存的失败候选普遍将英文原句改成中文，不能充作受控的同语释义。E7 另有 1 组状态判定格式失败；E6 的 3 组状态判定格式失败同样保留。',
        '',
        '主要未通过项：E4 活跃变量方向一致率 48.84%，低于 80%；E6 有效 43 组的一致率 49.87%，低于 70%，且存在 3 组回放失败；E8 40 个固定节点只有 3 个通过全部可见检查，音频语义尚未评估。视频按完全相同的渲染输入核对兼容性，整体场景版本不同的重新绑定仍待人工确认。E1/E2/E9 的机器工作是生成并绑定人工证据包，不产生伪造的人工一致率。']
    if oracle:
        lines+=['','## 旧 v2 开发题库的答案筛查记录','',
            f"冻结批次：已产出 {oracle.get('authored_items',0)}/300；独立私有证据核验 {oracle.get('independently_checked_items',0)}/300；公开材料盲答 {oracle.get('public_blind_checked_items',0)}/300。私有核验与候选答案一致且无私有核验问题 {oracle.get('oracle_agreement_items',0)}；综合机器争议题 {len(oracle.get('machine_concern_ids',[]))}。这些是出题质量检查，不是模型能力准确率。",
            '',"每题候选包含实际状态/受控回放绑定、私有证据解释和独立检查。题库中的 `ground_truth` 仍为人工标签字段，不把机器一致写成人工通过。",
            '',"采集入口 `/offline-annotation`：全部分配盲答锁定 → 全部私有证据独立初判 → 机器建议 → 最终人工审核。原盲答与两次 GT 判断分别保存；计算某人的基线时排除本人的 GT，缺其他两人的一致标签时准确率为 N/A。"]
    names=['目标达成','状态适应','风险管理','恢复','关系结果','五维完整子集']
    def fmt(v):
        return f"{v['mean']:.2f} (n={v['n']})" if v.get('mean') is not None and v.get('n') else 'N/A (n=0)'
    def fmt_ci(v):
        interval=v.get('bootstrap_ci95')
        return fmt(v)+(f"；95% 区间 [{interval[0]:.2f}, {interval[1]:.2f}]" if interval else '')
    for run in data['t4_runs']:
        lines+=['','## '+run['title'],'',
            f"状态 `{run['reported_status']}`；匹配进程存活 `{run['process_alive']}`；记录槽位 {run['finished_slots']}/{run['planned_slots']}。{run['note']}",'',
            '| 模型／条件 | '+' | '.join(names)+' |','|---|'+'---:|'*len(names)]
        for model,value in run['models'].items():
            for cond,group in value['conditions'].items():
                lines.append('| '+model+' / '+cond+' | '+' | '.join(fmt(group['metrics'][k]) for k in METRICS)+' |')
        for model,value in run['models'].items():
            lines+=['',f"{model}：结果计数 `{value['status_counts']}`；有效配对 {value['matched_scenarios']}。",
                '同批配对差值（视频条件 − 文字）：'+'；'.join(name+' '+fmt_ci(value['paired_differences'][k]) for name,k in zip(names,METRICS))+'。']
    lines+=['','来源哈希与完整分母见 [JSON 快照](2026-10-20_gates_and_results.json)。',
        '网站入口：在现有站点地址后访问 `/experiments`、`/offline-demo`、`/offline-annotation`。','']
    save_text(out.with_suffix('.md'),'\n'.join(lines))
    print(str(out.with_suffix('.md').relative_to(ROOT)))


if __name__=='__main__':main()
