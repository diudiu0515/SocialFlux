const $ = id => document.getElementById(id);
const PREFIX = "socialflux-state-annotation:";
const NEW_JUDGMENTS = new Set([
  "ordinary_new_evidence",
  "decisive_new_evidence",
]);
const JUDGMENT_OPTIONS = [
  ["no_relevant_evidence", "无相关证据"],
  ["repeated_evidence_only", "仅重复证据"],
  ["ordinary_new_evidence", "普通新增证据"],
  ["decisive_new_evidence", "决定性新增证据"],
];
const FIELD_LABELS = {
  definition: "变量定义",
  increase_evidence: "支持增加的证据",
  decrease_evidence: "支持减少的证据",
  non_evidence: "不构成证据",
  timescale: "时间尺度",
  update_rule: "转换规则",
  scenario_initialization_rationale: "当前初始判断依据",
  scenario_transition_evidence: "本场景的方向示例",
  persona: "人物性格",
  explicit_goal: "公开目标",
  hidden_intention: "私有动机",
  name: "姓名",
  role: "身份",
  relationship_structure: "关系结构",
  power_structure: "权力结构",
  goal_conflict: "目标冲突",
  information_asymmetry: "信息差",
  relevant_history: "相关前史",
  meaningful_choice_space: "有效选择空间",
};

let packet;
let draft = {reviewer: "", annotations: {}};
let activeRecord = 0;
let activeTarget = 0;

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function storageKey() {
  return PREFIX + packet.packet_sha256;
}

function save() {
  draft.reviewer = $("reviewer").value.trim();
  localStorage.setItem(storageKey(), JSON.stringify(draft));
  renderProgress();
}

function loadDraft() {
  const raw = localStorage.getItem(storageKey());
  if (raw) {
    try {
      draft = JSON.parse(raw);
    } catch {
      draft = {reviewer: "", annotations: {}};
    }
  }
  draft.annotations ||= {};
  $("reviewer").value = draft.reviewer || "";
}

function annotation(target) {
  return {
    ...structuredClone(target.human_annotation),
    ...(draft.annotations[target.annotation_id] || {}),
  };
}

function setAnnotation(target, value) {
  draft.annotations[target.annotation_id] = value;
  save();
}

function allTargets() {
  return packet.records.flatMap(record => record.targets);
}

function renderProgress() {
  if (!packet) return;
  const targets = allTargets();
  const done = targets.filter(target => annotation(target).status === "complete").length;
  $("progress").textContent =
    `进度 ${done}/${targets.length} · ${packet.summary.record_count} 条 rollout / ` +
    `${packet.summary.complete_rollout_turn_count} 轮历史`;
}

function addMeta(parent, label, value) {
  const box = el("div");
  box.append(el("div", "label", label), humanValue(value));
  parent.append(box);
}
function fieldLabel(key) {
  return FIELD_LABELS[key] || key.replaceAll("_", " ");
}

function humanValue(value) {
  if (value == null || value === "") return el("span", "muted", "—");
  if (["string", "number", "boolean"].includes(typeof value)) {
    return el("div", "value", String(value));
  }
  if (Array.isArray(value)) {
    if (!value.length) return el("span", "muted", "无");
    const list = el("ul", "human-list");
    value.forEach(item => {
      const entry = el("li");
      entry.append(humanValue(item));
      list.append(entry);
    });
    return list;
  }
  const fields = el("div", "human-fields");
  Object.entries(value).forEach(([key, item]) => {
    const row = el("div", "human-field");
    row.append(el("div", "field-name", fieldLabel(key)), humanValue(item));
    fields.append(row);
  });
  return fields;
}


function numericTable(title, groups) {
  const card = el("section", "card compact-card");
  card.append(el("h3", "", title));
  Object.entries(groups || {}).forEach(([family, values]) => {
    card.append(el("div", "family-name", fieldLabel(family)));
    const table = el("div", "score-table");
    Object.entries(values || {}).forEach(([name, score]) => {
      const row = el("div", "score-row");
      row.append(
        el("span", "score-name", fieldLabel(name)),
        el("strong", "score-value", score),
      );
      table.append(row);
    });
    card.append(table);
  });
  return card;
}
function renderNav() {
  const nav = $("recordNav");
  nav.replaceChildren();
  packet.records.forEach((record, index) => {
    const done = record.targets.filter(
      target => annotation(target).status === "complete"
    ).length;
    const button = el(
      "button",
      index === activeRecord ? "active" : "",
      `${index + 1}. ${record.scenario_id} · ${record.turn_count}轮\n` +
      `${done}/${record.target_count} 已确认`,
    );
    button.onclick = () => {
      activeRecord = index;
      activeTarget = 0;
      render();
    };
    nav.append(button);
  });
}

function renderScenario(record) {
  const root = $("scenario");
  root.replaceChildren(
    el("h2", "", `${record.scenario.title} · ${record.scenario_id}`),
    el("p", "muted", `Scenario: ${record.scenario_path} · Rollout: ${record.rollout_path}`),
  );
  const grid = el("div", "meta-grid");
  addMeta(grid, "背景", record.scenario.background);
  addMeta(grid, "机制", record.scenario.mechanism);
  addMeta(grid, "环境角色", record.scenario.environment_agent);
  addMeta(grid, "被测角色", record.scenario.evaluated_agent_role);
  addMeta(grid, "关系、冲突与前史", record.scenario.narrative_design);
  root.append(grid);
  const raw = el("details");
  raw.append(el("summary", "", "完整 scenario JSON"), el("pre", "", JSON.stringify(record.scenario, null, 2)));
  root.append(raw);
}

function renderTargets(record) {
  const root = $("targets");
  root.replaceChildren(el("h2", "", "必标 turn"));
  const tabs = el("div", "target-tabs");
  record.targets.forEach((target, index) => {
    const ann = annotation(target);
    const button = el(
      "button",
      index === activeTarget ? "active" : "",
      `${target.turn_id} · ${target.variable} · ` +
      `${ann.status === "complete" ? "已确认" : "待确认"}`,
    );
    button.onclick = () => {
      activeTarget = index;
      render();
    };
    tabs.append(button);
  });
  root.append(tabs);
  const target = record.targets[activeTarget];
  const semantics = el("div", "card semantics");
  semantics.append(el("h3", "", `当前 v7 变量定义 · ${target.variable}`));
  const grid = el("div", "meta-grid");
  Object.entries(target.variable_semantics)
    .filter(([key]) => !["evidence_features", "timescale_source"].includes(key))
    .forEach(([key, value]) => addMeta(grid, fieldLabel(key), value));
  semantics.append(grid);
  root.append(semantics);
}

function actionText(action) {
  return typeof action === "string" ? action : action?.text || "";
}

function renderDialogue(record) {
  const root = $("dialogue");
  const target = record.targets[activeTarget];
  const targetIndex = record.turns.findIndex(turn => turn.turn_id === target.turn_id);
  const visibleTurns = record.turns.slice(0, targetIndex + 1);
  root.replaceChildren(
    el("h2", "", "可用于判断的历史与当前动作"),
    el(
      "p",
      "muted",
      `只展示到 ${target.turn_id} 的 policy_action。该轮环境回应和之后 ` +
      `${record.turns.length - targetIndex - 1} 轮不会展示，也不得用于标签。`,
    ),
  );
  visibleTurns.forEach((turn, index) => {
    const isTarget = index === targetIndex;
    const box = el("article", `turn ${isTarget ? "target" : ""}`);
    const head = el("div", "turn-head");
    head.append(
      el("span", "", turn.turn_id),
      el("span", "", isTarget ? "当前待标动作" : "此前历史"),
    );
    box.append(
      head,
      el("div", "speaker", "evaluated_agent / policy_action"),
      el("div", "value", actionText(turn.policy_action)),
    );
    if (!isTarget) {
      box.append(
        el("div", "speaker environment", "environment_agent / response"),
        el("div", "value", turn.environment_response || ""),
      );
    } else {
      box.append(el("div", "muted", "目标动作之后的 environment response 已隐藏。"));
      const context = el("section", "context-section");
      context.append(el("h3", "", "目标动作发生前的状态与记忆"));
      const scoreGrid = el("div", "context-grid");
      scoreGrid.append(
        numericTable("State（0–10）", turn.state_before),
        numericTable("Dynamics（0–10）", {dynamics: turn.dynamics_before}),
      );
      context.append(scoreGrid);
      const memoryGrid = el("div", "meta-grid context-meta");
      addMeta(memoryGrid, "历史摘要", turn.memory_view?.memory_summary);
      addMeta(memoryGrid, "相关历史轮次", turn.memory_view?.relevant_turn_ids);
      addMeta(memoryGrid, "尚未解决事项", turn.memory_view?.important_unresolved_events);
      addMeta(memoryGrid, "纵向上下文", turn.observation?.longitudinal_context);
      context.append(memoryGrid);
      const ledger = turn.interaction_ledger_before || {};
      const ledgerGrid = el("div", "meta-grid context-meta");
      addMeta(ledgerGrid, "已确立事实", ledger.established_facts);
      addMeta(ledgerGrid, "活跃提案", ledger.active_proposals);
      addMeta(ledgerGrid, "承诺", ledger.commitments);
      addMeta(ledgerGrid, "未解决线索", ledger.unresolved_threads);
      addMeta(ledgerGrid, "最新义务", ledger.latest_obligation);
      addMeta(ledgerGrid, "互动进度", ledger.progress);
      context.append(ledgerGrid);
      const raw = el("details");
      raw.append(
        el("summary", "", "原始更新前上下文 JSON（仅供核查）"),
        el("pre", "", JSON.stringify({
          state_before: turn.state_before,
          dynamics_before: turn.dynamics_before,
          memory_view: turn.memory_view,
          interaction_ledger_before: turn.interaction_ledger_before,
          longitudinal_context: turn.observation?.longitudinal_context,
        }, null, 2)),
      );
      context.append(raw);
      box.append(context);
    }
    root.append(box);
  });
}

function selectField(label, value, options, onchange, wide = false) {
  const wrap = el("label", wide ? "wide" : "");
  wrap.append(document.createTextNode(label));
  const select = el("select");
  select.append(new Option("— 请选择 —", ""));
  options.forEach(option => {
    const [optionValue, optionLabel] = Array.isArray(option)
      ? option
      : [option, option];
    select.append(new Option(optionLabel, optionValue));
  });
  select.value = value ?? "";
  select.onchange = () => onchange(select.value || null);
  wrap.append(select);
  return wrap;
}

function textField(label, value, onchange) {
  const wrap = el("label", "wide");
  wrap.append(document.createTextNode(label));
  const area = el("textarea");
  area.value = value || "";
  area.oninput = () => onchange(area.value);
  wrap.append(area);
  return wrap;
}

function validationErrors(ann) {
  const errors = [];
  if (!ann.judgment) errors.push("请选择四类判断");
  const isNew = NEW_JUDGMENTS.has(ann.judgment);
  if (isNew && !ann.direction) errors.push("新增证据需要方向");
  if (isNew && !ann.directness) errors.push("新增证据需要 directness");
  if (isNew && !String(ann.evidence_span || "").trim()) {
    errors.push("新增证据需要复制目标动作中的原文");
  }
  if (!String(ann.rationale || "").trim()) errors.push("需要一句变量特定依据");
  if (!ann.confidence_1_to_5) errors.push("请选择置信度");
  if (!ann.label_is_ambiguous) errors.push("请选择标签是否有歧义");
  if (ann.label_is_ambiguous === "yes" && !String(ann.ambiguity_note || "").trim()) {
    errors.push("有歧义时需要填写说明");
  }
  return errors;
}

function renderAnnotation(record) {
  const root = $("annotation");
  root.replaceChildren();
  const target = record.targets[activeTarget];
  let ann = annotation(target);
  root.append(el("h2", "", `人工标签 · ${target.annotation_id}`));
  const card = el("div", "annotation-card");
  const status = el("div", "status-line");
  status.append(
    el("span", "", `目标：${target.turn_id} / ${target.variable}`),
    el(
      "span",
      `badge ${ann.status === "complete" ? "good" : "warn"}`,
      ann.status === "complete" ? "已确认" : "待确认",
    ),
  );
  card.append(status);

  const update = (name, value, rerender = false) => {
    ann = {...ann, [name]: value, status: "pending"};
    if (name === "judgment" && !NEW_JUDGMENTS.has(value)) {
      ann = {...ann, direction: null, directness: null, evidence_span: ""};
    }
    setAnnotation(target, ann);
    if (rerender) render();
  };
  const grid = el("div", "form-grid");
  grid.append(selectField("逐变量判断", ann.judgment, JUDGMENT_OPTIONS, value => update("judgment", value, true), true));
  if (NEW_JUDGMENTS.has(ann.judgment)) {
    grid.append(
      selectField("方向", ann.direction, [["increase", "增加"], ["decrease", "减少"]], value => update("direction", value)),
      selectField("Directness", ann.directness, [["direct", "直接"], ["indirect", "间接"]], value => update("directness", value)),
      textField("目标 action 中的精确证据原文", ann.evidence_span, value => update("evidence_span", value)),
    );
  }
  grid.append(
    textField("一句依据：本轮改变了环境角色此前哪项顾虑或判断", ann.rationale, value => update("rationale", value)),
    selectField("置信度", ann.confidence_1_to_5, [1, 2, 3, 4, 5], value => update("confidence_1_to_5", value ? Number(value) : null)),
    selectField("标签是否有歧义", ann.label_is_ambiguous, [["yes", "有歧义"], ["no", "无歧义"]], value => update("label_is_ambiguous", value, true)),
  );
  if (ann.label_is_ambiguous === "yes") {
    grid.append(textField("歧义说明", ann.ambiguity_note, value => update("ambiguity_note", value)));
  }
  grid.append(textField("其他审核备注", ann.reviewer_note, value => update("reviewer_note", value)));
  card.append(grid);

  const confirm = el("button", "confirm-button", "校验并确认本例");
  confirm.onclick = () => {
    const errors = validationErrors(ann);
    if (errors.length) {
      alert(errors.join("\n"));
      return;
    }
    ann = {...ann, status: "complete"};
    setAnnotation(target, ann);
    render();
  };
  card.append(confirm);
  root.append(card);
}

function render() {
  const record = packet.records[activeRecord];
  renderProgress();
  renderNav();
  renderScenario(record);
  renderTargets(record);
  renderDialogue(record);
  renderAnnotation(record);
  document.title = `${record.scenario_id} · State v7 人工标注`;
}

function exportDraft() {
  save();
  if (!draft.reviewer) {
    alert("请先填写审核人姓名或 ID");
    $("reviewer").focus();
    return;
  }
  const done = allTargets().filter(
    target => annotation(target).status === "complete"
  ).length;
  if (done !== allTargets().length) {
    alert(`当前仅确认 ${done}/${allTargets().length}；可以导出备份，但运行器会拒绝不完整标签。`);
  }
  const output = {
    format: "socialflux_state_human_annotations_v1",
    round_id: packet.round_id,
    packet_sha256: packet.packet_sha256,
    reviewer: draft.reviewer,
    exported_at_utc: new Date().toISOString(),
    annotations: draft.annotations,
  };
  const blob = new Blob([JSON.stringify(output, null, 2) + "\n"], {type: "application/json"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `state_annotations_${packet.round_id}_${draft.reviewer}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function importDraft(file) {
  const value = JSON.parse(await file.text());
  if (value.packet_sha256 !== packet.packet_sha256) {
    throw new Error("标注文件对应的 packet 哈希不同；旧 v1 草稿不能直接作为 v7 标签");
  }
  draft = {reviewer: value.reviewer || "", annotations: value.annotations || {}};
  $("reviewer").value = draft.reviewer;
  save();
  render();
}

async function init() {
  try {
    const response = await fetch("/api/state-annotation", {cache: "no-store"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    packet = await response.json();
    loadDraft();
    $("packetMeta").textContent =
      `${packet.interface_revision} · ${packet.summary.scenario_count} 个 scenario · ` +
      `${packet.summary.required_target_count} 个必标 turn · ${packet.packet_sha256.slice(0, 12)}`;
    $("reviewer").addEventListener("input", save);
    $("exportButton").onclick = exportDraft;
    $("importFile").onchange = event => importDraft(event.target.files[0]).catch(error => alert(error.message));
    render();
  } catch (error) {
    $("workspace").replaceChildren(el("div", "error", `加载失败：${error.message}`));
  }
}

init();
