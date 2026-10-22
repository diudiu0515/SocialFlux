const pageParams = new URLSearchParams(window.location.search);
const requestedBatch = pageParams.get("batch");
const requestedLane = pageParams.get("lane");
const ACTIVE_BATCH = ["gpt", "claude"].includes(requestedBatch)
  ? requestedBatch
  : "gpt";
const STORAGE_KEY = `socialflux.onlineMultimodalReview.v3.${ACTIVE_BATCH}`;
const CHECK_LABELS = {
  identity_matches_anchor: "人物与锚点一致",
  family_cue_alignment: "表达符合事件状态",
  audio_track_present: "音轨存在且可听",
  family_audio_cue_alignment: "声音符合事件状态",
  no_speech_or_mouthing: "无说话式嘴部动作",
  no_visible_text_or_branding: "无字幕、文字或品牌",
  subtle_natural_motion: "动作克制且自然",
  natural_synchronized_audio: "声音自然并与动作同步",
  exact_spoken_line: "英文台词逐字一致",
  lip_sync_and_speech_naturalness: "口型与语音自然同步",
  voice_delivery_naturalness: "语音像自然对话，不是机械念稿",
  expression_matches_state: "表情符合该轮可观测状态",
  factual_consistency: "事实与原公开回复一致",
  no_private_state_leakage: "未泄露私有状态或分数"
};
const STATE_FAMILY_LABELS = {
  emotion: "情绪",
  behavioral_disposition: "行为倾向",
  relationship: "关系",
  consequence_risk: "后果风险"
};
const TIER_LABELS = {
  easy: "易触发",
  moderate: "可触发",
  near_miss: "接近触发",
  not_observed: "本轨迹未观察到"
};
const BLOCKED_REASON_LABELS = {
  episode_cap: "单局上限",
  event_family_cooldown: "事件族冷却",
  global_cooldown: "全局冷却",
  per_trigger_cap: "同一触发器次数上限",
  trigger_cooldown: "触发器冷却",
  per_turn_priority_budget: "单轮优先级预算"
};
const IMPORTANCE_REASON_LABELS = {
  state_or_dynamics_change: "状态或动态发生变化",
  state_triggered_expression: "出现状态触发表达",
  consequential_claim: "包含后果性承诺或事实",
  socially_consequential_event: "具有社会后果的重要节点",
  endpoint: "轨迹端点"
};
const LANE_LABELS = {
  all: "全部视频",
  online_nonverbal: "Online 状态触发",
  talking_head: "Offline 响应口型"
};
let packet = null;
let activeScenarioId = null;
let draft = {reviewer: "", items: {}};
let statusFilter = "all";
let scenarioSearch = "";
let assetTypeFilter = ["all", "online_nonverbal", "talking_head"].includes(requestedLane)
  ? requestedLane
  : "online_nonverbal";

const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, ch => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[ch]));

function toast(message) {
  const element = $("toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("show"), 2200);
}

function loadDraft() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (saved && saved.items && typeof saved.items === "object") {
      draft = {reviewer: String(saved.reviewer || ""), items: saved.items};
    }
  } catch (_) {}
}

function saveDraft() {
  draft.reviewer = $("reviewer").value.trim();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
  renderProgress();
  renderScenarioList();
}

function allAssets() {
  return packet.scenarios.flatMap(scenario => scenario.assets);
}

function assetsInScope(scenario) {
  return assetTypeFilter === "all"
    ? scenario.assets
    : scenario.assets.filter(asset => asset.asset_type === assetTypeFilter);
}

function reviewAssets() {
  return packet.scenarios.flatMap(assetsInScope);
}

function checkKeysFor(asset) {
  return asset.check_keys?.length ? asset.check_keys : packet.check_keys;
}

function recordFor(asset) {
  let record = draft.items[asset.request_id];
  const staleEvidence = Boolean(record && (
    record.video_sha256 !== asset.video_sha256
    || record.playback_sha256 !== asset.playback_sha256
  ));
  if (!record || staleEvidence) {
    const checks = {};
    checkKeysFor(asset).forEach(key => {
      checks[key] = staleEvidence ? null : (asset.checks?.[key] ?? null);
    });
    record = {
      request_id: asset.request_id,
      scenario_id: asset.scenario_id,
      event_family: asset.event_family,
      asset_type: asset.asset_type || "online_nonverbal",
      media_asset_id: asset.media_asset_id,
      video_sha256: asset.video_sha256,
      playback_sha256: asset.playback_sha256,
      human_status: staleEvidence ? "pending" : (asset.human_status || "pending"),
      checks,
      notes: staleEvidence ? "视频已更新，旧审核自动失效，请重新检查。" : (asset.notes || "")
    };
    draft.items[asset.request_id] = record;
  }
  record.scenario_id = asset.scenario_id;
  record.event_family = asset.event_family;
  record.media_asset_id = asset.media_asset_id;
  record.video_sha256 = asset.video_sha256;
  record.playback_sha256 = asset.playback_sha256;
  record.checks = record.checks || {};
  checkKeysFor(asset).forEach(key => {
    if (![true, false, null].includes(record.checks[key])) record.checks[key] = null;
  });
  if (!["pending", "passed", "rejected"].includes(record.human_status)) {
    record.human_status = "pending";
  }
  return record;
}

function scenarioStats(scenario) {
  const records = assetsInScope(scenario).map(recordFor);
  return {
    total: records.length,
    passed: records.filter(item => item.human_status === "passed").length,
    rejected: records.filter(item => item.human_status === "rejected").length,
    reviewed: records.filter(item => item.human_status !== "pending").length
  };
}

function visibleScenarios() {
  const query = scenarioSearch.trim().toLowerCase();
  return packet.scenarios.filter(scenario => {
    const stats = scenarioStats(scenario);
    const statusMatches = stats.total > 0 && (
      statusFilter === "all"
      || (statusFilter === "pending" && stats.reviewed < stats.total)
      || (statusFilter === "rejected" && stats.rejected > 0)
      || (statusFilter === "passed" && stats.passed === stats.total));
    const textMatches = !query
      || `${scenario.scenario_id} ${scenario.title}`.toLowerCase().includes(query);
    return statusMatches && textMatches;
  });
}

function renderScenarioList() {
  const scenarios = visibleScenarios();
  $("scenarioCount").textContent = scenarios.length;
  $("scenarioList").innerHTML = scenarios.map(scenario => {
    const stats = scenarioStats(scenario);
    const summary = stats.rejected ? `${stats.rejected} 条退回` : `${stats.reviewed}/${stats.total} 已审`;
    const trigger = scenario.triggerability;
    const triggerSummary = trigger ? `重放：${TIER_LABELS[trigger.triggerability_tier] || trigger.triggerability_tier} · 发出 ${trigger.event_count} 次` : "重放：无证据";
    return `<button class="scenario-button ${scenario.scenario_id === activeScenarioId ? "active" : ""}" data-scenario="${escapeHtml(scenario.scenario_id)}"><span class="count">${stats.passed}/${stats.total}</span><strong>${escapeHtml(scenario.scenario_id)}</strong><small>${escapeHtml(scenario.title)}</small><small>${summary}</small><small class="trigger-tier">${escapeHtml(triggerSummary)}</small></button>`;
  }).join("") || '<div class="empty-filter">没有符合筛选条件的场景</div>';
  document.querySelectorAll("[data-scenario]").forEach(button => {
    button.addEventListener("click", () => {
      activeScenarioId = button.dataset.scenario;
      render();
      window.scrollTo({top: 0, behavior: "smooth"});
    });
  });
}

function renderMetrics() {
  const records = reviewAssets().map(recordFor);
  const inScopeScenarioCount = packet.scenarios.filter(
    scenario => assetsInScope(scenario).length > 0
  ).length;
  const passed = records.filter(item => item.human_status === "passed").length;
  const rejected = records.filter(item => item.human_status === "rejected").length;
  const pending = records.length - passed - rejected;
  const missing = assetTypeFilter === "talking_head"
    ? 0
    : (packet.missing_scenario_ids?.length || 0);
  $("metrics").innerHTML = [
    [`${inScopeScenarioCount}/${packet.expected_scenario_count || inScopeScenarioCount}`, "当前通道有视频 / 计划 scenarios"],
    [records.length, `${LANE_LABELS[assetTypeFilter]}待审核资产`],
    [assetTypeFilter === "online_nonverbal"
      ? (packet.talking_head_asset_count ?? 0)
      : (packet.online_asset_count ?? packet.asset_count),
    assetTypeFilter === "online_nonverbal"
      ? "Offline 口型（不计本轮）"
      : "Online 状态（不计本轮）"],
    [passed, "人工通过"],
    [pending, "仍待审核"],
    [rejected, "人工退回"]
  ].map(([value, label]) => `<div class="metric"><b>${value}</b><span>${label}</span></div>`).join("");
  const reviewComplete = pending === 0 && rejected === 0;
  $("batchBadge").className = `badge ${reviewComplete ? "good" : ""}`;
  $("batchBadge").textContent = reviewComplete
    ? `${LANE_LABELS[assetTypeFilter]} · ${passed}/${records.length} 人工审核通过`
    : `${LANE_LABELS[assetTypeFilter]} · ${pending} 待审${missing ? ` · ${missing} 场景缺视频` : ""}`;
}

function renderProgress() {
  if (!packet) return;
  const records = reviewAssets().map(recordFor);
  const reviewed = records.filter(item => item.human_status !== "pending").length;
  const passed = records.filter(item => item.human_status === "passed").length;
  $("progress").textContent = `${reviewed}/${records.length} 已审 · ${passed} 通过`;
  renderMetrics();
}


function asPercent(value) {
  return Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
}

function signed(value) {
  if (!Number.isFinite(value)) return "—";
  return value > 0 ? `+${value}` : String(value);
}

function conditionEvidence(event) {
  return (event.conditions || []).map(item =>
    `${escapeHtml(item.variable)}：${item.previous}→${item.current}（Δ${signed(item.delta)}，条件 ${escapeHtml(item.operator)} ${item.threshold}）`
  ).join("；");
}

function triggerConditionPanel(asset) {
  const triggers = asset.trigger_conditions || [];
  const observed = asset.observed_trigger_events || [];
  const rows = triggers.map(trigger => {
    const entries = Object.entries(trigger.conditions || {});
    const condition = entries.map(([variable, rule]) =>
      `<code>${escapeHtml(variable)} ${escapeHtml(rule.operator)} ${rule.threshold}</code>`
    ).join(" 且 ");
    const hits = observed.filter(item => item.trigger_id === trigger.trigger_id);
    const evidence = hits.length
      ? hits.map(item => `<div class="hit-evidence"><b>${escapeHtml(item.turn_id)}</b> ${conditionEvidence(item)}</div>`).join("")
      : '<span class="muted">该保存轨迹的离线重放未发出此事件</span>';
    return `<div class="trigger-row"><div><b>${escapeHtml(STATE_FAMILY_LABELS[trigger.source_state_family] || trigger.source_state_family)}</b><span>${escapeHtml(trigger.source_direction === "increase" ? "上升" : "下降")}</span></div><div>${condition}</div><div>${evidence}</div></div>`;
  }).join("");
  const summary = triggers.map(trigger => {
    const stateFamily = STATE_FAMILY_LABELS[trigger.source_state_family] || trigger.source_state_family;
    const direction = trigger.source_direction === "increase" ? "上升" : "下降";
    const condition = Object.entries(trigger.conditions || {}).map(([variable, rule]) =>
      `${escapeHtml(variable)} ${escapeHtml(rule.operator)} ${rule.threshold}`
    ).join(" 且 ");
    return `<li><b>${escapeHtml(stateFamily)} / ${escapeHtml(trigger.source_state_variable || "—")} ${direction}</b><code>${condition || "无阈值条件"}</code></li>`;
  }).join("");
  return `<div class="trigger-summary"><div class="summary-title">审核页常显触发条件</div><ul>${summary || '<li class="muted">没有与此事件族对应的触发条件。</li>'}</ul></div><details class="trigger-box" ${observed.length ? "open" : ""}><summary>查看离线重放证据 · 发出 ${observed.length} 次</summary><p class="trigger-note">这是保存状态快照上的反事实重放，不表示历史 rollout 当时播放过视频。重放还受：单轮最多 1 个、全局冷却 2 轮、事件族冷却 3 轮、同一触发器最多 1 次、每局最多 5 次约束。</p>${rows || '<p class="muted">没有与此事件族对应的触发条件。</p>'}</details>`;
}

function talkingHeadSelection(asset) {
  const reasons = (asset.importance_reasons || []).map(reason =>
    `<span>${escapeHtml(IMPORTANCE_REASON_LABELS[reason] || reason)}</span>`
  ).join("");
  return `<div class="selection-box"><div><b>来源节点</b><span>${escapeHtml(asset.trajectory_id || "—")} · ${escapeHtml(asset.turn_id || "—")}</span></div><div><b>入选分</b><span>${asset.importance_score ?? "—"}</span></div><div><b>生成版本</b><span>${escapeHtml(asset.prompt_id || "—")}</span></div><div class="selection-reasons"><b>入选原因</b><span class="reason-tags">${reasons || '<span class="muted">未记录</span>'}</span></div></div>`;
}

function renderTriggerability(scenario) {
  const audit = packet.triggerability || {};
  const root = $("triggerabilityPanel");
  if (!audit.available) {
    root.innerHTML = '<h2>触发容易度</h2><p class="warning">当前没有可用的轨迹重放证据。</p>';
    return;
  }
  const summary = audit.summary || {};
  const stateCounts = summary.source_state_family_counts || {};
  const blocked = Object.entries(summary.blocked_reason_counts || {})
    .map(([key, value]) => `<span>${escapeHtml(BLOCKED_REASON_LABELS[key] || key)} ${value}</span>`).join("");
  const coverage = Object.entries(STATE_FAMILY_LABELS).map(([key, label]) =>
    `<div class="coverage-item"><span>${label}</span><b>${stateCounts[key] || 0}</b></div>`
  ).join("");
  const local = scenario.triggerability || {};
  const scaleText = summary.target_pass
    ? "达到既定 reachability 目标，可进入有界 scale"
    : "中位触发数未达 3：暂缓全量，只做有界 scale";
  root.innerHTML = `<div class="triggerability-head"><div><div class="eyebrow">TRIGGERABILITY · COUNTERFACTUAL REPLAY</div><h2>被测模型是否容易触发？</h2></div><span class="scale-status ${summary.target_pass ? "good" : "warning"}">${scaleText}</span></div>
    <p class="audit-warning">${escapeHtml(audit.warning)}</p>
    <div class="trigger-metrics"><div><b>${summary.at_least_two_event_count}/${audit.evaluated_scenario_count || "—"}</b><span>重放至少发出 2 次</span></div><div><b>${summary.median_event_count ?? "—"}</b><span>重放发出次数中位数（目标 3）</span></div><div><b>t${summary.median_first_fire_turn ?? "—"}</b><span>首次重放发出轮次中位数</span></div><div><b>${local.event_count ?? "—"}</b><span>当前场景重放发出</span></div></div>
    <div class="trigger-columns"><div><h3>四维重放发出来源（50 条保存轨迹）</h3><div class="coverage-grid">${coverage}</div><p class="warning">行为倾向占比过高时，即使“很早发出”，也不能视为四维覆盖良好。</p></div><div><h3>当前场景</h3><p>${escapeHtml(TIER_LABELS[local.triggerability_tier] || "无证据")} · 首次 t${local.first_fire_turn ?? "—"} · 重放发出 ${local.event_count ?? 0} 次 · ${local.distinct_state_family_count ?? 0} 个状态维度</p><p>有条件命中的轮次占比 ${asPercent(local.eligible_turn_fraction)}；命中轮次重放发出率 ${asPercent(local.fire_given_eligible_turn_fraction)}</p><div class="blocked">${blocked}</div></div></div>
    <details class="method"><summary>评估口径</summary><p>“易触发”仅表示保存轨迹的离线重放至少发出 2 次且首次不晚于第 3 轮；“可触发”表示重放至少发出 1 次；零发出时再按距阈值是否仅差 1 点区分近失。该分级不是 Gate，不表示历史 rollout 当时播放过视频，也不等同于因果可控性。</p></details>`;
}

function assetCard(asset) {
  const record = recordFor(asset);
  const metadata = asset.structural_metadata || {};
  const talkingHead = asset.asset_type === "talking_head";
  const checks = checkKeysFor(asset).map(key => `<label class="check"><input type="checkbox" data-check="${escapeHtml(key)}" ${record.checks[key] === true ? "checked" : ""}><span>${escapeHtml(CHECK_LABELS[key] || key)}</span></label>`).join("");
  const laneBanner = talkingHead
    ? `<div class="lane-banner talking-lane"><b>响应口型视频 · 有语音</b><span>必须逐字说出台词；语音要像当面对话，禁止机械逐字念稿。</span></div>`
    : `<div class="lane-banner state-lane"><b>状态触发素材 · 无台词</b><span>只允许动作与非语言声音；若出现说话或说话式口型应退回。</span></div>`;
  return `<article class="video-card ${talkingHead ? "talking-card" : "state-card"} status-${record.human_status}" data-request="${escapeHtml(asset.request_id)}">
    <div class="video-wrap"><video controls playsinline preload="metadata" aria-label="${escapeHtml(asset.event_family_label)}视频" src="${escapeHtml(asset.url)}"></video></div>
    <div class="card-body">
      ${laneBanner}
      <div class="card-head"><div><h3>${escapeHtml(asset.event_family_label)}${asset.is_anchor ? '<span class="anchor">身份锚点</span>' : ""}${talkingHead ? '<span class="anchor">口型</span>' : ""}</h3><div class="event-id">${escapeHtml(asset.event_family)}</div></div>
      <select class="status-select" aria-label="审核状态"><option value="pending" ${record.human_status === "pending" ? "selected" : ""}>待审核</option><option value="passed" ${record.human_status === "passed" ? "selected" : ""}>通过</option><option value="rejected" ${record.human_status === "rejected" ? "selected" : ""}>退回</option></select></div>
      <div class="cue"><b>预期动作：</b>${escapeHtml(asset.expected_cue)}</div>
      <div class="cue"><b>${talkingHead ? "应说台词" : "预期声音"}：</b>${escapeHtml(asset.expected_audio)}</div>
      ${talkingHead ? talkingHeadSelection(asset) : ""}
      ${talkingHead && asset.source_public_response ? `<details class="trigger-box"><summary>中文原公开回复</summary><p>${escapeHtml(asset.source_public_response)}</p></details>` : ""}
      ${talkingHead ? "" : triggerConditionPanel(asset)}
      <div class="technical"><span>${metadata.duration_seconds_actual ?? "—"}s</span><span>${metadata.width ?? "—"}×${metadata.height ?? "—"}</span><span>${metadata.fps ?? "—"} fps</span><span>SHA ${escapeHtml(asset.video_sha256.slice(0, 10))}</span></div>
      <div class="checks">${checks}</div>
      <textarea class="notes" placeholder="问题描述或修改建议">${escapeHtml(record.notes)}</textarea>
      <div class="card-actions"><button class="pass-one primary">全部检查通过</button><button class="reject-one">标记退回</button></div>
    </div>
  </article>`;
}

function bindCards() {
  document.querySelectorAll("video").forEach(video => {
    video.muted = false;
    video.volume = 1;
    video.addEventListener("play", () => {
      video.muted = false;
      video.volume = 1;
      document.querySelectorAll("video").forEach(other => {
        if (other !== video) other.pause();
      });
    });
  });
  document.querySelectorAll(".video-card").forEach(card => {
    const asset = allAssets().find(item => item.request_id === card.dataset.request);
    const record = recordFor(asset);
    card.querySelectorAll("[data-check]").forEach(input => {
      input.addEventListener("change", () => {
        record.checks[input.dataset.check] = input.checked;
        if (record.human_status === "passed" && !Object.values(record.checks).every(Boolean)) {
          record.human_status = "pending";
        }
        saveDraft();
        render();
      });
    });
    card.querySelector(".status-select").addEventListener("change", event => {
      record.human_status = event.target.value;
      if (record.human_status === "passed") {
        Object.keys(record.checks).forEach(key => record.checks[key] = true);
      }
      saveDraft();
      render();
    });
    card.querySelector(".notes").addEventListener("input", event => {
      record.notes = event.target.value;
      saveDraft();
    });
    card.querySelector(".pass-one").addEventListener("click", () => {
      Object.keys(record.checks).forEach(key => record.checks[key] = true);
      record.human_status = "passed";
      saveDraft();
      render();
    });
    card.querySelector(".reject-one").addEventListener("click", () => {
      record.human_status = "rejected";
      saveDraft();
      render();
    });
  });
}

function render() {
  const inScopeScenarios = packet.scenarios.filter(
    item => assetsInScope(item).length > 0
  );
  const scenario = inScopeScenarios.find(
    item => item.scenario_id === activeScenarioId
  ) || inScopeScenarios[0];
  if (!scenario) {
    activeScenarioId = null;
    $("scenarioHeader").innerHTML = `<h2>${escapeHtml(LANE_LABELS[assetTypeFilter])}</h2><p>当前批次还没有这一类视频。</p>`;
    $("videoGrid").innerHTML = '<div class="empty-lane panel">当前通道暂无可审核视频。</div>';
    renderScenarioList();
    renderProgress();
    return;
  }
  activeScenarioId = scenario.scenario_id;
  const identity = scenario.assets[0]?.identity || {};
  const stateCount = scenario.assets.filter(asset => asset.asset_type === "online_nonverbal").length;
  const talkingCount = scenario.assets.filter(asset => asset.asset_type === "talking_head").length;
  const visibleAssets = assetsInScope(scenario);
  $("scenarioHeader").innerHTML = `<h2>${escapeHtml(scenario.scenario_id)} · ${escapeHtml(scenario.title)}</h2><p>${escapeHtml(scenario.background)}</p><div class="scenario-meta"><span>环境角色：${escapeHtml(scenario.environment_character)}</span><span>身份设定：${escapeHtml(identity.appearance || "")}</span><span>状态触发 ${stateCount}</span><span>响应口型 ${talkingCount}</span><span>轨迹触发：${scenario.triggerability?.event_count ?? "—"}</span></div>`;
  renderTriggerability(scenario);
  $("videoGrid").innerHTML = visibleAssets.length
    ? visibleAssets.map(assetCard).join("")
    : '<div class="empty-lane panel">当前场景还没有这一类视频。状态触发素材与响应口型视频是两条独立交付通道。</div>';
  renderScenarioList();
  renderMetrics();
  renderProgress();
  bindCards();
}

function moveScenario(direction, pendingOnly = false) {
  const candidates = packet.scenarios.filter(scenario => {
    const stats = scenarioStats(scenario);
    return stats.total > 0 && (!pendingOnly || stats.reviewed < stats.total);
  });
  if (!candidates.length) {
    toast(pendingOnly ? "已经没有待审场景" : "没有可切换场景");
    return;
  }
  const currentIndex = candidates.findIndex(item => item.scenario_id === activeScenarioId);
  const nextIndex = currentIndex < 0
    ? 0
    : (currentIndex + direction + candidates.length) % candidates.length;
  activeScenarioId = candidates[nextIndex].scenario_id;
  render();
  window.scrollTo({top: 0, behavior: "smooth"});
}

function setScenarioStatus(status) {
  const scenario = packet.scenarios.find(item => item.scenario_id === activeScenarioId);
  if (!scenario) return;
  assetsInScope(scenario).forEach(asset => {
    const record = recordFor(asset);
    record.human_status = status;
    if (status === "passed") Object.keys(record.checks).forEach(key => record.checks[key] = true);
    if (status === "pending") Object.keys(record.checks).forEach(key => record.checks[key] = null);
  });
  saveDraft();
  render();
}

function exportReview() {
  const reviewer = $("reviewer").value.trim();
  if (!reviewer) {
    toast("请先填写审核人姓名或 ID");
    $("reviewer").focus();
    return;
  }
  const now = new Date().toISOString();
  const items = reviewAssets().map(asset => {
    const record = structuredClone(recordFor(asset));
    record.reviewer = record.human_status === "pending" ? "" : reviewer;
    record.reviewed_at_utc = record.human_status === "pending" ? "" : now;
    return record;
  });
  const payload = {
    format: "socialflux_multimodal_asset_review_v1",
    exported_at_utc: now,
    reviewer,
    asset_scope: assetTypeFilter,
    scenario_count: packet.scenarios.filter(
      scenario => assetsInScope(scenario).length > 0
    ).length,
    item_count: items.length,
    review_summary: {
      passed: items.filter(item => item.human_status === "passed").length,
      rejected: items.filter(item => item.human_status === "rejected").length,
      pending: items.filter(item => item.human_status === "pending").length
    },
    source_profile: packet.profile,
    source_asset_version: packet.asset_version,
    items
  };
  const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], {type: "application/json"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `multimodal_review_${assetTypeFilter}_${now.slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
  toast("审核 JSON 已导出");
}

async function importReview(file) {
  const value = JSON.parse(await file.text());
  const items = value.items || [];
  if (!Array.isArray(items)) throw new Error("文件中没有 items 数组");
  const active = new Map(allAssets().map(asset => [asset.request_id, asset]));
  let imported = 0;
  let skipped = 0;
  items.forEach(item => {
    const asset = active.get(item.request_id);
    if (!asset || item.video_sha256 !== asset.video_sha256) {
      skipped += 1;
      return;
    }
    draft.items[item.request_id] = item;
    recordFor(asset);
    imported += 1;
  });
  if (value.reviewer) draft.reviewer = value.reviewer;
  $("reviewer").value = draft.reviewer || "";
  saveDraft();
  render();
  toast(`已导入 ${imported} 条${skipped ? `，跳过 ${skipped} 条非当前视频记录` : ""}`);
}

async function init() {
  loadDraft();
  $("batchSelect").value = ACTIVE_BATCH;
  $("assetTypeFilter").value = assetTypeFilter;
  $("reviewer").value = draft.reviewer || "";
  const response = await fetch(
    `/api/online-multimodal-review/${ACTIVE_BATCH}`,
    {cache: "no-store"}
  );
  if (!response.ok) throw new Error("HTTP " + response.status);
  packet = await response.json();
  if (!packet.scenarios?.length) throw new Error("没有可审核视频");
  $("batchTitle").textContent = `${packet.batch_label || ACTIVE_BATCH} · ${LANE_LABELS[assetTypeFilter]}审核`;
  activeScenarioId = packet.scenarios.find(
    scenario => scenario.scenario_id === pageParams.get("scenario") && assetsInScope(scenario).length > 0
  )?.scenario_id || packet.scenarios.find(
    scenario => assetsInScope(scenario).length > 0
  )?.scenario_id || null;
  allAssets().forEach(recordFor);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
  render();
  $("reviewer").addEventListener("input", saveDraft);
  $("batchSelect").addEventListener("change", event => {
    const url = new URL(window.location.href);
    url.searchParams.set("batch", event.target.value);
    window.location.assign(url.toString());
  });
  $("passScenario").addEventListener("click", () => setScenarioStatus("passed"));
  $("pendingScenario").addEventListener("click", () => setScenarioStatus("pending"));
  $("previousScenario").addEventListener("click", () => moveScenario(-1));
  $("nextPending").addEventListener("click", () => moveScenario(1, true));
  $("statusFilter").addEventListener("change", event => {
    statusFilter = event.target.value;
    renderScenarioList();
  });
  $("scenarioSearch").addEventListener("input", event => {
    scenarioSearch = event.target.value;
    renderScenarioList();
  });
  $("assetTypeFilter").addEventListener("change", event => {
    assetTypeFilter = event.target.value;
    $("batchTitle").textContent = `${packet.batch_label || ACTIVE_BATCH} · ${LANE_LABELS[assetTypeFilter]}审核`;
    if (!packet.scenarios.some(
      scenario => scenario.scenario_id === activeScenarioId && assetsInScope(scenario).length > 0
    )) {
      activeScenarioId = packet.scenarios.find(
        scenario => assetsInScope(scenario).length > 0
      )?.scenario_id || null;
    }
    const url = new URL(window.location.href);
    url.searchParams.set("lane", assetTypeFilter);
    window.history.replaceState({}, "", url.toString());
    render();
  });
  $("exportReview").addEventListener("click", exportReview);
  $("importReview").addEventListener("click", () => $("importFile").click());
  $("importFile").addEventListener("change", async event => {
    try { await importReview(event.target.files[0]); }
    catch (error) { toast("导入失败：" + error.message); }
    event.target.value = "";
  });
  $("clearDraft").addEventListener("click", () => {
    if (!confirm(`确认清空这 ${packet.asset_count} 条视频的浏览器审核草稿？`)) return;
    localStorage.removeItem(STORAGE_KEY);
    draft = {reviewer: "", items: {}};
    $("reviewer").value = "";
    allAssets().forEach(recordFor);
    render();
    toast("浏览器草稿已清空");
  });
}

init().catch(error => {
  $("batchBadge").textContent = "加载失败";
  $("scenarioHeader").innerHTML = `<h2 class="error">视频审核页加载失败</h2><p>${escapeHtml(error.message)}</p>`;
  $("progress").textContent = "请确认 Web 服务与资产文件存在";
});
