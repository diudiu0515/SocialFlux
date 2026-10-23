"""Export the /lab research matrix and source inventory; no model requests."""
import csv
from collections import Counter
from datetime import datetime
import io
import json
from zoneinfo import ZoneInfo

from web.experiment_catalog import REPORT, load_matrix
from web.experiment_hub import ROOT, records
from web.experiment_status import load_experiment_status
from web.experiment_tables import build_paper_tables, make_table
from web.experiment_protocols import GATE2_RELATION
from web.human_gt import load_human_gt


def csv_text(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    for row in rows:
        values = ["" if x is None else str(x) for x in row]
        writer.writerow(["'" + x if x.lstrip().startswith(("=", "+", "-", "@")) else x for x in values])
    return "\ufeff" + stream.getvalue()


def publish():
    live = load_experiment_status()
    matrix = load_matrix(ROOT, live, records())
    tables = build_paper_tables(live, matrix) + load_human_gt()['tables']
    stamp = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    base = ROOT / REPORT
    experiments = matrix["experiments"]
    matrix_csv = [["ID", "实验", "分组", "条件", "目标规模", "计划状态", "数据状态", "实际证据", "下一步", "来源"]]
    matrix_csv += [[r["id"], r["title"], r["group"], " / ".join(r["conditions"]), r["target"], r["plan_status"],
                    r["evidence_status"], r["evidence_summary"], r["next_step"], "\n".join(r["sources"])] for r in experiments]
    files_csv = [["文件", "状态", "字节", "SHA-256", "关联实验"]]
    files_csv += [[f["path"], f["status"], f["bytes"], f["sha256"], " / ".join(f["experiments"])] for f in matrix["inventory"]]
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["# 实验矩阵与数据索引", "", f"更新时间（北京时间）：{stamp}。网站入口：`/lab#matrix`。", "",
             "本轮整合 7 项主实验／消融与 Gate2 E1–E9。计划状态由实验台维护，实际证据状态由文件读取。",
             GATE2_RELATION,
             "两个 S0 实验共用 30 场景及动态基线，另设同输入重复基线。执行器和确定性抽样／扰动规则已准备，实际启动、完成和失败以补测表及运行摘要为准。", "",
             "T4 caption 是原文字输入＋视频中可观察内容的文字描述，作为第三条件；不从私有状态或视频生成提示提取答案。", "",
             "## 实验清单", "", "| 实验 | 条件 | 目标规模 | 实际数据 |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(map(cell, [r["title"], " / ".join(r["conditions"]), r["target"], r["evidence_summary"]])) + " |" for r in experiments]
    lines += ["", "## 方法与待办"]
    for row in experiments:
        lines += ["", "### " + row["title"], "", row["method"], "", "完成标准：" + row["acceptance"], "", "下一步：" + row["next_step"]]
    lines += ["", "## 数据口径", "",
              "T1–T3 的题库构建、机器盲试答和参考答案检查只表示材料准备进度；独立能力测试尚未登记，不能换算成模型准确率。",
              "T4 每个 run 独立保留；传输恢复含继承结果，诊断样本与历史评分各自列示，不跨 run 合并配对。",
              live["score_note"], "",
              "Gate2 原始样本、失败、机器筛查与人工签署分别保留。E6 是骨干敏感性，不能当成替换 S0 实验。旧 Gate2 不转作当前环境通过证据。", "",
              "## 导出与刷新", "",
              f"- [完整 JSON（含分 run 统计）]({base.with_suffix('.json').name})",
              f"- [实验矩阵 CSV]({base.with_suffix('.csv').name})",
              f"- [数据文件索引 CSV]({base.stem}_data.csv)", "",
              "- [Gate 方法与论文结果表](2026-10-21_paper_tables.md)",
              "- [LaTeX 表格文档](2026-10-21_paper_tables.tex)", "",
              "刷新：`python -m scripts.publish_experiment_hub`。只读取本地数据并更新本汇总，不调用模型。",
              "原始轨迹、状态和请求留在原目录。索引记录来源文件 SHA-256；本报告及其导出为派生输出，不作为自身输入。", ""]
    outputs = {
        base: "\n".join(lines),
        base.with_suffix(".json"): json.dumps(dict(generated_at=stamp, matrix=matrix, live=live, paper_tables=tables), ensure_ascii=False, indent=2) + "\n",
        base.with_suffix(".csv"): csv_text(matrix_csv),
        base.with_name(base.stem + "_data.csv"): csv_text(files_csv),
    }
    paper_base = base.with_name("2026-10-21_paper_tables")
    index = ["# Gate 方法与论文结果表", "", f"更新时间（北京时间）：{stamp}；页面入口 `/lab#paper`。", "", GATE2_RELATION, "",
             "每张表可在实验台独立下载 Markdown、CSV、LaTeX。下列数据保留机器／人工、材料／能力成绩和各 run 的边界。", "",
             "LaTeX 使用 longtable、booktabs、array；中文使用 XeLaTeX/ctex。表格可跨页，导出的独立片段可插入论文。", "",
             "## CSV 下载", ""]
    index += [f"- [{t['title']}]({paper_base.name}/{t['id']}.csv)" for t in tables]
    outputs[paper_base.with_suffix(".md")] = "\n".join(index) + "\n\n" + "\n".join(t["exports"]["markdown"] for t in tables)
    outputs[paper_base.with_suffix(".tex")] = (r"\documentclass[UTF8]{ctexart}" + "\n" +
        r"\usepackage[a4paper,landscape,margin=1.4cm]{geometry}" + "\n" + r"\usepackage{booktabs,longtable,array}" + "\n" +
        r"\begin{document}" + "\n" + ("\n" + r"\clearpage" + "\n").join(t["exports"]["latex"] for t in tables) + "\n" + r"\end{document}" + "\n")
    for table in tables:
        outputs[paper_base / (table["id"] + ".csv")] = table["exports"]["csv"]
    s0 = live.get('s0_ablation')
    if s0:
        s0_base = base.with_name('2026-10-22_gate2_supplement_continuation')
        pair_rows = []
        for condition, label in [('dynamic_repeat', '同输入重复基线'), ('replaced_s0', 'S1 替换 S0'),
                                 ('fixed_s0_no_update_prompt', 'S2 固定 S0 并移除更新')]:
            pair = s0.get('pairs', {}).get(condition, {})
            pair_rows.append([label, pair.get('n', 0), *[
                f'{pair["metrics"][key]:.4f}' if pair.get('metrics', {}).get(key) is not None else 'N/A'
                for key in ('state_delta_mae', 'state_level_mae', 'response_text_distance')]])
        paired = make_table('s0-latest-pairs', '完整场景配对结果',
            ['对照', '有效配对 n', '更新量 MAE', '状态值 MAE', '回复文本距离'], pair_rows,
            ['三项均与动态基线比较；各自配对分母不同，不直接相减。文本距离不是质量分。'],
            [f'data/{s0["run_id"]}/summary.json'])
        coverage = next((t for t in tables if t['id'] == 's0-current-coverage'), None)
        failures = dict(Counter(r.get('error_type', 'unknown') for r in s0.get('failures', [])))
        outputs[s0_base.with_suffix('.md')] = '\n'.join([
            '# Gate2 S1/S2 补充消融续跑', '', f'汇总更新时间（北京时间）：{stamp}。', '',
            f"当前机器状态：`{s0.get('status')}`；运行进程存活：`{s0.get('process_alive')}`；累计保存条件轮次 {s0.get('saved_turns', 0)}。", '',
            '同一冻结 30 场景、四条件共 120 个条件任务。成功前缀不计完整配对；全部历史失败保留。S1/S2 共用动态基线，不计作 60 个独立场景。', '',
            coverage['exports']['markdown'] if coverage else '', paired['exports']['markdown'],
            '失败类型：' + '；'.join(f'{k} {v}' for k, v in failures.items()) + '。', '',
            '本轮采用机器统计，不纳入人工标注任务。固定原始历史、行动和 ledger；生成回复不回填历史，不能当作自由 T4 结果，也不替代 Gate2 E1–E9 正式验证。', '',
            '[完整论文结果及执行后修订记录](2026-10-21_paper_tables.md) · [当前汇总 JSON](2026-10-22_gate2_supplement_continuation.json)', ''])
        outputs[s0_base.with_suffix('.json')] = json.dumps(dict(generated_at=stamp,
            **{key: s0.get(key) for key in ('run_id', 'updated_at', 'status', 'process_alive', 'target_scenarios',
                'execution_counts', 'pairs', 'saved_turns', 'frozen_checked_turns', 'reliable_continuation', 'failures')},
            failure_counts=failures, human_review_scope='machine_statistics_only_not_an_annotation_task'),
            ensure_ascii=False, indent=2) + '\n'
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    return dict(experiments=len(experiments), sources=len(matrix["inventory"]), paper_tables=len(tables),
                files=[str(path.relative_to(ROOT)) for path in outputs],
                read_errors=matrix["read_errors"] + live["read_errors"])


if __name__ == "__main__":
    print(json.dumps(publish(), ensure_ascii=False))
