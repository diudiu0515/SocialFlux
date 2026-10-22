"""Publish hash-bound review findings, never raw provider requests or new GT."""
import argparse
from collections import Counter
import json
from pathlib import Path
from offline.choice_builder import save, sha

ROOT=Path(__file__).resolve().parents[1]
LABELS={'metadata_only':'原题可留，补标签','editorial':'保留目标，轻改题面','substantive':'重写问题或答案选项','source_only':'只复用材料另出题'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',default='data/offline_reuse_api_20261020');args=p.parse_args();run=ROOT/args.run
    data=json.loads((run/'results.json').read_text());manifest=json.loads((run/'manifest.json').read_text())
    data['provenance']={'run_path':args.run,'results_sha256':sha(run/'results.json'),'model':manifest['provider']['model'],
           'rubric_sha256':manifest['rubric_sha256'],'reviewer_type':'model_review_not_human','complete':not data['summary']['pending_ids']}
    for row in data['items']:row['reviewer_model']=manifest['provider']['model']
    out=ROOT/'tasks/examples/offline_legacy_api_audit'
    notes_path=out/'assistant_checks.json'
    notes={n['instance_id']:n for n in json.loads(notes_path.read_text())} if notes_path.exists() else {}
    for row in data['items']:
        note=notes.get(row['instance_id'])
        if note and note['item_sha256']==row['item_sha256']:row['assistant_check']=note
    save(out/'results.json',data)
    counts=Counter()
    for f in (run/'calls').glob('*/*/*.json'):
        r=json.loads(f.read_text());counts[r['status']]+=1
    save(out/'manifest.json',{'provenance':data['provenance'],'summary':data['summary'],'api_calls':dict(counts)})
    s=data['summary'];lines=['# 旧题对新版任务设计的适配核验 · 2026-10-20','',
        '**旧题可以部分复用。新版仍保留当前状态、区间变化、历史比较和后果解释；新增能力框架不要求废弃符合边界的旧题。**', '',
        '需要区分原题保留、同目标轻改、重写问题、仅保留材料。标签迁移不能修复证据不足或选项含糊，已有回放也不等于原题适配新版。', '',
        f"实际 API 已完成 **{s.get('blind_completed_items',s['reviewed_items'])} / {s['planned_items']}** 题的公开材料盲试答，以及 **{s['reviewed_items']} / {s['planned_items']}** 题的新版设计复核。模型为 `{manifest['provider']['model']}`。"+
        ('所有计划题均完成。' if not s['pending_ids'] else f"仍有 {len(s['pending_ids'])} 题尚无完整适配结论；下面的迁移分类仅适用于已完成复核的题目。"),'',
        '| 迁移建议 | T1 | T2 | T3 | 合计 |','|---|---:|---:|---:|---:|']
    for key,label in LABELS.items():lines.append('| '+label+' | '+' | '.join(str(s['by_task'][t].get(key,0)) for t in ('T1','T2','T3'))+' | '+str(s['migration_levels'].get(key,0))+' |')
    lines.append('| 待完成适配复核 | '+' | '.join(str(s.get('pending_by_task',{}).get(t,0)) for t in ('T1','T2','T3'))+' | '+str(len(s['pending_ids']))+' |')
    lines += ['', '这些是模型筛查建议，全部 `formal_usable=false`；没有改动旧题、旧成绩、人工审核状态或 GT。分组盲试答用于发现争议，不能当成标准 benchmark 准确率。', '',
        '## 设计上如何复用', '',
        '| 旧题形式 | 新版对应 | 处理重点 |','|---|---|---|',
        '| T1 当前强度（55题） | 当前状态判断 | 材料可留；强/很强等档位缺可区分依据时改为明确状态判断，通常四选一 |',
        '| T1 区间变化（110题） | 状态变化判断 | 起点、主体和公开证据清楚时可保留；基本不变与不足分开 |',
        '| T1 联合变化（55题） | 多维状态组合 | 保留目标，分别核实各维变化，避免把合作当信任 |',
        '| T2 状态比较/共同表达/联合比较（20题） | 历史敏感解释 | 必须依赖具体 A/B 前史；重新检查过度绝对的干扰项 |',
        '| T3 即时/延迟/行动比较/跨时组合（220题） | 后果解释为主 | 写清比较对象、动作数字编号、时间窗口与概率边界 |','',
        '旧生成模板没有独立覆盖 T1 证据支持、T2 历史反证/修复整合、T3 给定目标选择行动。可以复用相同 rollout 或受控分支新出这些题，但不能靠补标签声称已覆盖新题型。', '',
        '## 可查看的具体判断','',
        '旧题审核页新增“新版适配”筛选；每题点击查看参考后显示 API 依据、需改问题与修改建议。接口未完成单列“待完成 API 复核”，不归入任何质量结论。入口：[60 题及 T2](http://127.0.0.1:8000/offline-review?bank=dev60)、[另 400 题](http://127.0.0.1:8000/offline-review?bank=gpt50-t1-t3)、[24 道新版示例](http://127.0.0.1:8000/offline-demo)。完整机器结果见 [results.json](../../tasks/examples/offline_legacy_api_audit/results.json)。', '',
        '| 题号 | 迁移建议 | 具体修改建议／依据 |','|---|---|---|']
    selected=[]
    for level in LABELS:
        selected.extend([r for r in data['items'] if r['migration_level']==level][:3])
    for r in selected:
        text=r['review']['revision'] or r['review']['rationale'];text=text.replace('|','／').replace('\n',' ')
        lines.append(f"| {r['instance_id']} | {LABELS[r['migration_level']]} | {text} |")
    lines += ['', '## 证据与范围', '',
        '助手抽查保留三处争议：SFO-003 的 API 理由误读了 t1 已允许刊发核实材料；SFO-008 不能仅因两侧状态相近判废，但需检查答案是否依赖具体历史；SFG50-003-T1-04 的建议把内在状态改问可见行为，会改变目标，不能视为措辞轻改。新版允许有公开证据支撑的内在状态推断。争议在网站参考区单列，不静默覆盖模型记录或旧答案。', '',
        f"已复核题中，{s['replay_pending']} 道原题仍缺对应完整回放，来源哈希失配 {s['source_hash_failures']} 道。题目适配性与来源准入分别记录。", '',
        '全库本地来源检查另发现：356 题的来源获旧机器审核 approve，72 题对应来源 reject，32 题来源未审；这些状态也不能替代人工判断。原轨道场景4道待回放题与新400题中的候选行动不同，不能借用后者分支冒充已完成。', '',
        '外发范围经用户明确授权：合成公开材料、题干选项、旧答案、变量名称和时间范围；没有发送私有 Persona、隐藏状态数值、未来分支或个人标注。原始 API 请求/输出及失败留在本地 data 目录，网站只展示按题目 SHA 绑定的复核结果。', '',
        f"本运行 API 调用状态：{json.dumps(dict(counts),ensure_ascii=False)}。失败保留，不算已核验；复跑复用已完成的同版本阶段。待完成原因（题数）：{json.dumps(s.get('pending_reasons',{}),ensure_ascii=False)}。", '',
        '这是同一模型的分组盲试答与二次审核，可能存在共同偏差；只检查公开材料能否支持题目，不替代完整分支核验或 T1/T2 人工核验、T3 人工标注。API 与旧答案不一致也不自动证明旧答案错误。', '',
        '流程先以 120／300 秒超时运行，随后保留缓存调整请求超时；为避免持续重复失败，后续运行每组每阶段累计最多两次尝试（早期试运行已有的超额记录保留）。失败记录中没有标注成功的完整复核结论。', '',
        '复现与续作：`python -m offline.reuse_audit --output data/offline_reuse_api_20261020 --workers 12 --request-timeout 180`（达到重试上限的阶段会跳过）；仅重建摘要：加 `--export-only`；发布摘要：`python -m scripts.publish_legacy_api_audit`。','']
    (ROOT/'reports/experiments/2026-10-20_legacy_task_migration.md').write_text('\n'.join(lines))
    print(json.dumps({'reviewed':s['reviewed_items'],'complete':data['provenance']['complete'],'levels':s['migration_levels']},ensure_ascii=False))


if __name__=='__main__':main()
