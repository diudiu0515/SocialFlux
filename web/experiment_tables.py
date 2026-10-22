"""One table representation shared by the website and paper exports."""
import csv
import io
import math

from web.experiment_protocols import GATE_OVERVIEW, GATE2_PROTOCOLS, GATE2_RELATION, PROTOCOL_SOURCES
from web.experiment_status import METRICS

METRIC_LABELS = ["目标达成", "状态适应", "风险管理", "恢复", "关系结果", "五维完整子集"]
STATUS_LABELS = {"pending": "待核验", "pass": "通过", "passed": "通过", "fail": "未通过", "rejected": "未通过"}


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def percent(value):
    return f"{100 * value:.2f}%" if number(value) else "N/A"


def ratio(numerator, denominator):
    if not number(numerator) or not number(denominator) or denominator <= 0:
        return "N/A"
    return f"{int(numerator)}/{int(denominator)} ({percent(numerator / denominator)})"


def score(value, paired=False):
    value = value or {}
    if not value.get("n") or not number(value.get("mean")):
        return "N/A (n=0)"
    result = f"{value['mean']:.2f} (n={value['n']})"
    if paired:
        interval = value.get("bootstrap_ci95")
        if isinstance(interval, list) and len(interval) == 2 and all(number(x) for x in interval):
            result += f"; 95% CI [{interval[0]:.2f}, {interval[1]:.2f}]"
    elif number(value.get("sd")):
        result += f"; SD={value['sd']:.2f}"
    return result


def csv_table(table):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    for row in [table["columns"], *table["rows"]]:
        cells = ["" if x is None else str(x) for x in row]
        writer.writerow(["'" + x if x.lstrip().startswith(("=", "+", "-", "@")) else x for x in cells])
    return "\ufeff" + output.getvalue()


def markdown_table(table):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", "<br>")
    lines = ["### " + table["title"], "", "| " + " | ".join(map(cell, table["columns"])) + " |",
             "|" + "---|" * len(table["columns"])]
    lines += ["| " + " | ".join(map(cell, row)) + " |" for row in table["rows"]]
    lines += ["", *table["notes"], "", "来源：" + "；".join("`" + p + "`" for p in table["sources"]), ""]
    return "\n".join(lines)


def latex_table(table):
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
                    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    def cell(value):
        return "".join(replacements.get(c, c) for c in str(value).replace("\n", " "))
    count = len(table["columns"])
    columns = (r">{\raggedright\arraybackslash}p{\dimexpr" + f"{1/count:.6f}" + r"\linewidth-2\tabcolsep\relax}") * count
    heading = " & ".join(map(cell, table["columns"])) + r" \\ "
    lines = [r"\begingroup\scriptsize", r"\begin{longtable}{" + columns + "}",
             r"\caption{" + cell(table["title"]) + r"}\label{tab:" + table["id"].replace("_", "-") + r"}\\",
             r"\toprule", heading, r"\midrule\endfirsthead", r"\toprule", heading, r"\midrule\endhead",
             r"\bottomrule\endfoot"]
    lines += [" & ".join(map(cell, row)) + r" \\" for row in table["rows"]]
    lines += [r"\end{longtable}", r"\par\smallskip\noindent", cell(" ".join(table["notes"])), r"\par\endgroup",
              *["% source: " + path for path in table["sources"]], ""]
    return "\n".join(lines)


def make_table(identity, title, columns, rows, notes, sources):
    table = dict(id=identity, title=title, columns=columns, rows=rows, notes=notes,
                 sources=list(dict.fromkeys(sources)))
    if any(len(row) != len(columns) for row in rows):
        raise ValueError("table column count mismatch: " + identity)
    table["exports"] = dict(csv=csv_table(table), markdown=markdown_table(table), latex=latex_table(table))
    return table


def dataset_tables(live):
    inventory = live.get('dataset_counts') or {}
    if not inventory:
        return []
    sources = [s['path'] for s in inventory.get('sources', [])]
    offline = inventory.get('offline') or {}
    stamp = '更新时间（北京时间）：' + inventory.get('generated_at', '')
    def cell(value):
        return 'N/A' if value is None else value
    rows = []
    for cohort in inventory.get('cohorts', []):
        bank = offline.get('cohorts', {}).get(cohort['id'], {})
        rows.append([cohort['id'], *[cell(cohort.get(k)) for k in
                     ('scenarios', 'usable', 'failed', 'invalid', 'pending')],
                     *[cell(bank.get(k)) for k in ('ordinary', 'hard', 'total')]])
    if rows:
        rows.append(['合计', *[sum(r[i] for r in rows) if all(number(r[i]) for r in rows) else 'N/A'
                              for i in range(1, len(rows[0]))]])
    tables = [make_table('dataset-overview', '数据总量：场景、rollout 与 Offline 题库',
        ['来源', 'Scenario 数', '可用 rollout', '生成失败 / T4-hard 候选', '完整性异常 / 待复核',
         '待完成', 'Offline 普通（简单）', 'Offline Hard', 'Offline 总题量'], rows,
        [stamp, '可用 rollout：当前指定来源中通过 T4 完整性校验的轨迹（1–20 轮、连续轮次、有效终止）；不代表 Gate3 人工或正式准入通过。',
         '失败按唯一场景统计；保留失败记录与前缀。T4-hard 目前仅为候选，需区分接口／结构错误和任务本身的困难，尚未形成已验证的 Hard 评测集。',
         'Offline 优先读取当前英文标注发布题库；未发布时读取 v2 开发题库。普通对应 ordinary，Hard 对应设计难度 hard。旧版、翻译和两个模态副本不重复累加；CF150 的 0 表示当前题库无题目。',
         '文件读取异常显示在页面提示中，不作为生成失败。'], sources + [str(p) for p in (
             'data/claude150_v1/state_v3_validation/full_rollout_state_repair_v31/sources',
             'data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/unified_current_trust_v1_gpt50_active')])]
    if offline:
        task_rows = [[task, *[cell(row.get(k)) for k in ('scenarios', 'ordinary', 'hard', 'unknown', 'total', 'pairs')]]
                     for task, row in offline.get('tasks', {}).items()]
        task_rows.append(['合计（场景去重）', *[cell(offline.get(k)) for k in
                         ('scenarios', 'ordinary', 'hard', 'unknown', 'total', 'pairs')]])
        tables.append(make_table('offline-counts', 'Offline 题量与文字／视频材料配对',
            ['任务', 'Scenario 数', '普通（简单）', 'Hard', '难度未标注', '总题量', 'Text / Text+Video 材料对'], task_rows,
            [stamp, '一题两个模态仍计一道题；配对要求同一题目编号同时有唯一 text 与 text+video 条目，且配对清单绑定当前题库哈希。',
             ('英文标注版只开放语音与口型检查通过的完整场景；人工媒体核对仍待完成。' if offline.get('release') else '材料对不表示模型已作答或媒体覆盖完整。') + '当前配对清单覆盖：' +
             '；'.join(f'{k}={v}' for k, v in offline.get('media_coverage', {}).items()) + '。',
             'Hard 是设计标签；不是已经测得的低正确率。'], sources))
    runs = [run for run in live.get('t4_runs', []) if run.get('kind') != 'historical_scoring']
    paired_rows = []
    for run in runs:
        for model, value in run.get('models', {}).items():
            conditions, counts = value.get('conditions', {}), value.get('status_counts', {})
            paired_rows.append([run['id'], model, cell(conditions.get('text_only', {}).get('n')),
                cell(conditions.get('text_video', {}).get('n')), cell(value.get('matched_scenarios')),
                counts.get('failed', 0), counts.get('completed_without_video_exposure', 0),
                counts.get('unsupported_video_input', 0), counts.get('delegated_to_run', 0)])
    tables.append(make_table('t4-counts', 'T4 评测数量：Text、Text+Video 与有效配对',
        ['Run', '模型', 'Text 有效 n', 'Text+Video 有效 n', '有效配对数', '失败槽位', '未送达视频', '不支持视频', '移交槽位'],
        paired_rows, [stamp, '每行是一个 run × 模型；配对为同 run、同场景、同模型的两条件均完成，且视频实际送达。',
        '各 run 独立列示，不设跨 run 总计：续跑会继承前批结果，不能重复相加，也不能跨批拼接配对。失败槽位不是去重的失败场景数。',
        '原始生成轨迹的终局评分与人工校准另列，未计入本表的在线模态评测。'],
        [f"build/{run['id']}/run/summary.json" for run in runs]))
    tables.append(make_table('t4hard-candidates', 'Rollout 失败场景：T4-hard 候选清单',
        ['Scenario', '来源', '类型', '原因', '原始来源'],
        [[x['scenario_id'], x['cohort'], '生成失败' if x['status'] == 'failed' else '完整性异常', x['reason'], x['source']]
         for x in inventory.get('t4hard_candidates', [])],
        [stamp, '仅保留候选清单，不修改原始数据、不启动新评测；技术故障不等同于已证实的任务难度。'], sources))
    return tables


def build_paper_tables(live, matrix):
    live = live or {}
    tables = dataset_tables(live) + [make_table("gate-overview", "四个 Gate 的职责与准入要求",
        ["Gate", "验证对象", "样本单位", "具体检查", "审核安排", "通过要求"], GATE_OVERVIEW,
        ["此表描述项目当前协议；开发批次机器证据不能自动视为正式通过。"], PROTOCOL_SOURCES)]
    tables.append(make_table("gate2-methods", "Gate2 E1–E9：研究问题、对照与指标",
        ["实验", "类型", "验证什么", "具体做法与固定项", "测量指标", "通过要求"],
        [[key + " " + p["name"], p["kind"], p["hypothesis"], p["method"], p["measurement"], p["acceptance"]]
         for key, p in GATE2_PROTOCOLS.items()], [GATE2_RELATION], PROTOCOL_SOURCES))
    followup = live.get('gate2_followup') or {}
    if followup:
        coverage = followup.get('condition_counts', {})
        equivalence_labels = {'machine_equivalent': '机器判等价', 'machine_rejected': '机器判不等价', 'unavailable': '构造或核验未完成'}
        followup_status = {'running': '执行中', 'finished': '已执行，待人工核验', 'prepared': '已准备'}.get(followup.get('status'), followup.get('status'))
        tables.append(make_table('gate2-followup-coverage', 'Gate2 补测执行覆盖与失败分母',
            ['条件', '目标场景', '完成', '失败', '未执行/不适用', '场景结果待记录'],
            [[label, followup.get('expected', 46), coverage.get(key, {}).get('completed', 0), coverage.get(key, {}).get('failed', 0),
              sum(v for k, v in coverage.get(key, {}).items() if k not in ('completed', 'failed')),
              max(0, followup.get('expected', 46)-followup.get('recorded', 0))]
             for key, label in [('original','原句'), ('repeat','原句重复'), ('paraphrase','同语言释义'), ('recent3','recent-3 完整轮次')]],
            ['完成单个条件不等于形成配对；仅同一场景的两个条件均成功时计算对应指标。失败不换场景、不填零。',
             '释义未执行包含机器判为不等价或构造/核验失败；recent-3 不适用表示原历史不超过三轮。',
             '机器等价状态：' + '；'.join(f'{equivalence_labels.get(k, k)} {v}' for k, v in followup.get('semantic_equivalence', {}).items())],
            ['data/gate2_followup_final_20261022/summary.json']))
        rows = []
        labels = {'repeat':'原句重复（随机波动基线）', 'paraphrase':'同语言释义（机器等价筛查后）', 'recent3':'recent-3 历史对照'}
        for key, label in labels.items():
            r = followup.get('comparisons', {}).get(key, {})
            rows.append([label, r.get('pairs', 0), r.get('active_dimensions', 0), percent(r.get('direction_agreement')), percent(r.get('change_agreement')), percent(r.get('reversal_rate')), percent(r.get('all_dimension_agreement'))])
        tables.append(make_table('gate2-followup', 'Gate2 补测：释义、原句重复与 recent-3',
            ['对照', '有效配对', '活跃维度', '活跃方向一致率', '变化/不变一致率', '真实反向率', '全维方向一致率'], rows,
            [f"固定 46 场景；已记录 {followup.get('recorded', 0)}/46；{followup_status}；累计请求 {followup.get('api_requests', 0)}/600（含此前中止批次）。",
             '原始 31 对 E4 另表保留。补测四条件使用同一冻结 checkpoint；已完成的同配置原句/重复输出按哈希复用，其余重新执行。主指标只计活跃维度，不以双零维度抬高一致率。',
             '初次输出多次截断；在保留失败的前提下，提高输出上限和超时；另修正 recent-3 按完整轮次截取（每轮包含双方消息）。阈值仍为 80%，未改场景、模型、温度、seed 或语义提示。',
             '机器判断等价不替代人工等价核验；失败、缺失及无活跃维度保持 N/A，不自动触发正式准入。',
             '80% 是 E4 释义的原定方向阈值；recent-3 检查历史依赖，不能按此阈值判失败。原句重复用于估计同输入波动。'],
            ['data/gate2_followup_final_20261022/summary.json', 'data/gate2_followup_final_20261022/manifest.json', 'data/gate2_followup_20261022/summary.json']))
    controls = followup.get('matched_controls') or {}
    if controls:
        input_audit = controls.get('repeat_input_audit', {})
        tables.append(make_table('gate2-followup-controls', '释义与原句重复：相同场景、相同活跃维度对照',
            ['完整三元组', '共同活跃维度', '原句重复方向一致率', '释义方向一致率', '释义−原句重复', '场景配对 bootstrap 95% CI'],
            [[controls['matched_scenarios'], controls['active_dimensions'], percent(controls['repeat_direction_agreement']),
              percent(controls['paraphrase_direction_agreement']), percent(controls['paraphrase_minus_repeat']),
              ' / '.join(percent(x) for x in controls['paired_scene_bootstrap_ci95']) if controls.get('paired_scene_bootstrap_ci95') else 'N/A']],
            ['仅使用原句、重复、释义全部有效的同一场景；共同分母为三条件中任一发生变化的维度。',
             '这是区分措辞影响与同输入波动的辅助分析，不替换原定双条件活跃维度指标或 80% 阈值。按场景配对 bootstrap 2000 次；人工等价核验仍待完成。',
             f"原句重复的实际输入及采样参数核验：{input_audit.get('matched_stage_pairs', 0)}/{input_audit.get('compared_stage_pairs', 0)} 组阶段请求相同；不一致 {len(input_audit.get('mismatches', []))}，缺失 {len(input_audit.get('missing', []))}。"],
            ['data/gate2_followup_final_20261022/matched_controls.json']))
    gate2 = next((g for g in live.get("gates", []) if g["id"] == "Gate 2"), {})
    evidence = {e["id"]: e for e in gate2.get("experiments", [])}
    rows = []
    for key, p in GATE2_PROTOCOLS.items():
        e = evidence.get(key, {})
        m, extra = e.get("machine_record", {}), e.get("report_metrics", {})
        human = "已签署" if e.get("human_attestation") else "待人工"
        if key == "E6":
            human = "协议不要求人工签署"
        amount, valid, screening, primary, detail = "N/A", "N/A", "N/A", "N/A", "证据暂缺"
        if e.get("evidence_present"):
            if key in ("E1", "E2", "E9"):
                amount = e.get("review_items", 0)
                screening = "仅已准备证据包"
                if key == "E1":
                    valid = amount if e.get("human_attestation") and number(extra.get("agreement")) else "N/A"
                    primary = "人工方向一致率 " + percent(extra.get("agreement"))
                    detail = "含生成错误来源转移 " + str(extra.get("source_status_counts", {}).get("generation_error", 0))
                elif key == "E2":
                    scores = extra.get("scores") or {}
                    valid = amount if e.get("human_attestation") and number(scores.get("overall")) else "N/A"
                    primary = "整体 " + (f"{scores['overall']:.2f}/5" if number(scores.get("overall")) else "N/A")
                    detail = "；".join(label + " " + (f"{scores[k]:.2f}" if number(scores.get(k)) else "N/A")
                        for k, label in (("persona_consistency", "人格"), ("history_sensitivity", "历史"),
                                         ("state_continuity", "状态连续性"), ("response_state_consistency", "回应一致性")))
                    detail += "；部分失败前缀 " + str(extra.get('source_status_counts', {}).get('generation_error', 0)) + "（仅诊断，不算完整轨迹）"
                else:
                    valid = extra.get("matched_variable_count", 0)
                    primary = "人工速度方向一致率 " + percent(extra.get("direction_consistency"))
                    families = extra.get("timescale_families") or {}
                    detail = "快/中/慢候选 " + "/".join(str(families.get(k, 0)) for k in ("fast", "medium", "slow"))
                    detail += "；零变化比例 " + percent(extra.get("review_sample_zero_change_fraction"))
            elif key in ("E3", "E4", "E5", "E7"):
                partial = e.get("raw_partial") or {}
                amount = gate2.get("raw_intervention_records", "N/A")
                valid = partial.get("records", "N/A")
                screening = ratio(partial.get("screen_passed"), valid)
                primary = "活跃变量方向一致率 " + percent(m.get("active_union_direction_agreement")) if key == "E4" else "干预有效性待人工确认"
                detail = ("未形成有效配对 " + str(amount - valid)) if number(amount) and number(valid) else "分母待核验"
                if key == "E4":
                    detail += "；活跃变量 " + str(extra.get("active_union_dimension_count", "N/A"))
                elif key == "E3":
                    detail += "；原批次 full vs critical-removed，recent-3 见补测表"
                elif key == "E7":
                    detail += "；改 4 个人格风格字段，数值状态固定；响应与重复基线未测"
            elif key == "E6":
                amount = m.get("matched_checkpoint_count", "N/A")
                valid = m.get("successful_matched_checkpoint_count", "N/A")
                screening = "节点通过比例 " + percent(extra.get("record_pass_fraction"))
                primary = "活跃变量方向一致率 " + percent(m.get("mean_active_union_direction_agreement"))
                detail = f"回放失败 {m.get('replay_failure_count', 'N/A')}；真实符号反转率 {percent(m.get('mean_true_sign_reversal_rate'))}"
            elif key == "E8":
                amount = m.get("matched_node_count", "N/A")
                valid = m.get("machine_reviewed_nodes", "N/A")
                screening = ratio(m.get("visual_passed_nodes"), valid)
                primary = "全部可见检查通过率 " + percent(m.get("visual_passed_nodes", 0) / valid) if number(valid) and valid > 0 else "N/A"
                detail = "四帧视觉输入；音频语义 " + str(m.get("audio_semantic_review", "待核验"))
        unit = {"E1": "状态转移", "E2": "完整轨迹", "E9": "变量序列", "E8": "视频节点"}.get(key, "匹配节点/对")
        rows.append([key + " " + p["name"], unit, amount, valid, screening, primary, detail, human,
                     STATUS_LABELS.get(e.get("status"), e.get("status", "证据暂缺"))])
    progress = gate2.get("machine_progress", {})
    notes = ["证据量是抽样包或尝试量；n 为主指标可用样本。E1/E2/E9 缺人工判断时显示 N/A，不用零分代替。",
             "E3/E4/E5/E7 的机器筛查率与 E4/E6 的方向一致率是不同统计量。机器通过数不代表人工通过数。",
             "E4/E6 主方向指标仅在活跃变量并集上计算，避免双方都不变抬高一致率；失败留在原分母并另报。",
             f"当前来源合同：{gate2.get('source_contract_status', '未知')}；可读来源 {progress.get('expected_readable_sources', 'N/A')}，原始场景分母 {live.get('rollouts', {}).get('expected', 'N/A')}。"]
    thresholds = evidence.get("E6", {}).get("report_metrics", {}).get("thresholds", {})
    if thresholds:
        labels = {"minimum_direction_agreement": "方向一致率下限", "maximum_reversal_fraction": "反转率上限",
                  "minimum_record_pass_fraction": "节点通过比例下限", "minimum_backbone_active_record_fraction": "骨干活跃节点比例下限"}
        notes.append("E6 本次运行阈值：" + "；".join(label + " " + percent(thresholds.get(k)) for k, label in labels.items()) + "；回放失败为硬阻断。")
    tables.append(make_table("gate2-results", "Gate2 当前批次结果（机器证据与人工审核分列）",
        ["实验", "单位", "证据/尝试量", "可计算样本 n", "机器筛查/通过", "主指标", "失败与补充指标", "人工状态", "正式状态"],
        rows, notes, [e["source"] for e in evidence.values() if e.get("source")]))
    tables.append(make_table("gate2-coverage-gaps", "Gate2 覆盖范围与仍需完成的验证",
        ["项目", "已有覆盖", "明确缺口", "下一步"], [
            ["E1 / E2 / E9", "状态转移、完整轨迹和变量序列证据包已准备", "尚无规定的人工判断／签署", "在 annotation 页随题完成对应核对，再导入 lab；不能以新增机器调用替代"],
            ["E3 历史", "full vs critical-removed；appraisal/state 回放", "recent-3 见补测表；生成回复对照仍未覆盖", "新增时单列条件及分母；当前结果只支持已跑对照"],
            ["E4 释义", "有效释义配对与活跃变量方向指标见结果表", "无效配对／失败仍存在，机器筛查不能证明语义等价", "同语言释义与原句重复补测另表保留；在 annotation 页独立核验等价性"],
            ["E6 骨干", "两个模型家族同节点回放", "现有结果未通过；同时有回放失败和方向不一致", "分开诊断执行故障与实质差异，不以增加样本冒充通过"],
            ["E7 人格 P", "改 4 个风格字段，固定数值状态、历史和行动", "1 条执行失败；无回复对照、同输入重复基线或人工确认", "保留 45 对 / 39 筛查结果；数值 S0 扩展记为 S1，不混算"],
            ["E8 视频", "四个时间戳帧的视觉检查", "可见检查通过率低；音频与完整视频人工语义未覆盖", "annotation 页已接入精确绑定的视频及音轨核对；等待人工，不能称多模态有效性已通过"],
            ["S1 数值 S0", "执行器及同批 30 场景抽样／±2 替换规则已准备", "真实调用进度见补测表；人工差异判读待完成", "原 S0 / 重复原 S0 / 替换 S0，固定历史回放全部可用轮次"],
            ["S2 固定 S0", "冻结 S0/D0、无状态请求及 prompt 移除的本地检查已通过", "真实调用进度见补测表；回复差异待人工判读", "共用 S1 场景和基线，核验每轮冻结不变量，按组合消融解释"],
        ], ["缺口包含未测试、执行失败、实质未通过和待人工四类；不能相互替代。本地代码测试不计作模型实验结果。"],
        ["web/experiment_protocols.py", "scripts/run_environment_interventions.py", "scripts/complete_gate_machine_checks.py", "scripts/run_s0_mechanism_ablation.py"]))
    supplementary = [r for r in matrix.get("experiments", []) if r.get("supplement_id") or r["id"] == "study-t4-caption"]
    from web.experiment_protocols import S0_STATUS_LABELS
    supplementary_rows = []
    run = live.get("s0_ablation", {})
    audit_checks = run.get('prompt_audit', {}).get('checks', {})
    audit_note = "；".join(label + ("是" if audit_checks.get(key) else "否") for key,label in (
        ('repeat_identical_state_request','重复基线状态请求完全一致：'),
        ('repeat_identical_interaction_request','重复基线交互请求完全一致：'),
        ('frozen_update_policy_present','冻结条件仍含更新策略提示：')))
    audit_note += "；冻结条件状态请求数：" + str(audit_checks.get('frozen_state_request_count','未核验'))
    source_counts = run.get('source_status_counts', {})
    if run.get('execution_counts'):
        names = {'dynamic_state':'原 S0 动态更新','dynamic_repeat':'原 S0 重复基线',
                 'replaced_s0':'替换数值 S0','fixed_s0_no_update_prompt':'固定 S0/D0 并移除更新提示'}
        tables.append(make_table('s0-current-coverage', 'S0 四条件补测：当前执行覆盖',
            ['条件','目标场景','完整完成','失败','待续或恢复','执行中','尚未开始','有效保存轮次'],
            [[names.get(c,c),run.get('target_scenarios',30),v.get('completed',0),v.get('failed',0),
              v.get('pilot_ready',0),v.get('running',0),v.get('not_started',0),v.get('saved_turns',0)]
             for c,v in run['execution_counts'].items()],
            [f"当前状态：{S0_STATUS_LABELS.get(run.get('status'),run.get('status'))}；更新时间：{run.get('updated_at','')}。",
             '逐场景读取当前结果；原始失败留档、成功前缀复用，未开始和有效前缀都不算完整完成。来源为同一冻结 30 场景，不是新增样本。',
             '当前续跑信息：'+str(run.get('reliable_continuation') or run.get('supplement_continuation',{}))],
            [f"data/{run['run_id']}/summary.json",f"data/{run['run_id']}/reliable_continuation_20261022.json",f"data/{run['run_id']}/supplement_continuation_20261022.json"]))
    diagnosis = run.get('diagnostics', {})
    if diagnosis:
        bounds = diagnosis.get('bounds_preflight', {})
        probe = diagnosis.get('provider_probe', {})
        names = {'dynamic_state':'原 S0 动态更新','dynamic_repeat':'原 S0 重复基线',
                 'replaced_s0':'替换数值 S0','fixed_s0_no_update_prompt':'固定 S0/D0 并移除更新提示'}
        rows = [[names.get(c,c), 30, v.get('completed',0), v.get('failed',0),
                 v.get('interrupted',0), v.get('not_started',0), v.get('saved_turns',0)]
                for c,v in diagnosis.get('execution_counts',{}).items()]
        tables.append(make_table('s0-execution-coverage', 'S0 四条件补测：首次故障暂停时的覆盖快照',
            ['条件','目标场景','完整完成','失败','执行中断','尚未开始','有效保存轮次'], rows,
            [f"快照时间：{diagnosis.get('updated_at','')}；后续恢复以补测实时表为准。" + diagnosis.get('reason',''), '失败分类：' + str(diagnosis.get('failure_counts',{})) + '。失败、中断及未开始均不计为完整配对。',
             f"S0 修正规则本地预检：{bounds.get('passed',0)}/{bounds.get('total',30)}；需修正 {bounds.get('changed_scenarios',0)} 个场景。旧规则允许 [0,10]，初始化契约要求 [1,9]；修正规则保留原哈希方向，在越界时反向 ±2。预检本身不产生实验结果，原始失败保留。",
             '真实空响应请求的独立诊断：' + str(probe) + '。诊断输出不计入补测轮次、样本量或配对指标。',
             '保存轮次包括未完成场景的有效前缀，不能替代完整场景数。'],
            [f"data/{run['run_id']}/diagnostic_status.json",f"data/{run['run_id']}/s0_bounds_preflight.json"]))
    def result_text(pair):
        metrics = pair.get("metrics", {})
        return "；".join(label + (f"{metrics[key]:.4f}" if number(metrics.get(key)) else "N/A")
            for key, label in (("state_delta_mae", "更新量 MAE="), ("state_level_mae", "状态值 MAE="),
                               ("response_text_distance", "回复文本距离=")))
    for r in supplementary:
        condition = "replaced_s0" if r.get("supplement_id") == "S1" else "fixed_s0_no_update_prompt"
        active = bool(run and r.get("supplement_id"))
        pair = run.get("pairs", {}).get(condition, {}) if active else {}
        count = pair.get("n", 0) if active else "N/A"
        condition_progress = run.get("conditions", {}).get(condition, {})
        result = (f"{S0_STATUS_LABELS.get(run.get('status'),run.get('status'))}；已存 {condition_progress.get('saved_turns',0)} 轮；失败 {condition_progress.get('failed',0)} 场景；" + result_text(pair)) if active else "待运行"
        supplementary_rows.append([r["title"], r["group"], " / ".join(r["conditions"]), r["target"], count, result, r["acceptance"]])
    if run:
        pair = run.get("pairs", {}).get("dynamic_repeat", {})
        supplementary_rows.append(["同输入重复基线", "Gate2 补充消融", "dynamic_state / dynamic_repeat",
            "与 S1/S2 同一 30 场景", pair.get("n", 0), result_text(pair), "测量随机波动；不作为独立场景加到总样本量。"])
    tables.append(make_table("supplementary-results", "补充消融与 caption 对照：实际进度与配对结果",
        ["实验", "归属", "条件", "目标规模", "实际配对 n", "结果", "验证要求"],
        supplementary_rows,
        ["S1/S2 共用 30 场景和动态基线；不可加成 60 个独立场景。四条件单轮试跑通过后覆盖来源全部可用轮次。仅双方完成预定来源轮次才计入配对 n，并不意味着来源为合格的自然完整轨迹。",
         "冻结队列来源：完整未审核 " + str(source_counts.get('completed_unreviewed','未读取')) + "，保留原生成失败片段 " + str(source_counts.get('generation_error','未读取')) + "；每场景来源轮次范围：" + str(run.get("source_turn_range", "未读取")) + "。须按来源状态解释，不能视为正式 Gate3 准入。",
         ("试跑后修订：100 秒传输上限恢复为源配置 600 秒；复用相同请求的已完成输出，每个条件最多一次传输恢复及一次空正文恢复。按原顺序诊断首两场景，语义拒绝保留为失败、不重采样；这些修订不是最初预注册方案。初试失败记录：" + str(run['transport_recovery'].get('initial_failure_counts',{})) + "，保留原分母，不计作新增独立场景。" if run.get("transport_recovery") else "原始失败及后续协议修订须单独留档。"),
         ("首场景首轮的实际请求审计：" + audit_note + "。该审计验证请求控制，不代表响应成功或人工有效性通过。" if run.get('prompt_audit') else "真实请求层的控制审计待记录。"),
         "固定原始历史、行动和 ledger，逐轮累积各条件状态；回复不回填历史，属于 Gate2 机制回放，不能当成自由 T4 成绩。S1 为数值多维 ±2 联合扰动，D0 不变。",
         "S2 同时固定 S0/D0、移除 state appraisal/校准器及交互输入 update_policy，按组合消融解释。文本距离只描述措辞差异，不是质量分或因果有效性通过率。",
         "UnsupportedConsequentialClaim 表示模型将固定动作中的某项事实判断为缺少依据；各条件分别计入失败。基线也出现的拒绝，不能直接归因于冻结状态。",
         "各指标先按场景内所有轮次求均值，再按完整场景求均值；与重复基线配对数不一致时，不直接相减。人工判读仍为待完成。Caption 须在同场景、模型、媒体节点重新配对。"] +
        (["初始化修订 v2：在同一队列内把数值 S0 扰动限定于 [1,9]，12 个场景的拟干预值改变；仅重置尚无模型调用的初始化错误，其他既有模型失败保留。已有有效替换输出须与修正规则初值完全相同方可沿用。首个未完成场景四条件单轮全部通过才续跑；连续 3 个新条件失败则停止提交。" + str(run['bounds_recovery'])] if run.get('bounds_recovery') else []) +
        (["空响应类型兼容恢复：新异常类型此前漏识别，只补尚未用掉的原定一次恢复；原进程退出后串行执行，等待 8 秒，保留实际 wire seed。仅补失败轮次，不把成功前缀算作完整配对。" + str(run['empty_error_compat'])] if run.get('empty_error_compat') else []) +
        (["2026-10-22 凌晨续跑历史（已停止）：原30场景首轮检查通过，后续预算未覆盖每轮而失败。原记录：" + str(run['supplement_continuation'])] if run.get('supplement_continuation') else []) +
        (["2026-10-22 逐请求恢复修订：每轮 GPT 输出预算32768、回复16384，确认截断时该请求最多加倍一次；空响应/传输各最多恢复两次，同一请求与种子。原始失败留档，恢复执行故障，语义/结构化校验失败保留。先跑完整场景；单条件失败后继续队列。属于执行后修订，非原始预注册。" + str(run['reliable_continuation'])] if run.get('reliable_continuation') else []),
        ["web/experiment_catalog.py", "scripts/run_s0_mechanism_ablation.py"] +
        ([f"data/{run['run_id']}/summary.json", f"data/{run['run_id']}/manifest.json"] if run else [])))
    offline_rows = []
    for r in matrix.get("experiments", []):
        if "task" in r:
            e = r["evidence"]
            offline_rows.append([r["task"], e.get("items", "N/A"), e.get("media_pairs") if e.get("media_pairs") is not None else "N/A",
                e.get("missing_media") if e.get("missing_media") is not None else "N/A", "N/A", "N/A", "N/A", "未登记独立能力评测"])
    tables.append(make_table("offline-results", "T1–T3 材料覆盖与独立评测结果位置",
        ["任务", "文字题数", "媒体配对数", "缺媒体", "text 准确率", "text+video 准确率", "配对差值", "状态"], offline_rows,
        ["配对材料数不是已完成模型调用数。出题盲试答及机器参考答案检查不计为独立能力成绩。",
         "T2 当前媒体覆盖共同前史，共同 ending 仍为文字。"],
        ["tasks/examples/offline_scenarios_v2/manifest.json", "tasks/examples/offline_scenarios_v2/pairing_report.json"]))
    for run in live.get("t4_runs", []):
        accounting = run.get("execution_accounting", [])
        if accounting:
            execution_rows = []
            modes = {"native_video": "原生视频", "video_frames": "视频帧"}
            for row in accounting:
                mode = "文字" if row["condition"] == "text_only" else " / ".join(
                    modes[x] for x in row["transports"]) or "未记录"
                execution_rows.append([row["model"], row["condition"], mode,
                    row["planned"], row["recorded"], row["completed"], row["valid_scored"],
                    percent(row["completion_rate"]), row["failed"], row["unrecorded"],
                    row["unsupported"], row["missing_video"], row["delegated"],
                    row["duplicate_records"], row["conflicting_slots"]])
            tables.append(make_table(run["id"] + "-execution", run.get("title", run["id"]) + "：单次运行分母与输入方式",
                ["模型", "条件", "实际输入", "计划", "已记录", "完成", "有效评分", "完成率", "失败",
                 "尚无本批结果", "不支持", "未收到视频", "移交", "重复记录", "冲突槽位"], execution_rows,
                ["每个场景、模型、条件只运行一次。完成率 = 完成结果 / 冻结计划场景数，包含未完成和不支持槽位的原始分母。",
                 "完成包含未收到视频的已评分轨迹；有效视频评分要求实际送达。各维适用 n 仍见条件结果表。",
                 "按本目录 results.json 快照计数；尚无本批结果可能仍在运行或等待继承。重试、恢复与继承不增加独立样本，不跨目录求和。",
                 "相同槽位的完全相同副本只计一次；冲突槽位不选择优胜结果，不计入完成或有效评分，需核验后再解释成绩。",
                 "视频帧不含音频；原生视频的音频覆盖须另核验，不能仅凭传输名称认定三模态。"],
                [f"build/{run['id']}/run/plan.json", f"build/{run['id']}/run/results.json"]))
        scores, pairs, outcomes = [], [], []
        for model, values in run.get("models", {}).items():
            for condition, group in values.get("conditions", {}).items():
                scores.append([model, condition, *[score(group.get("metrics", {}).get(k)) for k in METRICS]])
            pairs.append([model, values.get("matched_scenarios", 0), *[score(values.get("paired_differences", {}).get(k), paired=True) for k in METRICS]])
            counts = values.get("status_counts", {})
            outcomes.append([model, *[counts.get(k, 0) for k in ("completed", "failed", "unsupported_video_input", "completed_without_video_exposure", "delegated_to_run", "source_unavailable")]])
        notes = [run.get("note", ""), f"Run: {run['id']}；记录状态：{run.get('reported_status', '未知')}。",
                 "机器评分未经人工校准；每维分别报告有效 n。恢复无机会及五维不完整为 N/A，不填零。"]
        sources = [f"build/{run['id']}/run/summary.json"]
        tables += [
            make_table(run["id"] + "-scores", run.get("title", run["id"]) + "：条件结果",
                       ["模型", "条件", *METRIC_LABELS], scores, notes, sources),
            make_table(run["id"] + "-paired", run.get("title", run["id"]) + "：同批配对差值",
                       ["模型", "配对场景", *METRIC_LABELS], pairs,
                       notes + ["差值 = text+video − text；仅同 run、同场景、同模型且视频实际送达的有效配对。95% CI 按已有摘要提供，不对缺失区间插值。"], sources),
            make_table(run["id"] + "-coverage", run.get("title", run["id"]) + "：运行覆盖与失败",
                       ["模型", "完成", "失败", "不支持视频", "未收到视频", "移交", "来源不可用"], outcomes,
                       notes + ["状态是槽位计数；移交、继承和技术恢复不是新增独立样本。"], sources),
        ]
    return tables
