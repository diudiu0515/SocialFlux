"use strict";
const $ = id => document.getElementById(id);
const selectedBank = new URLSearchParams(location.search).get("bank") || "scenarios-v2";
const phases = {
  blind: ["1 · 独立盲答", "本场景全部题目提交后，才开放私有证据。答案一经提交即锁定。"],
  private_review: ["2 · 私有证据与独立 GT 初判", "查看相关完整对话、实际私有状态和分支，独立判断答案。本场景全部初判提交后开放机器建议；完成审核后才能进入下一场景。"],
  machine_review: ["3 · 机器建议与最终人工审核", "对照自己的独立初判检查机器建议，提交最终审核；盲答和初判均保持原样。"],
  complete: ["本次任务已完成", "记录已保存到服务器。标准答案须经过不同标注人的独立复核；争议题保留待裁决。"],
};
const labels = {
  background: "背景", public_situation: "关系与前史", relationship_structure: "关系结构", power_structure: "权力与资源",
  goal_conflict: "目标冲突", relevant_history: "相关前史", explicit_goal: "目标", name: "姓名", role: "身份",
  character_id: "角色 ID", facial_expression: "表情", gaze: "视线", speech_style: "说话方式", prosody: "语气", behavioral_cues: "动作",
  private_character: "私有人物设定", initial_state: "初始状态", prefix: "截止点前全部历史与状态",
  branches: "行动分支", replays: "A/B 受控回放", turns: "完整窗口", state_before: "更新前状态", state_after: "更新后状态",
  state_judgments: "状态判定依据", action: "行动", response: "环境回应", evidence_id: "证据编号",
  target_spec: "判断范围与目标", state_semantics: "状态语义", scenario: "原始场景", source_turns: "来源历史",
  source_checks: "来源检查", omniscient_evidence: "上帝视角证据", scope_note: "时间范围",
};
let session = null, current = null, token = null, loadVersion = 0;
function node(tag, cls, text) {
  const n = document.createElement(tag); if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text; return n;
}
function say(text) { $("message").textContent = text; }
function card(title) { const n = node("section", "card"); n.append(node("h2", "", title)); return n; }
function display(value) {
  if (value == null) return node("span", "muted", "—");
  if (typeof value !== "object") return node("div", "value", String(value));
  const box = node("div");
  for (const [key, content] of Object.entries(value)) {
    const field = node("div", "field");
    field.append(node("div", "field-name", labels[key] || (Array.isArray(value) ? `第 ${Number(key) + 1} 项` : key)), display(content));
    box.append(field);
  }
  return box;
}
async function api(action, payload = {}) {
  const response = await fetch("/api/offline-annotation/" + action, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({...payload, ...(["start", "catalog"].includes(action) ? {bank: selectedBank} : {}), ...(token && !["start", "catalog"].includes(action) ? {token} : {})}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function storedSessions() { try { return JSON.parse(localStorage.getItem("socialflux-human-sessions") || "[]"); } catch { return []; } }
function remember() {
  const rows = storedSessions().filter(x => x.token !== token);
  rows.unshift({token, reviewer: session.reviewer, count: session.counts.total, created: new Date().toLocaleDateString()});
  localStorage.setItem("socialflux-human-sessions", JSON.stringify(rows));
}
function renderNavigation() {
  const [title, sceneDescription] = phases[session.stage];
  const description = !session.sequential && session.stage === "blind"
    ? "本次全部题目提交后，才开放私有证据。答案一经提交即锁定。"
    : !session.sequential && session.stage === "private_review"
      ? "查看相关完整对话、实际私有状态和分支，独立判断答案。全部初判提交后才开放机器建议。"
      : sceneDescription;
  $("phaseTitle").textContent = title; $("phaseDescription").textContent = description;
  $("baselineNotice").textContent = session.baseline_eligible
    ? "本次记录符合首次盲答的流程条件；评分仍需独立 GT。"
    : "本次含重复作答或先前信息接触记录，仅参与审核，不计入首次盲答基线。";
  $("assignmentCount").textContent = session.active_scene ? `${session.active_scene} · ${session.scenes.find(x => x.scene === session.active_scene).total} 题` : `${session.counts.total} 题`;
  $("sessionProgress").textContent = `盲答 ${session.counts.blind} · 独立初判 ${session.counts.private} · 最终审核 ${session.counts.final}`;
  $("sessionCondition").textContent = session.modality === "text+video"
    ? "本次输入：文字＋视频。请结合题面和对应视频作答；同一会话保持相同输入条件。"
    : "这是此前领取的文字任务，原答案和输入条件已保留。新的视频任务可从“回到任务选择”领取。";
  $("sessionNav").replaceChildren();
  if (session.sequential) {
    const summary = node("div", "scene-sequence");
    (session.scenes || []).forEach((row, index) => summary.append(node("p", row.scene === session.active_scene ? "active" : "muted", `${index + 1}. ${row.scene} · ${row.stage === "complete" ? "已完成并锁定" : row.scene === session.active_scene ? "当前场景" : "未解锁"}`)));
    $("sessionNav").append(summary);
  }
  session.items.forEach((row, index) => {
    if (session.sequential && session.active_scene && row.scene !== session.active_scene) return;
    const done = session.stage === "blind" ? row.blind_submitted : session.stage === "private_review" ? row.private_submitted : row.final_submitted;
    const button = node("button", "item-button" + (row.instance_id === current ? " active" : ""));
    button.dataset.id = row.instance_id;
    button.append(node("strong", "", `${done ? "✓ " : ""}第 ${index + 1} 题`), node("small", "", row.instance_id));
    button.onclick = () => openItem(row.instance_id); $("sessionNav").append(button);
  });
}
function nextPending() {
  const key = session.stage === "blind" ? "blind_submitted" : session.stage === "private_review" ? "private_submitted" : "final_submitted";
  const items = session.items.filter(x => !session.sequential || !session.active_scene || x.scene === session.active_scene);
  return items.find(x => !x[key])?.instance_id || items[0].instance_id;
}
async function enter(value) {
  session = value; token = session.token; remember();
  $("setup").hidden = true; $("sessionLayout").hidden = false;
  $("exportSession").hidden = false; $("newAssignment").hidden = false;
  await openItem(nextPending());
}
function material(input) {
  const box = card("题目材料");
  box.append(display(input.context));
  const roles = node("div", "field-grid role-grid");
  roles.append(display({"行动角色": input.role}), display({"判断对象": input.target_character})); box.append(roles);
  function turns(title, values) {
    const column = node("div", "history-column"); column.append(node("h3", "", title));
    values.forEach(turn => {
      const row = node("article", "turn"); row.append(node("div", "turn-id", turn.turn_id));
      for (const [name, text, cls] of [[input.role.name, turn.evaluated_agent, ""], [input.target_character.name, turn.environment_character, " environment"]]) {
        const speech = node("div", "utterance" + cls); speech.append(node("div", "speaker", name), display(text)); row.append(speech);
      }
      if (Object.keys(turn.observable_expression || {}).length) row.append(display(turn.observable_expression));
      if (turn.public_events?.length) row.append(display({"公开事件": turn.public_events}));
      column.append(row);
    }); return column;
  }
  if (input.history) box.append(turns("已发生的对话", input.history));
  if (input.history_a) {
    const columns = node("div", "histories");
    columns.append(turns("History A", input.history_a), turns("History B", input.history_b)); box.append(columns);
    const ending = node("article", "turn ending");
    ending.append(node("h3", "", "相同的当前表达"), display(input.shared_ending.current_response), display(input.shared_ending.observable_expression)); box.append(ending);
  }
  if (input.candidate_actions) {
    box.append(node("h3", "", "候选行动"));
    input.candidate_actions.forEach(a => { const row = node("article", "turn"); row.append(node("strong", "", a.label), display(a.text)); box.append(row); });
  }
  return box;
}
function publicMedia(data) {
  const section = card("题目视频"); section.id = "annotationMedia";
  section.append(node("p", "muted", "请结合下面标明的位置观看视频，再阅读完整题面并作答。"));
  for (const asset of data.media || []) {
    const clip = node("article", "annotation-clip");
    clip.append(node("h3", "", "对应位置：" + asset.evidence_ids.join("、")));
    if (asset.evidence_ids.some(id => id.startsWith("A:")) && asset.evidence_ids.some(id => id.startsWith("B:"))) {
      clip.append(node("p", "muted", "History A / B 共用这段视频。"));
    }
    const video = node("video"); video.controls = true; video.playsInline = true;
    video.preload = "metadata"; video.src = asset.url; video.dataset.assetId = asset.asset_id;
    video.setAttribute("aria-label", "题目视频：" + asset.evidence_ids.join("、"));
    video.addEventListener("error", () => {
      if (!clip.isConnected) return;
      clip.append(node("p", "warning", "视频加载失败，请刷新后重试；视频可播放后再提交本题。"));
      const submit = $("submitJudgment"); if (submit) submit.disabled = true;
    }, {once: true});
    clip.append(video);
    if (asset.response_neutral) clip.append(node("p", "muted", "这段视频提供表情与动作线索；对白请结合题面文字阅读。"));
    section.append(clip);
  }
  const uncovered = (data.media_coverage?.uncovered_evidence_ids || []).map(id => id === "ending" ? "共同结尾" : id);
  if (uncovered.length) section.append(node("p", "muted", "以下位置仍以文字呈现：" + uncovered.join("、") + "。"));
  return section;
}
function choices(options, selected, disabled = false) {
  const box = node("div", "options");
  for (const [key, text] of Object.entries(options)) {
    const label = node("label", "option"), radio = node("input");
    radio.type = "radio"; radio.name = "answer"; radio.value = key; radio.checked = selected === key; radio.disabled = disabled;
    label.append(radio, node("strong", "", key), node("span", "", text)); box.append(label);
  }
  return box;
}
async function submit(action, identity, payload) {
  session = await api(action, {instance_id: identity, ...payload});
  say(action === "blind" ? "盲答已保存并锁定。" : action === "private" ? "独立 GT 初判已保存并锁定。" : "最终人工审核已保存。");
  await openItem(nextPending());
}
function judgmentForm(identity, question, action, previous) {
  const form = node("form", "annotation-form"); form.id = "judgmentForm";
  form.append(choices(question.options, previous?.answer));
  const rationaleLabel = node("label", "", action === "blind" ? "判断依据（可选）" : "判断依据（必填）");
  const rationale = node("textarea"); rationale.id = "judgmentRationale"; rationale.value = previous?.rationale || "";
  rationale.required = action !== "blind"; rationaleLabel.append(rationale); form.append(rationaleLabel);
  let decision, attestation;
  if (action !== "blind") {
    const label = node("label", "", "题目质量");
    decision = node("select"); decision.id = "judgmentDecision";
    [["usable", "唯一答案，建议可用"], ["revise", "存在问题，需要修改"], ["reject", "无可靠答案，退回"]].forEach(([value, text]) => {
      const option = node("option", "", text); option.value = value; decision.append(option);
    }); decision.value = previous?.decision || "usable"; label.append(decision); form.append(label);
  }
  if (action === "final") {
    const label = node("label", "attestation"); attestation = node("input"); attestation.type = "checkbox"; attestation.required = true; attestation.id = "humanAttestation";
    label.append(attestation, document.createTextNode("确认这是我本人完成的人工审核")); form.append(label);
  }
  const button = node("button", "primary", action === "blind" ? "提交并锁定本题盲答" : action === "private" ? "提交独立 GT 初判" : "提交最终人工审核");
  button.type = "submit"; button.id = "submitJudgment"; form.append(button);
  form.onsubmit = async event => {
    event.preventDefault(); button.disabled = true;
    const answer = form.querySelector("input[name=answer]:checked")?.value || null;
    try { await submit(action, identity, {answer, rationale: rationale.value, decision: decision?.value || "usable", human_attestation: !!attestation?.checked}); }
    catch (error) { say(error.message); button.disabled = false; }
  };
  return form;
}
async function openItem(identity) {
  const version = ++loadVersion; current = identity; renderNavigation();
  const workspace = $("annotationWorkspace"); workspace.replaceChildren(node("p", "muted", "正在加载…")); workspace.setAttribute("aria-busy", "true");
  try {
    const data = await api("item", {instance_id: identity});
    if (version !== loadVersion) return;
    const question = data.public, header = card(`第 ${session.items.findIndex(x => x.instance_id === identity) + 1} 题`);
    header.append(node("p", "question", question.question)); workspace.replaceChildren(header);
    if (session.modality === "text+video") workspace.append(publicMedia(data));
    workspace.append(material(question.input));
    if (session.stage === "blind") {
      const answer = card(data.blind_response ? "已锁定的盲答" : "你的独立答案");
      if (data.blind_response) { answer.append(choices(question.options, data.blind_response.answer, true), node("p", "locked-answer", "原始答案已保存，不能修改。")); }
      else answer.append(judgmentForm(identity, question, "blind"));
      workspace.append(answer); return;
    }
    const original = card("已锁定的原始盲答"); original.append(node("p", "locked-answer", `答案 ${data.blind_response.answer}`));
    const evidence = card("上帝视角证据"); evidence.classList.add("annotation-evidence");
    const button = node("button", "primary", "查看相关完整对话与私有状态"); button.id = "openPrivateEvidence";
    evidence.append(button); workspace.append(original, evidence);
    button.onclick = async () => {
      button.disabled = true;
      try {
        const result = await api("evidence", {instance_id: identity});
        if (current !== identity || !evidence.isConnected) return;
        button.textContent = "私有证据已展开";
        for (const [key, value] of Object.entries(result)) {
          if (["instance_id", "item_sha256"].includes(key)) continue;
          const section = node("details"); section.open = ["scope_note", "source_checks", "omniscient_evidence"].includes(key);
          section.append(node("summary", "", labels[key] || key), display(value)); evidence.append(section);
        }
        if (!data.private_judgment) {
          const judge = card("独立 GT 初判"); judge.append(judgmentForm(identity, question, "private")); workspace.append(judge);
        }
      } catch (error) { say(error.message); button.disabled = false; }
    };
    if (data.private_judgment) {
      const saved = card("已锁定的独立 GT 初判"); saved.append(display(data.private_judgment)); workspace.append(saved);
    }
    if (["machine_review", "complete"].includes(session.stage)) {
      const machine = card("机器建议"); const reveal = node("button", "", "查看机器标准答案候选"); reveal.id = "openMachineSuggestion"; machine.append(reveal);
      reveal.onclick = async () => {
        reveal.disabled = true;
        try {
          const result = await api("machine", {instance_id: identity});
          if (current !== identity || !machine.isConnected) return;
          const author = result.authoring;
          machine.append(node("h3", "", `机器候选：${author.answer} · ${question.options[author.answer] || ""}`), display(author.oracle_reference || {"公开材料参考依据": author.rationale}),
            node("p", "muted", "机器一致不等于人工 GT；发现证据冲突请标记修改或退回。"));
        } catch (error) { say(error.message); reveal.disabled = false; }
      };
      workspace.append(machine);
      const final = card(data.final_judgment ? "已提交的最终人工审核" : "最终人工审核");
      final.append(data.final_judgment ? display(data.final_judgment) : judgmentForm(identity, question, "final", data.private_judgment)); workspace.append(final);
    }
  } catch (error) { if (version === loadVersion) workspace.replaceChildren(node("p", "warning", error.message)); }
  finally { if (version === loadVersion) workspace.setAttribute("aria-busy", "false"); }
}
async function setup() {
  $("newAssignment").onclick = () => location.reload();
  $("exportSession").onclick = async () => {
    try {
      const data = await api("export"), url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: "application/json"}));
      const link = node("a"); link.href = url; link.download = "socialflux-human-annotation.json"; link.click(); URL.revokeObjectURL(url);
    } catch (error) { say(error.message); }
  };
  try {
    const previous = storedSessions(); $("resumeCard").hidden = !previous.length;
    previous.forEach(row => {
      const button = node("button", "resume-button", `${row.reviewer} · ${row.count} 题 · ${row.created}`);
      button.onclick = async () => { token = row.token; try { await enter(await api("status")); } catch (error) { say(error.message); } };
      $("resumeList").append(button);
    });
  } catch (error) { say("加载失败：" + error.message); }
}
setup();
