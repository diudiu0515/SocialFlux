"""Generate and verify human-readable scenario projections and catalog metadata."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

VARIABLE_LABELS = {
    "anger": "愤怒",
    "anxiety": "焦虑",
    "hope": "希望",
    "resolve": "坚持推进意愿",
    "repair_intent": "关系修复意愿",
    "trust": "信任",
    "hostility": "敌意",
    "goal_failure_risk": "目标失败风险",
    "escalation_risk": "冲突升级风险",
    "negotiation_open": "协商开放度",
}


VARIABLE_LABELS.update({
    'irritation': '烦躁',
    'control_urge': '控制冲动',
    'openness': '接纳替代方案意愿',
    'professional_respect': '专业尊重',
    'schedule_pressure': '进度压力',
    'reputational_risk': '声誉风险',
    'grief': '悲伤',
    'fear': '恐惧',
    'protectiveness': '保护意愿',
    'compromise_readiness': '妥协准备度',
    'felt_respect': '被尊重感',
    'child_stability_risk': '儿童生活稳定风险',
    'legal_escalation_risk': '法律升级风险',
    'frustration': '挫败',
    'uncertainty': '不确定感',
    'moral_concern': '道德关切',
    'certainty_seeking': '确定性追求',
    'evidence_openness': '证据开放度',
    'credibility_trust': '专业可信度信任',
    'antagonism': '对立倾向',
    'consensus_pressure': '共识压力',
    'decision_error_risk': '错误决策风险',
    'deliberation_open': '审议开放度',
    'shame_threat': '羞耻威胁感',
    'resentment': '怨愤',
    'coalition_openness': '合作联盟开放度',
    'sibling_trust': '手足信任',
    'recognition': '被认可感',
    'donor_confidence_risk': '捐赠人信心风险',
    'governance_failure_risk': '治理失败风险',
    'moral_distress': '道德压力',
    'defensiveness': '防御感',
    'truth_commitment': '真相承诺',
    'denial_pressure': '否认压力',
    'expert_trust': '专业信任',
    'institutional_hostility': '制度性敌意',
    'public_harm_risk': '公共伤害风险',
    'accountability_risk': '问责风险',
    'panic': '惊慌',
    'change_resistance': '变革阻力',
    'shared_ownership': '共同承担意愿',
    'family_trust': '家人信任',
    'cashflow_risk': '现金流风险',
    'team_breakdown_risk': '团队崩解风险',
    'coordination_open': '协调开放度',
    'guilt': '内疚',
    'sadness': '难过',
    'loyalty_pressure': '忠诚压力',
    'honesty_readiness': '诚实披露准备度',
    'felt_judgment': '被评判感',
    'elder_distress_risk': '长辈痛苦风险',
    'family_cohesion_risk': '家庭凝聚风险',
    'conversation_open': '对话开放度',
    'threat_alert': '威胁警觉',
    'curiosity': '好奇',
    'action_urgency': '行动紧迫感',
    'interpretive_patience': '解释耐心',
    'distrust': '不信任',
    'crisis_escalation_risk': '危机升级风险',
    'data_fragmentation_risk': '数据碎片化风险',
    'envy': '嫉妒',
    'recognition_readiness': '承认贡献准备度',
    'friendship_trust': '友谊信任',
    'equity_dispute_risk': '股权争议风险',
    'company_stability_risk': '公司稳定风险',
    'disappointment': '失望',
    'institutional_loyalty': '机构忠诚',
    'moral_resolve': '道德决心',
    'mentor_trust': '导师信任',
    'professional_safety': '职业安全感',
    'client_harm_risk': '当事人伤害风险',
    'funding_collapse_risk': '资金崩溃风险',
    'dynamics': '互动动力',
})


def _flatten(values, prefix=""):
    rows = []
    for key, value in (values or {}).items():
        path = f"{prefix}.{key}" if prefix else key
        rows.extend(_flatten(value, path) if isinstance(value, dict) else [(path, value)])
    return rows


def _variable(path):
    leaf = path.split(".")[-1]
    return f"{VARIABLE_LABELS.get(leaf, leaf)} (`{path}`)"


def _state_table(values):
    lines = ["| 状态变量 | 初始值 |", "|---|---|"]
    lines.extend(f"| {_variable(path)} | {value} |" for path, value in _flatten(values))
    return lines


def _expression(expression):
    labels = {
        "facial_expression": "面部表情",
        "gaze": "视线",
        "speech_style": "说话方式",
        "prosody": "语气/韵律",
        "behavioral_cues": "行为线索",
    }
    lines = []
    for key, value in (expression or {}).items():
        rendered = "；".join(map(str, value)) if isinstance(value, list) else value
        lines.append(f"- {labels.get(key, key)}：{rendered}")
    return lines or ["- 未配置。"]


def _initialization_notes(notes):
    rationale = notes.get("rationale", {}) if isinstance(notes, dict) else {}
    reachability = notes.get("trigger_reachability", []) if isinstance(notes, dict) else []
    rationale_lines = [
        f"- {key}：{value}" for key, value in rationale.items()
    ] or ["- 未配置；需在人工 freeze 前补充。"]
    reachability_lines = [f"- {item}" for item in reachability] or [
        "- 未配置；需验证 S0 不触发且 episode horizon 内合理可达。"
    ]
    return rationale_lines, reachability_lines


def _mode_text(mode):
    return {
        "crossing": "前一轮尚未满足、当前轮首次满足全部阈值时触发",
        "threshold": "当前状态满足全部阈值时触发，并受冷却轮次限制",
        "state_change": "本轮变化量满足 change_conditions 时触发",
    }.get(mode, mode)


PROMPT_MANIFEST = Path(__file__).resolve().parents[1] / "prompts" / "manifest.json"


def scenario_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def discover_scenario_paths(directory):
    directory = Path(directory)
    return sorted(directory.glob("scenario_*/scenario_*.json"))


def render_scenario_document(scenario, source_name, source_hash):
    agent = scenario["environment_agent"]
    persona = agent.get("persona", {})
    role = scenario.get("evaluated_agent_role", {})
    source = scenario["source"]
    design = scenario["narrative_design"]
    status = scenario["construction_status"]
    media = scenario.get("media_generation", {})
    lines = [
        "<!-- AUTO-GENERATED BY scripts/scenario_docs.py; EDIT JSON THEN REGENERATE. -->",
        "",
        f"# {scenario['title']}",
        "",
        "## 文档身份与来源",
        "",
        f"- Scenario ID：`{scenario['scenario_id']}`",
        f"- 配对 JSON：`{source_name}`",
        f"- JSON SHA-256：`{source_hash}`",
        f"- 社会机制：{scenario['mechanism']}",
        f"- 来源类型：`{source['type']}`",
        f"- Provenance ID：`{source['provenance_id']}`",
        f"- 表层文本策略：`{source['surface_text_policy']}`",
        f"- 来源说明：{source.get('provenance_note', '未配置')}",
        "",
        "## 1. 叙事结构与初始化",
        "",
        f"故事背景：{scenario['background']}",
        "",
        f"关系结构：{design['relationship_structure']}",
        "",
        f"权力结构：{design['power_structure']}",
        "",
        f"目标冲突：{design['goal_conflict']}",
        "",
        f"信息不对称：{design['information_asymmetry']}",
        "",
        "### 相关历史",
        "",
        *[f"- {item}" for item in design["relevant_history"]],
        "",
        "### 非平凡选择空间",
        "",
        *[f"- {item}" for item in design["meaningful_choice_space"]],
        "",
        f"被评估角色：{role.get('name', role.get('character_id', '未配置'))}（`{role.get('character_id', 'unknown')}`）。",
        "",
        f"被评估角色公开目标：{role.get('explicit_goal', '未配置')}",
        "",
        f"环境角色：{persona.get('name', '未配置')} / {persona.get('role', '未配置')}。",
        "",
        f"环境角色显式目标（作者侧）：{agent['explicit_goal']}",
        "",
        f"隐藏意图（作者侧私有）：{agent['hidden_intention']}",
        "",
        f"最长互动：`{scenario['max_turns']}` 轮。",
        "",
        "### 初始 State（0–10）",
        "",
        f"状态：`{status['initial_state']}`。当前数值是候选配置；只有真实人工审核后才能标记为 human_frozen。",
        "",
        *_state_table(scenario["initial_state"]),
        "",
        "### 初始 Interaction Dynamics（0–10）",
        "",
        *_state_table(scenario["initial_dynamics"]),
        "",
        "### 初始化依据",
        "",
        *_initialization_notes(scenario.get("initialization_notes", {}))[0],
        "",
        "### Trigger 可达性",
        "",
        *_initialization_notes(scenario.get("initialization_notes", {}))[1],
        "",
        "### 重点预测状态",
        "",
        *[f"- {_variable(item)}" for item in scenario.get("target_state_ids", [])],
        "",
        "## 2. 自由交互与状态更新契约",
        "",
        "Scenario 只定义社会世界，不定义行动策略，也不预写任何 action→state 转移。",
        "",
        "正常 rollout 中，模型产生任意自然语言 action；同一个模型驱动环境按 persona、完整相关历史、S_t/D_t 和 action 独立完成 appraisal、语义 delta 与可观察回应。repair/neutral/escalation 不是 action taxonomy，也不得作为多轮数据生成策略。",
        "",
        "局部因果验证只能从真实自由轨迹 checkpoint 恢复相同 history/S_t/D_t，再注入若干自然语言替代 action；它不属于 scenario 定义。",
        "",
        "## 3. Talking Head / 视频生成",
        "",
        "### 默认外显表达",
        "",
        *_expression(scenario.get("observable_expression", {}).get("default", {})),
        "",
        "### 媒体生成配置",
        "",
        f"- 阶段：`{media.get('stage', '未配置')}`",
        f"- 默认媒体类型：`{media.get('default_media_type', '未配置')}`",
        f"- 资产状态：`{media.get('asset_status', '未配置')}`",
        f"- 资产根目录：`{media.get('asset_root', '未配置')}`",
        f"- 说明：{media.get('note', '未配置')}",
        "",
        "### 视频触发规则",
        "",
        "同一规则 conditions 按 AND 判断。阈值与 trigger ID 仅进入私有 trajectory；公开 observation 只获得安全的 expression/media spec。",
        "",
    ]
    for trigger in scenario.get("video_triggers", []):
        mode = trigger.get("trigger_mode", "crossing")
        lines.extend([
            f"#### `{trigger['trigger_id']}`",
            "",
            f"触发模式：`{mode}`，即{_mode_text(mode)}。",
            "",
            "阈值条件：",
            "",
        ])
        lines.extend(
            f"- {_variable(variable)} {condition.get('operator')} `{condition.get('threshold')}`"
            for variable, condition in trigger.get("conditions", {}).items()
        )
        lines.extend([
            "",
            f"冷却 `{trigger.get('cooldown_turns', 0)}` 轮；媒体 `{trigger.get('media_type', 'video')}`；时长 `{trigger.get('duration_seconds', 4)}` 秒。",
            "",
            "触发后的外显表达：",
            "",
            *_expression(trigger.get("observable_expression", {})),
            "",
        ])
    gate = scenario["quality_gate"]
    lines.extend([
        "## 4. 构建与质量门禁",
        "",
        f"- Normalization：`{status['normalization']}`",
        f"- Scenario quality gate：`{status['quality_gate']}`",
        f"- 待审核项：`{sum(value == 'pending' for value in gate.values())}` / `{len(gate)}`",
        f"- T1/T2/T3 候选上限：`{scenario.get('sampling_plan', {}).get('t1_max', '未配置')}` / `{scenario.get('sampling_plan', {}).get('t2_max', '未配置')}` / `{scenario.get('sampling_plan', {}).get('t3_max', '未配置')}`",
        f"- T3 delayed horizon：`{scenario.get('t3_delayed_horizon', '未配置')}`",
        "",
        "```bash",
        f"python scripts/scenario_docs.py configs/scenarios/{Path(source_name).stem}/{source_name}",
        "python -m scripts.run_pipeline --rollout-config configs/rollout_pool.example.json",
        "```",
        "",
        "自由模型 rollout 生成后与本场景放在 `rollouts/`；`dialogues.md` 是可读投影，manifest 和逐 trajectory JSON 是私有研究产物。",
        "",
    ])
    return "\n".join(lines)


def expected_document(json_path):
    json_path = Path(json_path)
    scenario = json.loads(json_path.read_text(encoding="utf-8"))
    return render_scenario_document(scenario, json_path.name, scenario_hash(json_path))


def write_document(json_path):
    json_path = Path(json_path)
    output = json_path.with_suffix(".md")
    output.write_text(expected_document(json_path), encoding="utf-8")
    return output


def assert_document_current(json_path):
    json_path = Path(json_path)
    output = json_path.with_suffix(".md")
    if not output.exists():
        raise ValueError(f"scenario documentation missing: {output}")
    if output.read_text(encoding="utf-8") != expected_document(json_path):
        raise ValueError(f"scenario documentation is stale: {output}")
    return output


def _scenario_rows(directory):
    for path in discover_scenario_paths(directory):
        yield path, json.loads(path.read_text(encoding="utf-8"))


def manifest_payload(directory):
    directory = Path(directory)
    rows = list(_scenario_rows(directory))
    source_counts = Counter(scenario["source"]["type"] for _, scenario in rows)
    scenarios = [
        {
            "scenario_id": scenario["scenario_id"],
            "title": scenario["title"],
            "mechanism": scenario["mechanism"],
            "source_type": scenario["source"]["type"],
            "quality_gate": scenario["construction_status"]["quality_gate"],
            "initial_state_status": scenario["construction_status"]["initial_state"],
            "source": path.relative_to(directory).as_posix(),
            "scenario_sha256": scenario_hash(path),
            "documentation": path.with_suffix(".md").relative_to(directory).as_posix(),
            "documentation_sha256": scenario_hash(path.with_suffix(".md")),
            "rollouts": (path.parent / "rollouts").relative_to(directory).as_posix(),
        }
        for path, scenario in rows
    ]
    return {
        "format": "socialflux_scenario_manifest_v2",
        "scenario_count": len(scenarios),
        "prompt_manifest_sha256": scenario_hash(PROMPT_MANIFEST),
        "source_counts": dict(sorted(source_counts.items())),
        "scenarios": scenarios,
    }


def coverage_payload(directory):
    rows = list(_scenario_rows(directory))
    return {
        "format": "socialflux_scenario_coverage_v1",
        "dimensions": [
            "relationship_type",
            "social_mechanism",
            "power_asymmetry",
            "goal_conflict",
            "information_asymmetry",
            "temporal_history_pattern",
            "relevant_state_families",
            "repair_possibility",
            "failure_mode",
            "scenario_source",
        ],
        "rows": [
            {
                "scenario_id": scenario["scenario_id"],
                "relationship_type": scenario["narrative_design"]["relationship_structure"],
                "social_mechanism": scenario["mechanism"],
                "power_asymmetry": scenario["narrative_design"]["power_structure"],
                "goal_conflict": scenario["narrative_design"]["goal_conflict"],
                "information_asymmetry": scenario["narrative_design"]["information_asymmetry"],
                "temporal_history_pattern": scenario["narrative_design"]["relevant_history"],
                "relevant_state_families": sorted(scenario.get("selected_state_variables", {})),
                "repair_possibility": "human_review_pending",
                "failure_mode": "human_review_pending",
                "scenario_source": scenario["source"]["type"],
            }
            for _, scenario in rows
        ],
    }


def _write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_catalog(directory):
    directory = Path(directory)
    _write_json(directory / "manifest.json", manifest_payload(directory))
    _write_json(directory / "coverage_matrix.json", coverage_payload(directory))


def assert_manifest_current(directory):
    directory = Path(directory)
    expected = {
        directory / "manifest.json": manifest_payload(directory),
        directory / "coverage_matrix.json": coverage_payload(directory),
    }
    for path, payload in expected.items():
        rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if not path.exists() or path.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"scenario catalog artifact is missing or stale: {path}")
    source_counts = expected[directory / "manifest.json"]["source_counts"]
    if not source_counts.get("narrative-derived") or not source_counts.get("synthetic-script"):
        raise ValueError("scenario catalog must contain both source types")
    return directory / "manifest.json"


def main():
    parser = argparse.ArgumentParser(description="Generate paired scenario docs and catalog")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    catalog = Path("configs/scenarios")
    paths = args.paths or discover_scenario_paths(catalog)
    if not paths:
        parser.error("no bundled scenario JSON files found")
    for path in paths:
        output = assert_document_current(path) if args.check else write_document(path)
        print(f"{'checked' if args.check else 'generated'} {output}")
    directories = {
        path.parent.parent if path.parent.name.startswith("scenario_") else path.parent
        for path in paths
    }
    for directory in sorted(directories):
        manifest = assert_manifest_current(directory) if args.check else None
        if not args.check:
            write_catalog(directory)
            manifest = directory / "manifest.json"
        print(f"{'checked' if args.check else 'generated'} {manifest}")
        print(f"{'checked' if args.check else 'generated'} {directory / 'coverage_matrix.json'}")


if __name__ == "__main__":
    main()
