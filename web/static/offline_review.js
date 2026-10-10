/* Review existing artifacts only. No model calls and no ground-truth mutation. */
"use strict";
const $ = id => document.getElementById(id);
const LABELS = {
  background: "场景背景", public_situation: "关系、约束与前史", relationship_structure: "关系结构",
  power_structure: "权力与资源", goal_conflict: "目标冲突", relevant_history: "相关前史",
  explicit_goal: "角色目标", role: "身份", name: "姓名", character_id: "人物 ID",
  facial_expression: "表情", gaze: "视线", speech_style: "说话方式", prosody: "语气",
  behavioral_cues: "动作线索", definition: "变量定义", increase_evidence: "上升依据",
  decrease_evidence: "下降依据", non_evidence: "不构成证据", Emotion: "情绪体验",
  "Behavioral Disposition": "行为倾向", Relationship: "关系判断", "Interaction Risk": "互动风险",
  current_intensity: "当前状态强度", interval_change: "区间变化", joint_change: "两变量变化",
  history_comparison: "前史状态比较", expression_meaning: "共同表达的含义", joint_comparison: "前史组合比较",
  immediate_effect: "即时影响", delayed_effect: "延迟影响", action_comparison: "行动比较", immediate_delayed: "即时—延迟组合",
  actor_reversal: "主体／对象反转", expression_as_state: "表面表达替代状态", state_dimension_confusion: "状态维度混淆",
  history_ignored: "忽略历史", promise_as_fulfillment: "承诺与履约混淆", immediate_delayed_confusion: "即时与延迟混淆",
  goal_constraint_ignored: "忽略目标约束", unsupported_inference: "无依据过度推断",
  supports_history: "非语言线索与历史相互支持", ambiguous_without_history: "非语言线索需结合历史理解",
};
const RATINGS = {clarity: "题目是否清楚", evidence_support: "证据是否充分", answer_distinguishability: "答案是否可区分", analyzability: "结果是否便于分析"};
let bank, detail, activeId, requestVersion = 0, modality = "text";
let draft = {reviewer: "", annotations: {}};
const detailCache = new Map();

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}
function human(value) {
  if (value == null || value === "") return el("span", "muted", "—");
  if (typeof value !== "object") return el("div", "value", String(value));
  if (Array.isArray(value)) {
    const list = el("ul", "human-list");
    value.forEach(v => {const li = el("li"); li.append(human(v)); list.append(li);});
    return list;
  }
  const container = el("div");
  Object.entries(value).forEach(([k, v]) => {
    const field = el("div", "field");
    field.append(el("div", "field-name", LABELS[k] || k), human(v)); container.append(field);
  });
  return container;
}
function jsonDetails(title, value) {
  const node = el("details");
  node.append(el("summary", "", title), el("pre", "", JSON.stringify(value, null, 2)));
  return node;
}
function card(title) {const node = el("section", "card"); node.append(el("h2", "", title)); return node;}
function message(text) {$("message").textContent = text;}
function storageKey() {return "socialflux-offline-choice-review:" + bank.bank_sha256;}
function annotation(id = activeId) {
  if (!draft.annotations[id]) {
    const meta = bank.items.find(item => item.instance_id === id);
    draft.annotations[id] = {instance_id: id, item_sha256: meta.item_sha256, status: "draft",
      answer: null, acceptable_answers: [], evidence_ids: [], ratings: {}, decision: "",
      rationale: "", revision_note: "", reference_viewed_at: null, modalities_seen: ["text"]};
  }
  return draft.annotations[id];
}
function save() {
  draft.reviewer = $("reviewer").value.trim();
  try {localStorage.setItem(storageKey(), JSON.stringify(draft));}
  catch {message("浏览器未能保存草稿，请及时导出备份。");}
  renderNav();
}
function update(field, value) {
  const ann = annotation(); ann[field] = value; ann.status = "draft";
  ann.updated_at_utc = new Date().toISOString();
  save(); updateStatus();
}
function filteredItems() {
  const query = $("search").value.trim().toLowerCase();
  return bank.items.filter(item => {
    const complete = draft.annotations[item.instance_id]?.status === "complete";
    return (!$("taskFilter").value || item.task === $("taskFilter").value) &&
      (!$("familyFilter").value || item.families.includes($("familyFilter").value)) &&
      (!$("shapeFilter").value || item.combination === ($("shapeFilter").value === "combo")) &&
      (!$("statusFilter").value || ($("statusFilter").value === "complete" ? complete :
        $("statusFilter").value === "pending" ? !complete : item.task !== "T1" && item.replay_status !== "validated")) &&
      (!query || `${item.instance_id} ${item.scenario_id} ${item.question}`.toLowerCase().includes(query));
  });
}
function renderNav() {
  if (!bank) return;
  const done = bank.items.filter(i => draft.annotations[i.instance_id]?.status === "complete").length;
  const items = filteredItems();
  $("progress").textContent = `已完成 ${done} / ${bank.items.length} · 筛选 ${items.length} 题`;
  $("itemNav").replaceChildren();
  items.forEach(item => {
    const button = el("button", "item-button" + (item.instance_id === activeId ? " active" : ""));
    button.dataset.id = item.instance_id;
    button.append(el("strong", "", `${draft.annotations[item.instance_id]?.status === "complete" ? "✓ " : ""}${item.instance_id} · ${item.task}`),
      el("small", "", `${item.scenario_id} · ${LABELS[item.subtype]}`), el("span", "preview", item.question));
    button.onclick = () => selectItem(item.instance_id);
    $("itemNav").append(button);
  });
  if (!items.length) $("itemNav").append(el("p", "muted", "没有符合筛选条件的题目。"));
}
async function fetchJSON(url) {
  const response = await fetch(url, {cache: "no-store"});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
async function selectItem(id) {
  if (!bank.items.some(i => i.instance_id === id)) return;
  const version = ++requestVersion;
  activeId = id; detail = null; modality = "text";
  history.replaceState(null, "", "#" + encodeURIComponent(id));
  $("workspace").setAttribute("aria-busy", "true");
  $("workspace").replaceChildren(el("p", "muted", "正在加载题目…"));
  renderNav();
  try {
    const value = detailCache.get(id) || await fetchJSON("/api/offline-review/" + encodeURIComponent(id));
    if (version !== requestVersion) return;
    if (value.bank_sha256 !== bank.bank_sha256) throw new Error("题库版本已更新，请导出草稿后刷新页面");
    detailCache.set(id, value); detail = value;
    renderItem();
  } catch (error) {
    if (version === requestVersion) $("workspace").replaceChildren(el("p", "warning", `加载失败：${error.message}`));
  } finally {if (version === requestVersion) $("workspace").setAttribute("aria-busy", "false");}
}
function turnNode(turn, input) {
  const box = el("article", "turn");
  box.append(el("div", "turn-id", turn.turn_id), el("div", "speaker", input.role.name), human(turn.evaluated_agent),
    el("div", "speaker", input.target_character.name), human(turn.environment_character));
  if (Object.keys(turn.observable_expression || {}).length) {
    const cues = el("details"); cues.open = true;
    cues.append(el("summary", "", "可见表情、动作与语气"), human(turn.observable_expression)); box.append(cues);
  }
  if (turn.public_events?.length) box.append(human({"公开事件": turn.public_events}));
  return box;
}
function renderMaterial(input) {
  const section = card("题目材料"); section.id = "publicMaterial";
  section.append(human({background: input.context.background, public_situation: input.context.public_situation}));
  const roles = el("div", "field-grid");
  roles.append(human({"行动角色": input.role}), human({"判断对象": input.target_character})); section.append(roles);
  if (input.history_a) {
    const histories = el("div", "histories");
    ["a", "b"].forEach(side => {
      const column = el("div", "history-column"); column.dataset.history = side;
      column.append(el("h3", "", "History " + side.toUpperCase()));
      input["history_" + side].forEach(turn => column.append(turnNode(turn, input))); histories.append(column);
    });
    section.append(histories);
    const ending = el("article", "turn ending"); ending.id = "sharedEnding";
    ending.append(el("h3", "", "相同的当前表达 · " + input.shared_ending.turn_id),
      human(input.shared_ending.current_response), human(input.shared_ending.observable_expression));
    section.append(ending);
  } else {
    section.append(el("h3", "", "已发生的历史"));
    input.history.forEach(turn => section.append(turnNode(turn, input)));
  }
  if (input.candidate_actions) {
    section.append(el("h3", "", "候选行动"));
    input.candidate_actions.forEach(action => {
      const node = el("article", "candidate");
      node.append(el("strong", "", action.action_id), human(action.text)); section.append(node);
    });
    section.append(el("p", "muted", "即时影响指执行行动后的下一次环境回应；具体时间范围以题干为准。"));
  }
  return section;
}
function renderMedia() {
  const section = card("配对材料");
  const select = el("select"); select.id = "modality";
  select.append(new Option("文字", "text"), new Option("文字 + 视频", "text+video")); select.value = modality;
  const label = el("label", "", "展示条件"); label.append(select); section.append(label);
  const clips = el("div"); clips.id = "mediaClips"; section.append(clips);
  function show() {
    clips.replaceChildren();
    if (modality === "text") {clips.append(el("p", "muted", "当前只展示文字与原有非语言描述。")); return;}
    clips.append(el("p", "muted", "与文字版共用题干、选项和待审答案。" + (LABELS[detail.nonverbal_history_relation] || "")));
    if (!detail.media.length) clips.append(el("p", "warning", "没有与当前题目版本匹配的配对视频。"));
    detail.media.forEach(asset => {
      clips.append(el("p", "", "历史位置：" + asset.evidence_ids.join("、")));
      if (asset.available) {
        const video = el("video"); video.controls = true; video.preload = "metadata"; video.playsInline = true;
        video.src = asset.url; clips.append(video);
      } else clips.append(el("p", "warning", "素材缺失或哈希不匹配，暂不可播放。"));
      clips.append(el("p", "muted", "素材审核：" + (asset.human_review === "approved" ? "已通过" : "待人工审核")));
    });
  }
  select.onchange = () => {
    modality = select.value;
    const seen = new Set(annotation().modalities_seen); seen.add(modality);
    update("modalities_seen", [...seen]); show();
  };
  show(); return section;
}
function updateStatus() {
  const ann = annotation();
  const status = $("annotationStatus");
  if (status) status.textContent = `${ann.status === "complete" ? "已完成本题标注" : "草稿 · 自动保存到浏览器"} · ${ann.reference_viewed_at ? "已看过作者参考" : "未查看作者参考"}`;
}
function selectField(label, id, value, options, onChange) {
  const node = el("label", "", label), select = el("select"); select.id = id;
  select.append(new Option("请选择", "")); options.forEach(([v, t]) => select.append(new Option(t, v)));
  select.value = value || ""; select.onchange = () => onChange(select.value); node.append(select); return node;
}
function textField(label, id, value, onChange) {
  const node = el("label", "wide", label), input = el("textarea"); input.id = id; input.value = value || "";
  input.oninput = () => onChange(input.value); node.append(input); return node;
}
function validateAnnotation(ann, options, evidence, complete = false) {
  const errors = [];
  if (ann.answer != null && !Object.hasOwn(options, ann.answer)) errors.push("答案不属于本题选项");
  if (!Array.isArray(ann.acceptable_answers) || ann.acceptable_answers.some(x => !Object.hasOwn(options, x))) errors.push("可接受答案无效");
  if (!Array.isArray(ann.evidence_ids) || ann.evidence_ids.some(x => !evidence.includes(x))) errors.push("证据 ID 不属于本题可见材料");
  if (!ann.ratings || Object.values(ann.ratings).some(x => !["yes", "partial", "no", ""].includes(x))) errors.push("质量判断无效");
  if (!["", "usable", "revise", "reject"].includes(ann.decision)) errors.push("审核意见无效");
  if (!["draft", "complete"].includes(ann.status)) errors.push("标注状态无效");
  if (!Array.isArray(ann.modalities_seen) || ann.modalities_seen.some(x => !["text", "text+video"].includes(x))) errors.push("模态记录无效");
  if (complete) {
    if (!ann.answer && ann.decision !== "reject") errors.push("请选择你的答案；无合理选项时可选择退回");
    if (!ann.decision) errors.push("请选择审核意见");
    if (Object.keys(RATINGS).some(k => !ann.ratings?.[k])) errors.push("请完成四项质量判断");
    if (!String(ann.rationale || "").trim()) errors.push("请填写判断依据");
    if (ann.decision === "usable" && Object.values(ann.ratings).some(v => v !== "yes")) errors.push("仍有质量问题时请选择修改或退回");
    if (["revise", "reject"].includes(ann.decision) && !String(ann.revision_note || "").trim()) errors.push("修改或退回时请填写问题与建议");
  }
  return errors;
}
function renderAnnotation() {
  const ann = annotation(), section = card("独立判断与题目审核"); section.id = "annotation";
  section.append(el("p", "review-state", "")); section.lastChild.id = "annotationStatus";
  const options = el("div", "options");
  Object.entries(detail.public.options).forEach(([letter, text]) => {
    const label = el("label", "option"), radio = el("input"); radio.type = "radio"; radio.name = "answer";
    radio.value = letter; radio.checked = ann.answer === letter;
    radio.onchange = () => update("answer", letter);
    label.append(radio, el("strong", "", letter), el("span", "", text)); options.append(label);
  });
  section.append(options);
  section.append(el("p", "form-label", "其他可接受选项（存在相近合理判断时）"));
  const accepted = el("div", "evidence");
  Object.keys(detail.public.options).forEach(letter => {
    const label = el("label"), check = el("input"); check.type = "checkbox"; check.value = letter;
    check.checked = ann.acceptable_answers.includes(letter); check.name = "acceptable";
    check.onchange = () => update("acceptable_answers", [...accepted.querySelectorAll("input:checked")].map(n => n.value));
    label.append(check, document.createTextNode(letter)); accepted.append(label);
  }); section.append(accepted);
  section.append(el("p", "form-label", "支持判断的证据位置（独立诊断，可多选）"));
  const evidence = el("div", "evidence");
  detail.evidence_ids.forEach(id => {
    const label = el("label"), check = el("input"); check.type = "checkbox"; check.value = id; check.name = "evidence";
    check.checked = ann.evidence_ids.includes(id);
    check.onchange = () => update("evidence_ids", [...evidence.querySelectorAll("input:checked")].map(n => n.value));
    label.append(check, document.createTextNode(id)); evidence.append(label);
  }); section.append(evidence);
  const form = el("div", "field-grid");
  form.append(textField("判断依据", "rationale", ann.rationale, value => update("rationale", value)));
  Object.entries(RATINGS).forEach(([key, label]) => {
    form.append(selectField(label, key, ann.ratings[key], [["yes", "是"], ["partial", "部分满足"], ["no", "否"]],
      value => update("ratings", {...annotation().ratings, [key]: value})));
  });
  form.append(selectField("题目审核意见", "decision", ann.decision, [["usable", "建议可用"], ["revise", "需要修改"], ["reject", "退回 / 无合理答案"]], value => update("decision", value)),
    textField("问题与修改建议", "revisionNote", ann.revision_note, value => update("revision_note", value)));
  section.append(form);
  const actions = el("div", "form-actions"), complete = el("button", "primary", "完成本题标注"); complete.id = "completeButton";
  complete.onclick = () => {
    const current = annotation();
    const errors = validateAnnotation(current, detail.public.options, detail.evidence_ids, true);
    if (!$("reviewer").value.trim()) errors.unshift("请填写标注人姓名或 ID");
    if (errors.length) {message(errors.join("；")); return;}
    current.status = "complete"; current.reviewed_by = $("reviewer").value.trim(); current.completed_at_utc = new Date().toISOString();
    save(); updateStatus(); message("本题标注已保存在浏览器。导出可备份，不会自动批准正式答案。");
  };
  actions.append(complete); section.append(actions); return section;
}
function renderReference() {
  const section = card("作者参考与来源核查"); section.classList.add("reference");
  section.append(el("p", "reference-label", "包含待审参考答案、私有 state 与分支结果。查看后会记录为参考辅助标注。"));
  const button = el("button", "", "查看参考答案与来源"); button.id = "revealReference";
  const body = el("div"); body.id = "referenceBody"; section.append(button, body);
  const id = activeId;
  button.onclick = async () => {
    button.disabled = true;
    try {
      const ref = await fetchJSON(`/api/offline-review/${encodeURIComponent(id)}/reference`);
      if (activeId !== id || !section.isConnected) return;
      if (ref.bank_sha256 !== bank.bank_sha256) throw new Error("题库已更新，请先导出草稿并刷新");
      const ann = annotation();
      if (!ann.reference_viewed_at) {
        ann.blind_judgment = {answer: ann.answer, acceptable_answers: [...ann.acceptable_answers],
          evidence_ids: [...ann.evidence_ids], rationale: ann.rationale, status: ann.status};
        update("reference_viewed_at", new Date().toISOString());
      }
      button.textContent = "已展开作者参考";
      const author = ref.authoring;
      body.append(el("h3", "", `待审参考：${author.answer}${author.acceptable_answers ? " · 可接受 " + author.acceptable_answers.join("、") : ""}`),
        human(author.rationale), el("p", "muted", "作者证据：" + author.evidence_ids.join("、")));
      if (author.review_notes) body.append(human({"作者备注（保留原记录）": author.review_notes}));
      const table = el("table"); const head = el("tr");
      ["选项", "主要错误类型", "各变量判断"].forEach(t => head.append(el("th", "", t))); table.append(head);
      Object.keys(detail.public.options).forEach(letter => {
        const row = el("tr"); row.append(el("td", "", letter), el("td", "", LABELS[author.option_errors[letter]] || "参考可接受选项"));
        const cell = el("td"); cell.append(human(author.option_variable_map[letter])); row.append(cell); table.append(row);
      }); body.append(table);
      body.append(el("h3", "", "判断对象与时间范围"), human(ref.target_spec),
        el("h3", "", "绑定的 state 语义"), human(ref.state_semantics));
      const checks = Object.entries(ref.source_checks).map(([name, ok]) => `${name}：${ok ? "匹配" : "缺失或不匹配"}`).join("；");
      body.append(el("p", "muted", "来源哈希与行动检查 · " + checks));
      body.append(jsonDetails("构造来源与改写位置", author.construction_source));
      if (ref.scenario) body.append(jsonDetails("完整原始 scenario（含作者侧信息）", ref.scenario));
      if (ref.state_crosscheck) body.append(jsonDetails("状态交叉检查（机器参考，不是人工答案）", ref.state_crosscheck));
      function referenceTurns(title, turns) {
        const container = el("details"); container.append(el("summary", "", title));
        turns.forEach(turn => {
          const box = el("article", "turn");
          box.append(el("strong", "", turn.turn_id), human({"行动": turn.policy_action?.text || turn.policy_action,
            "环境回应": turn.environment_response, "可见表达": turn.observable_expression,
            "更新前 state": turn.state_before, "更新后 state": turn.state_after,
            "事件": turn.environment_response_ledger_events, "触发事件": turn.trigger_events})); container.append(box);
        }); body.append(container);
      }
      referenceTurns("原轨迹对应历史与 state", ref.source_turns);
      ref.replays.forEach(replay => referenceTurns(`${replay.label} · ${replay.delayed_horizon ? `后续 ${replay.delayed_horizon} 次回应 · ${replay.window_complete ? "窗口完整" : "窗口未完成"}` : "受控回放"}`, replay.turns));
      if (detail.metadata.task !== "T1" && !ref.replays.length) body.append(el("p", "warning", "没有可核查的完整回放，不能据此批准分支标注。"));
    } catch (error) {if (activeId === id) {message(`参考加载失败：${error.message}`); button.disabled = false;}}
  };
  return section;
}
function renderItem() {
  const meta = detail.metadata, workspace = $("workspace"); workspace.replaceChildren();
  const nav = el("div", "previous-next"), items = filteredItems(), index = items.findIndex(i => i.instance_id === activeId);
  [[-1, "← 上一题"], [1, "下一题 →"]].forEach(([offset, text]) => {
    const button = el("button", "", text), next = items[index + offset]; button.disabled = index < 0 || !next;
    button.onclick = () => selectItem(next.instance_id); nav.append(button);
  }); workspace.append(nav);
  const title = card(`${meta.instance_id} · ${LABELS[meta.subtype]}`);
  [meta.task, meta.scenario_id, ...meta.families.map(f => LABELS[f]), meta.combination ? "组合题" : "单维题"].forEach(t => title.append(el("span", "badge", t)));
  title.append(el("p", "question", detail.public.question));
  title.append(el("p", "muted", "本批标签待人工审核。题目版本 " + meta.item_sha256.slice(0, 12)));
  if (meta.task !== "T1" && meta.replay_status !== "validated") title.append(el("p", "warning", "此题完整分支回放尚未完成，当前仅为开发候选。"));
  workspace.append(title, renderMaterial(detail.public.input), renderMedia(), renderAnnotation(), renderReference());
  updateStatus(); document.title = `${meta.instance_id} · SocialFlux 题目标注`;
}
function exportDraft() {
  save();
  if (!draft.reviewer) {message("导出前请填写标注人姓名或 ID。"); $("reviewer").focus(); return;}
  const output = {format: "socialflux_offline_choice_annotations_v1", bank_id: bank.bank_id,
    bank_sha256: bank.bank_sha256, reviewer: draft.reviewer, exported_at_utc: new Date().toISOString(),
    status: "human_review_draft_not_formal_ground_truth", annotations: draft.annotations};
  const url = URL.createObjectURL(new Blob([JSON.stringify(output, null, 2) + "\n"], {type: "application/json"}));
  const link = el("a"); link.href = url; link.download = `offline_review_${bank.bank_sha256.slice(0, 12)}.json`;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); message("标注已导出，可在其他浏览器导入同一版本题库继续。");
}
async function importDraft(file) {
  if (!file) return;
  const value = JSON.parse(await file.text());
  if (value.format !== "socialflux_offline_choice_annotations_v1" || value.bank_sha256 !== bank.bank_sha256) throw new Error("导入文件与当前题库版本不匹配");
  if (!value.annotations || typeof value.annotations !== "object" || Array.isArray(value.annotations)) throw new Error("标注结构无效");
  // Validate every record before mutating local progress. Merging keeps unrelated work.
  for (const [id, ann] of Object.entries(value.annotations)) {
    const meta = bank.items.find(i => i.instance_id === id);
    if (!meta || ann.instance_id !== id || ann.item_sha256 !== meta.item_sha256) throw new Error(`题目版本不匹配：${id}`);
    const item = detailCache.get(id) || await fetchJSON("/api/offline-review/" + encodeURIComponent(id));
    if (item.bank_sha256 !== bank.bank_sha256) throw new Error("题库已更新，请刷新后再导入");
    detailCache.set(id, item);
    const errors = validateAnnotation(ann, item.public.options, item.evidence_ids, ann.status === "complete");
    if (ann.status === "complete" && !String(ann.reviewed_by || "").trim()) errors.push("已完成记录缺少标注人");
    if (errors.length) throw new Error(`${id}：${errors.join("；")}`);
  }
  for (const [id, incoming] of Object.entries(value.annotations)) {
    const existing = draft.annotations[id];
    // Once exposed, a record must not become blind again through an older import.
    if (existing?.reference_viewed_at && !incoming.reference_viewed_at) {
      incoming.reference_viewed_at = existing.reference_viewed_at;
      incoming.blind_judgment = existing.blind_judgment;
    }
    incoming.modalities_seen = [...new Set([...(existing?.modalities_seen || []), ...incoming.modalities_seen])];
    draft.annotations[id] = incoming;
  }
  $("reviewer").value = value.reviewer || draft.reviewer;
  save(); if (detail) renderItem(); message("标注已导入；同题记录采用导入内容，其余本地标注保留。");
}
async function init() {
  try {
    bank = await fetchJSON("/api/offline-review");
    const summary = bank.summary;
    $("bankMeta").textContent = `${summary.item_count} 题 · ${summary.scenario_count} 个场景 · ${["T1", "T2", "T3"].map(task => `${task} ${summary.tasks[task] || 0}`).join(" / ")} · ${summary.combinations} 道组合题 · ${summary.replay_pending} 题回放待完成`;
    if (!bank.items.length) {$("workspace").replaceChildren(el("p", "empty", "当前没有可标注的题目。")); return;}
    try {const saved = JSON.parse(localStorage.getItem(storageKey()) || "null"); if (saved?.annotations) draft = saved;}
    catch {message("未能读取浏览器草稿，可以导入已导出的备份。");}
    $("reviewer").value = draft.reviewer || ""; $("reviewer").oninput = save;
    for (const id of ["taskFilter", "familyFilter", "shapeFilter", "statusFilter", "search"]) $(id).addEventListener("input", renderNav);
    $("exportButton").onclick = exportDraft;
    $("importFile").onchange = event => importDraft(event.target.files[0]).catch(error => message("导入失败：" + error.message));
    const requested = decodeURIComponent(location.hash.slice(1));
    await selectItem(bank.items.some(i => i.instance_id === requested) ? requested : bank.items[0].instance_id);
  } catch (error) {$("workspace").replaceChildren(el("p", "warning", "加载失败：" + error.message));}
}
init();
