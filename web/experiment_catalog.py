"""Research matrix and file inventory. Reading it never launches an experiment."""
import hashlib
import json
from pathlib import Path

from web.experiment_status import E_NAMES
from web.experiment_protocols import GATE2_PROTOCOLS, GATE2_RELATION, S0_STATUS_LABELS

REPORT = "reports/experiments/2026-10-21_experiment_matrix.md"
BANK = "tasks/examples/offline_scenarios_v2"


def definitions():
    rows = []
    for task in ("T1", "T2", "T3"):
        rows.append(dict(
            id="study-" + task.lower(), title=f"{task} · text / text+video", category="T1–T3",
            group="主实验", conditions=["text_only", "text_video"], target="当前新版题库，按同题配对",
            hypothesis=f"比较 {task} 在文字和文字＋视频条件下的表现。",
            method="同题干、选项、模型与采样设置；按题目版本及媒体 SHA 绑定两条件。按任务、模型和条件分别统计。"
                   + ("T2 当前视频仅覆盖共同前史，共同 ending 仍为文字，需单列覆盖限制。" if task == "T2" else ""),
            acceptance="独立评测调用、答案来源、有效配对 n、失败和缺媒体分母齐全；报告准确率及同题差值。机器候选与人工 GT 分开。",
            next_step="冻结评测模型与题库版本，补齐人工 GT 后执行独立 text / text+video 评测。",
            sources=[REPORT, f"{BANK}/manifest.json", f"{BANK}/items.jsonl", f"{BANK}/pairing_report.json",
                     f"{BANK}/paired.items.jsonl", f"{BANK}/media.json"], task=task))
    rows += [
        dict(id="study-t4", title="T4 · text / text+video", category="T4", group="主实验",
             conditions=["text_only", "text_video"], target="各 run 保留自己的场景与模型分母",
             hypothesis="比较在线交互中视频线索对目标达成、状态适应、风险、恢复和关系的作用。",
             method="每个场景、模型、条件只运行一次；同 run、同场景、同模型做配对。按模型能力使用原生视频或视频帧，记录实际输入和媒体送达；重试、断点恢复及继承不计新增独立样本。",
             acceptance="按 run 展示五维分数、各维 n、配对差值及区间，并列计划分母、完成率、失败、未完成、不支持与缺视频；无恢复机会为 N/A，历史评分与诊断样本单列。",
             next_step="核对停止原因与媒体送达，补齐同批配对并进行评分人工校准。",
             sources=[REPORT, "reports/experiments/2026-10-21_t4_continuation.md"]),
        dict(id="study-t4-caption", title="T4 · video 的 text caption 对照", category="T4", group="主实验",
             conditions=["text_only", "text_video", "text_caption"], target="复用同一 T4 场景、模型和媒体节点",
             hypothesis="检验视频收益能否由可观察线索的文字描述解释。",
             method="第三条件为原文字输入＋同一段视频内容描述，不传视频。caption 仅写可见表情、动作、姿态等；"
                    "按实际可见媒体范围生成，记录视频 SHA、时间段、生成版本和人工复核。不得从隐藏 state、渲染提示或参考答案反推描述。",
             acceptance="三条件输入对齐；caption 不增加事实、不泄漏私有状态。分别报告 caption−text、video−text、video−caption 的同批配对差值及 n。",
             next_step="生成并复核视频内容 caption，接入独立第三条件后运行三条件对照。",
             sources=[REPORT]),
        dict(id="study-s0-sensitivity", title="Gate2 S1 · 初始状态敏感性（替换 S0）", category="Gate 2", group="Gate2 补充消融",
             supplement_id="S1", related_gates=["E7"],
             conditions=["original_s0", "replaced_s0"], target="约 30 个场景；每场景两条件", target_scenarios=30,
             hypothesis="检查环境对初始状态 S0 的变化是否产生可解释的响应。",
             method="与 E7 人格干预同属初始环境干预。按场景 ID 哈希从可读来源固定抽 30 场景，数值 S0 各变量确定性 ±2，在初始化允许的 [1,9] 内越界反向，D0 不变。"
                    "固定原始历史、行动和 ledger，逐轮累积各条件自己的状态；覆盖来源所有可用轮次，生成回复但不回填历史。"
                    "原 S0、原 S0 重复、替换 S0 均正常更新；本轮为多变量联合扰动，不代表单维消融或自由 T4。",
             acceptance="冻结场景清单和替换规则；保存状态轨迹、响应差异、有效配对 n 与失败原因。不得将 Gate2 E6 骨干替换计作本实验结果。",
             next_step="沿用同一 30 场景并保留失败，对照重复基线报告状态与回复差异、完整配对及执行覆盖；本轮采用机器统计，不加入人工标注任务。",
             sources=[REPORT, "scripts/run_s0_mechanism_ablation.py", "scripts/resume_gate2_supplements.py"]),
        dict(id="study-state-update-ablation", title="Gate2 S2 · 显式状态更新消融（始终 S0）", category="Gate 2", group="Gate2 补充消融",
             supplement_id="S2", related_gates=["E1", "E9"],
             conditions=["dynamic_state", "fixed_s0_no_update_prompt"], target="约 30 个场景；与 S0 敏感性共用集合", target_scenarios=30,
             hypothesis="比较正常显式状态更新与固定初始状态环境的行为差异。",
             method="与 S1 共用 30 场景及动态基线；每轮固定 S0 和 D0，移除状态更新 prompt（state appraisal 调用）、校准器及 interaction 输入中的 update_policy。"
                    "保留交互分析和回复生成；固定原始历史、行动和 ledger。逐轮核验状态不变且 state 请求文件数为 0；该固定历史回放不计作 T4。",
             acceptance="逐轮核验 state == S0、更新调用数为 0、无更新 prompt；保存 prompt 差异、响应、质量指标、配对 n 与失败。"
                        "该对照同时去掉更新机制和更新指令，结论按组合消融解释。",
             next_step="继续全部来源轮次，核验固定状态与零更新调用；报告组合消融、执行失败及完整配对数。本轮不要求人工判读，也不阻塞标注发放。",
             sources=[REPORT, "scripts/run_s0_mechanism_ablation.py", "scripts/resume_gate2_supplements.py"]),
    ]
    for i, name in enumerate(E_NAMES, 1):
        protocol = GATE2_PROTOCOLS[f"E{i}"]
        rows.append(dict(id=f"study-gate2-e{i}", title=f"Gate2 E{i} · {name}", category="Gate 2",
                         group="Gate2 核心验证", gate_id=f"E{i}", conditions=[protocol["kind"]], target=protocol["target"],
                         hypothesis=protocol["hypothesis"], method=protocol["method"], measurement=protocol["measurement"],
                         acceptance=protocol["acceptance"], human_required=protocol["human_required"],
                         next_step="复核机器未通过项及回放失败，按当前阈值重新验证。" if i == 6 else "复核当前机器结果、失败及人工证据缺口。",
                         sources=[REPORT, "reports/experiments/2026-10-20_gates_and_results.md"]))
    return rows


def planned_records(stamp):
    for row in definitions():
        yield dict(id=row["id"], title=row["title"], category=row["category"], priority="P0",
                   status="planned", owner="", due_date="", hypothesis=row["hypothesis"],
                   method=row["method"], acceptance=row["acceptance"],
                   notes="本轮整合的研究计划。目标规模：" + row["target"] + "。" + row["next_step"]
                         + " 实际数据状态见实验矩阵，计划状态单独维护。",
                   sources=row["sources"], metrics=[], origin="research_matrix_20261021",
                   created_at=stamp, updated_at=stamp, revision=1)


def gate_summary(evidence):
    record = evidence.get("machine_record", {})
    partial = evidence.get("raw_partial")
    if partial:
        result = f"已执行 {partial['records']}；机器筛查通过 {partial['screen_passed']}"
        if evidence["id"] == "E4":
            result += f"；活跃变量方向一致率 {record.get('active_union_direction_agreement', 'N/A')}"
        return result
    if evidence.get("id") == "E6":
        return (f"双模型回放 {record.get('matched_checkpoint_count', 0)}；有效 {record.get('successful_matched_checkpoint_count', 0)}；"
                f"方向一致率 {record.get('mean_active_union_direction_agreement', 'N/A')}；失败 {record.get('replay_failure_count', 0)}")
    if evidence.get("id") == "E8":
        return (f"视频节点检查 {record.get('machine_reviewed_nodes', 0)}；可见检查全部通过 {record.get('visual_passed_nodes', 0)}；"
                "音频语义另行复核")
    return f"人工证据包 {evidence.get('review_items', 0)} 项；人工签署：" + ("已签署" if evidence.get("human_attestation") else "待完成")


def load_matrix(root, live, records):
    """Return allowlisted aggregates and metadata, never raw state/GT or calls."""
    root = Path(root)
    errors = []
    inventory = {}

    def register(relative):
        if relative in inventory:
            return inventory[relative]
        row = dict(path=relative, status="missing", bytes=None, sha256=None, experiments=[])
        try:
            path = root / relative
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("source outside project")
            if path.is_file():
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                row.update(status="available", bytes=path.stat().st_size, sha256=digest.hexdigest())
        except (OSError, ValueError) as exc:
            row["status"] = "unreadable"
            errors.append({"path": relative, "error": type(exc).__name__})
        inventory[relative] = row
        return row

    pairing = {}
    pair_source = register(f"{BANK}/pairing_report.json")
    if pair_source["status"] == "available":
        try:
            pairing = json.loads((root / pair_source["path"]).read_text())
            if not isinstance(pairing, dict):
                raise ValueError("invalid pairing report")
        except (OSError, ValueError) as exc:
            errors.append({"path": pair_source["path"], "error": type(exc).__name__})
            pairing = {}
    items_source = register(f"{BANK}/items.jsonl")
    pairing_current = bool(pairing.get("items_sha256") and pairing["items_sha256"] == items_source["sha256"])
    offline = (live or {}).get("offline", {})
    gates = {e["id"]: e for g in (live or {}).get("gates", []) if g["id"] == "Gate 2" for e in g.get("experiments", [])}
    plans = {r["id"]: r for r in records}
    rows = []
    for definition in definitions():
        row = dict(definition, plan_status=plans.get(definition["id"], {}).get("status", "planned"),
                   evidence_status="planned", evidence_summary="尚未登记本实验的独立运行结果。", evidence={}, run_ids=[])
        paths = list(row["sources"])
        if "task" in row:
            task = row["task"]
            count = offline.get("tasks", {}).get(task)
            paired = pairing.get("paired_by_task", {}).get(task, 0) if pairing_current else None
            row.update(evidence_status="materials_ready" if count else "unavailable",
                       evidence_summary=f"题库 {count if count is not None else 'N/A'} 题；有效媒体配对 {paired if paired is not None else '待重新绑定'}；独立能力评测待登记。",
                       evidence=dict(items=count, media_pairs=paired, missing_media=(count-paired) if count is not None and paired is not None else None,
                                     pairing_current=pairing_current, independent_evaluation_registered=False))
        elif row["id"] == "study-t4":
            runs = (live or {}).get("t4_runs", [])
            row.update(evidence_status="results_available" if runs else "unavailable",
                       evidence_summary=f"已登记 {len(runs)} 个 run；各自保留模型、条件、有效配对与失败分母。",
                       run_ids=[r["id"] for r in runs])
            paths += [f"build/{r['id']}/run/{name}" for r in runs
                      for name in (("summary.json", "all_results.json", "manifest.json") if r.get("kind") == "historical_scoring"
                                   else ("summary.json", "results.json", "status.json"))]
        elif "gate_id" in row:
            e = gates.get(row["gate_id"], {})
            row.update(evidence_status="machine_evidence" if e.get("evidence_present") else "unavailable",
                       evidence_summary=gate_summary(e) if e else "当前批次证据暂不可读。", evidence=e)
            if e.get("source"):
                paths.append(e["source"])
            followup = (live or {}).get('gate2_followup')
            if followup and row['gate_id'] in ('E3', 'E4'):
                condition = 'recent3' if row['gate_id'] == 'E3' else 'paraphrase'
                result = followup.get('comparisons', {}).get(condition, {})
                row['evidence_summary'] += (f"；独立补测 {followup.get('recorded', 0)}/46 场景已记录，"
                    f"{condition} 有效配对 {result.get('pairs', 0)}；状态 {followup.get('status')}（详见补测表）")
                row['run_ids'].append(followup['run_id'])
                row['next_step'] = '在 annotation 页完成场景与环境核对；补测和旧批次分别保留，人工核验前不标记正式通过。'
                paths += [f"data/{followup['run_id']}/summary.json", f"data/{followup['run_id']}/manifest.json"]
        elif row.get("supplement_id") and (live or {}).get("s0_ablation"):
            run = live["s0_ablation"]
            comparison = "replaced_s0" if row["supplement_id"] == "S1" else "fixed_s0_no_update_prompt"
            pair = run.get("pairs", {}).get(comparison, {})
            row.update(evidence_status=run.get("status", "unavailable"), evidence=run,
                evidence_summary=f"{S0_STATUS_LABELS.get(run.get('status'), run.get('status'))}；完整场景配对 {pair.get('n', 0)}/{run.get('target_scenarios', 30)}；"
                                 f"累计保存条件轮次 {run.get('saved_turns', 0)}；本轮采用机器统计，不纳入人工任务。",
                run_ids=[run["run_id"]])
            paths += [f"data/{run['run_id']}/{name}" for name in ("manifest.json", "summary.json", "process.json")]
            if run.get('transport_recovery'):
                paths.append(f"data/{run['run_id']}/recovery.json")
            if run.get('prompt_audit'):
                paths.append(f"data/{run['run_id']}/prompt_ablation_audit.json")
            if run.get('diagnostics'):
                paths += [f"data/{run['run_id']}/{name}" for name in ('diagnostic_status.json','s0_bounds_preflight.json')]
            if run.get('bounds_recovery'):
                paths.append(f"data/{run['run_id']}/bounds_recovery.json")
            if run.get('empty_error_compat'):
                paths.append(f"data/{run['run_id']}/empty_error_compat.json")
            if run.get('supplement_continuation'):
                paths += [f"data/{run['run_id']}/supplement_continuation_20261022.json",
                          f"data/{run['run_id']}/continuation_20261022/manifest.json"]
        if live is None and ("task" in row or "gate_id" in row or row["id"] == "study-t4"):
            row.update(evidence_status="unavailable", evidence_summary="实时摘要暂不可读，请稍后刷新。")
        row["sources"] = list(dict.fromkeys(paths))
        for path in row["sources"]:
            if path != REPORT:  # Generated report is an output, not its own input.
                register(path)["experiments"].append(row["id"])
        rows.append(row)
    return dict(schema="socialflux_research_matrix_v1", experiments=rows, inventory=list(inventory.values()),
                read_errors=errors, historical_gate2=(live or {}).get("historical_gate2"),
                gate2_relation=GATE2_RELATION,
                note="目标样本量是计划值。数据状态来自原始摘要，计划状态可手动维护；二者不互相替代。")
