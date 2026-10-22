"""Report the exact published bank; machine consistency is not ability accuracy."""
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
import json

from offline.choice_builder import load, save, save_text, sha
from offline.oracle import ROOT, BANK
from offline.oracle_release import RUN
from offline.reuse_audit import digest
from evaluation.quality_gates import deterministic_task_review_sample
from web.annotation_sessions import human_results


def main():
    items = [json.loads(line) for line in (BANK / "items.jsonl").read_text().splitlines()]
    manifest = load(BANK / "manifest.json")
    summary = manifest["oracle_summary"]
    originals = {x["instance_id"]: x for x in map(json.loads, (RUN / "source.items.jsonl").read_text().splitlines())}
    flagged = set(summary["machine_concern_ids"])
    private_issues, blind_issues = Counter(), Counter()
    for item in items:
        private_issues.update(item["authoring"]["oracle_reference"]["independent_check"]["issues"])
        blind_issues.update(item["authoring"]["api_screening"]["issues"])
    sample = deterministic_task_review_sample([
        {"instance_id": x["instance_id"], "task_type": x["task"], "item_sha256": digest(x)}
        for x in items])
    audit = {"published_items_sha256": sha(BANK / "items.jsonl"), "executed_items": 300,
             "schema_valid": 300, "bound_state_targets": 300, "t2_replayed_scenes": 50,
             "independent_private_checks": 300, "public_blind_checks": 300,
             "machine_unflagged": 300-len(flagged), "machine_flagged": len(flagged),
             "private_issue_counts": dict(private_issues), "public_blind_issue_counts": dict(blind_issues),
             "changed_target_items": sum(x["target_spec"]["target_state_ids"] != originals[x["instance_id"]]["target_spec"]["target_state_ids"] for x in items),
             "human_reviewers_required": 2, "gate4_spot_check_sample": sample,
             "human_gt": human_results(), "formal_admitted": 0}
    save(RUN / "gate4_machine.json", audit)
    out = ROOT / "reports/experiments/2026-10-20_oracle_reference_and_annotation"
    save(out.with_suffix(".json"), {**audit, "summary": summary, "manifest": manifest})
    lines = ["# 上帝视角参考、人工盲答与 GT 采集", "",
             "报告时间（北京时间）："+datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()+"。", "",
             f"已发布 50 场景、300 道开发题。每个场景 T1/T2/T3 各 2 题；300 题均绑定真实保存的私有状态、完成独立私有证据核验及公开材料盲答。机器综合标记 {len(flagged)} 题需修订或裁决，其余 {300-len(flagged)} 题仍待人工审核。人工 GT 与正式准入均为 0，不能把本次生成完成称为正式测试集通过。", "",
             "| 配置 | 当前值 |", "|---|---|",
             "| T1 | 每场景 2 题，完整公开前史 t1–t2；当前状态／区间变化／证据支持／双变量组合 |",
             "| T2 | 每场景 2 题，A/B 历史各 2 轮、一个共同 ending；50 组同快照受控回放均已验证 |",
             "| T3 | 每场景 2 题，2 个候选行动；每个行动保存 5 次环境回应，按即时或指定延迟窗口判断 |",
             "| 选项 | 四选一，A/B/C/D 各 75 个候选答案；组合题恰好两个实际记录变量 |",
             f"| 视频配对 | {manifest['modality_pairs']} 个逻辑配对；素材待人工。T2 只复用未改变的 t1 视频 |",
             f"| Gate4 人工抽样 | 同一固定样本 {len(sample)} 题，每任务 10 题；两人独立审核，分歧待第三人裁决 |", "",
             "上帝视角证据包括人物设定、完整相关对话、实际状态与更新依据，以及 T2 的两侧受控回放／T3 的行动分支。T1 禁止用截止点以后的事实解释当前状态；即时 T3 不得用后续分支证据。每条分支只有一个实现样本，不能据此声称一般发生概率。", "",
             f"本次修订了 {audit['changed_target_items']} 题的目标变量。GPT50_044 的 T2 删除无依据的选民偏好断言；GPT50_050 的 T2 将既有权限分工改成肯定表达。两个修订均另存版本并重放；原始自然轨迹和失败记录保持原样。", "",
             "公开盲答与私有复核均为独立请求，未向检查者提供候选答案；出题和这两类检查沿用同一模型系列，仍可能存在相关偏差。它们是题目质量筛查，不是独立模型能力准确率。", "",
             f"私有侧唯一答案一致且无问题：{summary['oracle_agreement_items']}/300；综合公开／私有检查后无标记：{300-len(flagged)}/300。", "",
             "私有复核问题（可重叠）：`"+json.dumps(dict(private_issues),ensure_ascii=False)+"`。", "",
             "公开盲答问题（可重叠）：`"+json.dumps(dict(blind_issues),ensure_ascii=False)+"`。", "",
             "## 人工流程", "",
             "入口 `/offline-annotation`。先完成分配范围内全部公开材料盲答并锁定；再开放相关私有证据，完成全部独立 GT 初判；最后按需查看机器候选，提交最终人工判断。三个阶段分别落盘，刷新可恢复，原盲答不可覆盖。当前采集固定为文字条件，与文字被测输入同一白名单投影。", "",
             "两名不同标注人的有效一致结论仅形成待冻结的人类共识；分歧、修改／拒绝意见继续待裁决。某位参与者的人类基线只使用另外至少两人的一致标签，排除其本人 GT；没有独立标签时准确率为 N/A。重复参与或声明已看过私有材料者不进入盲测基线。标注人 ID 为自报身份，需由实验组织者分配和核对。", "",
             "原 `/offline-demo` 是探索与题库审核入口，可筛选机器争议题。正式采集应从新入口开始；已看过旧页面参考答案者须如实声明暴露。没有模拟测试记录写入生产人工库。", "",
             "## 来源与复现", "",
             "- 题库：`tasks/examples/offline_scenarios_v2`；完整原版本：`data/offline_oracle_20261020_complete/previous_release`。",
             "- 主冻结批次、失败请求、修订历史和逐题证据：`data/offline_oracle_20261020_complete`。",
             "- Gate4 机器检查与固定抽样：`data/offline_oracle_20261020_complete/gate4_machine.json`。",
             f"- 主批次实际日志请求 {summary['api_calls']} 次（含失败、修订与解释字母核对，不含之前两个启动批次；详见原始日志）。",
             "- 刷新本报告：`python -m scripts.report_oracle_release`；四 Gate 和 T4 快照：`python -m scripts.publish_experiment_status`。", "",
             "## 逐题机器争议", "",
             "| 题号 | 作者保留问题 | 私有核验问题 | 公开盲答问题／分歧 |", "|---|---|---|---|"]
    for x in items:
        if x["instance_id"] not in flagged:
            continue
        a=x["authoring"];ref=a["oracle_reference"];blind=a["api_screening"]
        check=ref["independent_check"]
        values=[x["instance_id"],"; ".join(ref["unresolved_issues"]),
                "; ".join(check["issues"])+(f"；独立答案 {check['answer']}，可接受 {check['plausible_answers']}，候选 {a['answer']}" if check["plausible_answers"] != [a["answer"]] else ""),
                "; ".join(blind["issues"])+(f"；盲答 {blind['answer']}，候选 {a['answer']}" if blind["plausible_answers"] != [a["answer"]] else "")]
        lines.append("| "+" | ".join(str(v).replace("|","／").replace("\n"," ") or "—" for v in values)+" |")
    save_text(out.with_suffix(".md"), "\n".join(lines)+"\n")
    print(out.with_suffix(".md").relative_to(ROOT))


if __name__ == "__main__":
    main()
