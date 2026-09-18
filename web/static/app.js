const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const STORAGE_KEY = 'socialflux.annotation.drafts.v1';

const state = {
  data: null,
  detail: null,
  contract: null,
  scenarioId: null,
  trajectoryId: null,
  taskType: 'all',
  taskId: null,
  pilot: null,
  pilotTrajectoryId: null,
  view: 'scenario',
  search: '',
  drafts: loadDrafts()
};

const LABELS = {
  social_plausibility: '社会情境可信度',
  tradeoff_quality: '真实权衡质量',
  history_necessity: '历史依赖必要性',
  strategy_space: '策略空间丰富度',
  motivation_coherence: '人物动机连贯性',
  surface_originality: '表层内容原创性',
  character_coherence: '人物与动机连贯性',
  interaction_richness: '互动与长期演化容量',
  t1_t4_suitability: 'T1–T4 综合适配度',
  variables_relevant: 'S0 状态变量与场景相关',
  values_justified: 'S0/D0 数值有背景依据',
  no_policy_effect_baked_in: '初始值未预写某个策略效果',
  initial_triggers_inactive: '视频触发器在初始状态不误触发',
  multiple_future_paths_possible: '允许多条合理未来路径',
  shared_across_models_and_seeds: 'S0/D0 可跨模型与 seed 共用',
  social_mechanism: '社会机制明确',
  real_tradeoff: '存在真实权衡',
  both_sides_have_goals: '双方都有目标',
  no_unique_script: '不存在唯一脚本',
  history_changes_meaning: '历史会改变含义',
  multiple_plausible_trajectories: '多条合理演化路径',
  t1_suitability: '适合 T1',
  t2_suitability: '适合 T2',
  t3_suitability: '适合 T3',
  t4_adaptation_opportunity: '提供 T4 适应空间',
  no_hidden_state_leakage: '无隐藏状态泄漏',
  narrative_provenance: '叙事来源可追溯',
  narrative_originalization: '影视抽象已原创化',
  quality_checklist: '质量清单完整',
  human_approval: '真人审核与 S0/D0 冻结',
  dialogue_coherence: '对话连贯性',
  history_dependence: '历史依赖',
  character_consistency: '人物一致性',
  state_response_consistency: '状态—回应一致性',
  interaction_progression: '互动推进',
  naturalness: '自然度',
  hidden_state_leakage: '隐藏状态泄漏',
  malformed_output: '输出格式损坏',
  repetitive_loop: '重复循环',
  severe_character_contradiction: '严重人物矛盾',
  broken_dialogue_logic: '对话逻辑断裂',
  meaningless_premature_ending: '无意义提前结束',
  nonsensical_state_oscillation: '状态无意义振荡',
  implementation_induced_state_saturation: '实现导致状态饱和',
  future_information_leakage: '未来信息泄漏',
  unusable_trajectory: '无法形成历史依赖片段',
  from_free_form_rollout: '来自自由 rollout',
  target_state_meaningful: '目标状态有意义',
  history_evidence_present: '历史证据充分',
  current_only_insufficient: '仅当前信息不足',
  nontrivial_transition: '状态变化非平凡',
  human_answerable: '人类可回答',
  histories_from_natural_rollouts: '两段历史来自自然 rollout',
  meaningful_history_divergence: '历史差异有意义',
  shared_observation_identical: '共享观察严格一致',
  shared_video_identical_or_not_applicable: '共享视频一致或不适用',
  shared_observation_natural_after_both: '共享观察接在两段历史后都自然',
  state_interpretation_differs: '状态解释应有差异',
  current_observation_nonleaking: '当前观察不泄漏历史差异',
  causal_history_evidence_localizable: '可定位因果历史证据',
  checkpoint_from_natural_rollout: '检查点来自自然 rollout',
  actions_socially_plausible: '候选行动社会上合理',
  no_obvious_good_bad_choice: '没有显然好坏答案',
  real_social_tradeoff: '存在真实社会权衡',
  immediate_effect_judgable: '即时影响可判断',
  delayed_effect_judgable: '延迟影响可判断',
  same_continuation_protocol: '延续协议一致',
  no_simulator_instability_reversal: '无模拟器不稳定反转',
  human_effect_judgable: '人类可判断行动影响'
};

function loadDrafts() {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    return {reviewer: value.reviewer || '', records: value.records || {}};
  } catch {
    return {reviewer: '', records: {}};
  }
}

function saveDrafts() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.drafts));
  renderProgress();
}

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));

const label = (key) => LABELS[key] || String(key).replaceAll('_', ' ');
const flat = (obj, prefix = '') => Object.entries(obj || {}).flatMap(([key, value]) =>
  typeof value === 'object' && value !== null
    ? flat(value, prefix ? `${prefix}.${key}` : key)
    : [[prefix ? `${prefix}.${key}` : key, value]]
);
const clamp = (value) => Math.max(0, Math.min(100, Number(value) * 10));
const statusDone = (value) => value && value !== 'pending';

async function get(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function currentRecord(kind, id) {
  const key = `${kind}:${id}`;
  const existing = state.drafts.records[key];
  if (kind === 'scenario' && state.detail?.gate1_review_packet?.scenario_id === id) {
    const packet = state.detail.gate1_review_packet;
    if (existing?.scenario_sha256 === packet.scenario_sha256) return existing;
    return {
      record_type: kind,
      record_id: id,
      scenario_id: id,
      scenario_sha256: packet.scenario_sha256,
      reviewer: state.drafts.reviewer,
      status: packet.decision || 'pending',
      ratings: structuredClone(packet.quality_scores || {}),
      checks: {},
      attestations: structuredClone(packet.attestations || {}),
      issues: existing ? {prior_version: existing.notes || '旧版本草稿已因场景哈希变化而重置'} : {},
      prior_scenario_sha256: existing?.scenario_sha256 || null,
      human_attestation: false,
      updated_at: null
    };
  }
  if (existing) return existing;
  return {
    record_type: kind,
    record_id: id,
    scenario_id: state.scenarioId,
    reviewer: state.drafts.reviewer,
    status: 'pending',
    updated_at: null
  };
}

function updateRecord(kind, id, path, value) {
  const key = `${kind}:${id}`;
  const record = structuredClone(currentRecord(kind, id));
  let cursor = record;
  const parts = path.split('/');
  parts.slice(0, -1).forEach((part) => {
    cursor[part] = cursor[part] || {};
    cursor = cursor[part];
  });
  cursor[parts.at(-1)] = value;
  record.reviewer = state.drafts.reviewer;
  record.updated_at = new Date().toISOString();
  state.drafts.records[key] = record;
  saveDrafts();
  renderScenarioList();
}

function showToast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.add('show');
  setTimeout(() => $('#toast').classList.remove('show'), 2200);
}

function renderProgress() {
  if (!state.data) return;
  const records = Object.values(state.drafts.records);
  const scenarioRecords = records.filter((item) => item.record_type === 'scenario');
  const decided = scenarioRecords.filter((item) => statusDone(item.status)).length;
  const attested = scenarioRecords.filter((item) => item.human_attestation && statusDone(item.status)).length;
  const allDone = records.filter((item) => statusDone(item.status)).length;
  $('#localProgress').textContent = `Gate 1 已判定 ${decided}/20 · 真人确认 ${attested}/20 · 全部草稿 ${allDone}`;
}

function renderOverview() {
  const manifest = state.data.pipeline_manifest || {};
  const totals = manifest.totals || {};
  const gate = state.data.quality_gates || state.data.acceptance.gate || {};
  $('#scenarioCount').textContent = state.data.scenario_count;
  $('#gateBadge').textContent = gate.research_ready || gate.research_acceptance ? 'RESEARCH GATE · PASS' : 'RESEARCH GATE · PENDING';
  const screening = state.data.screening || {};
  const values = [
    ['SCENARIOS', state.data.scenario_count, '情节与 S0/D0'],
    ['NEW 20T RAW', state.data.long_rollout_generation?.completed_slot_count ?? 0, `目标 ${state.data.long_rollout_generation?.expected_slot_count ?? 0} · ${state.data.long_rollout_generation?.status || 'not_started'}`],
    ['AUDIT QUEUE', screening.human_review_queue_count ?? 0, `库存 ${screening.inventory_count ?? 0} · 每场景最终 1 条`],
    ['PROVISIONAL WINNERS', screening.provisional_selected_count ?? 0, '待人工逐场景确认'],
    ['TASKS', totals.instances ?? 0, `T1 ${totals.t1 ?? 0} · T2 ${totals.t2 ?? 0} · T3 ${totals.t3 ?? 0}`],
    ['LOCAL DRAFTS', Object.keys(state.drafts.records).length, '仅当前浏览器']
  ];
  $('#overview').innerHTML = values.map(([name, value, note]) =>
    `<div class="metric"><div class="metric-label">${name}</div><div class="metric-value">${esc(value)}</div><div class="metric-note">${esc(note)}</div></div>`
  ).join('');
}

function renderScenarioList() {
  if (!state.data) return;
  const filtered = state.data.scenarios.filter((item) =>
    `${item.scenario_id} ${item.title} ${item.mechanism}`.toLowerCase().includes(state.search.toLowerCase())
  );
  $('#scenarioList').innerHTML = filtered.map((item) => {
    const record = currentRecord('scenario', item.scenario_id);
    return `<button class="scenario-item ${item.scenario_id === state.scenarioId ? 'active' : ''}" data-scenario="${esc(item.scenario_id)}">
      <span class="scenario-index">${esc(item.scenario_id.replace('IA_PIPE_', ''))}</span>
      <span><strong>${esc(item.title)}</strong><small>${esc(item.mechanism)}</small></span>
      <i class="review-dot ${statusDone(record.status) && record.human_attestation ? 'done' : ''}"></i>
    </button>`;
  }).join('') || '<div class="empty-side">没有匹配的 scenario</div>';
}

function renderHeader() {
  const scenario = state.detail.scenario;
  const summary = state.detail.summary;
  const persona = scenario.environment_agent?.persona || {};
  $('#scenarioHeader').classList.remove('loading');
  $('#scenarioHeader').innerHTML = `
    <div class="scenario-heading">
      <div class="eyebrow">${esc(scenario.scenario_id)} · ${esc(scenario.source?.type)}</div>
      <h2>${esc(scenario.title)}</h2>
      <p>${esc(scenario.background)}</p>
      <div class="tag-row">
        <span class="tag">${esc(scenario.mechanism)}</span>
        <span class="tag warning">${esc(scenario.construction_status?.quality_gate)}</span>
        <span class="tag warning">${esc(scenario.construction_status?.initial_state)}</span>
      </div>
    </div>
    <div class="header-persona">
      <span class="mini-label">TARGET PERSONA</span>
      <strong>${esc(persona.name || '—')}</strong>
      <p>${esc(persona.role || '')} · patience ${esc(persona.patience)} · empathy ${esc(persona.empathy)}</p>
      <div class="header-counts"><b>${summary.screening?.final_trajectory_count ?? 0}</b> 最终 rollout <b>${state.detail.rollouts?.length || 0}</b> 人工候选 <b>${summary.task_count}</b> task <b>${summary.trigger_count}</b> video</div>
    </div>`;
}

function stateBars(values) {
  return flat(values).map(([key, value]) => `
    <div class="state-row">
      <span title="${esc(key)}">${esc(key)}</span>
      <i><b style="width:${clamp(value)}%"></b></i>
      <strong>${esc(value)}</strong>
    </div>`
  ).join('');
}

function listItems(items) {
  return `<ol class="clean-list">${(items || []).map((item) => `<li>${esc(item)}</li>`).join('')}</ol>`;
}

function renderScenarioView() {
  const scenario = state.detail.scenario;
  const design = scenario.narrative_design || {};
  const longitudinal = scenario.longitudinal_design || null;
  const persona = scenario.environment_agent?.persona || {};
  const modelContract = state.detail.evaluated_model_contract || {};
  const assets = state.detail.media_assets || [];
  const scenarioIndex = state.data.scenarios.findIndex((item) => item.scenario_id === state.scenarioId);
  $('#viewToolbar').innerHTML = `<div class="toolbar-group"><button class="icon-button" data-nav-scenario="-1" ${scenarioIndex <= 0 ? 'disabled' : ''}>← 上一条</button><span class="toolbar-title">${scenarioIndex + 1}/20 · 情节全貌</span><button class="icon-button" data-nav-scenario="1" ${scenarioIndex >= state.data.scenarios.length - 1 ? 'disabled' : ''}>下一条 →</button></div><span class="toolbar-note">先判断故事是否值得进入 benchmark，再审核 S0/D0、任务适配与视频阈值</span>`;
  $('#viewContent').innerHTML = `
    <section class="panel content-panel">
      <div class="section-kicker">STORY MAP</div>
      <h3>冲突结构与人物目标</h3>
      <div class="two-column">
        <div class="role-card agent">
          <span>被评估模型扮演的角色</span>
          <strong>${esc(scenario.evaluated_agent_role?.name)}</strong>
          <p><b>身份：</b>${esc(scenario.evaluated_agent_role?.role)}</p>
          <p><b>公开目标：</b>${esc(scenario.evaluated_agent_role?.explicit_goal)}</p>
        </div>
        <div class="role-card environment">
          <span>环境角色 / 状态目标</span>
          <strong>${esc(persona.name)}</strong>
          <p><b>身份：</b>${esc(persona.role)}</p>
          <p><b>作者侧目标：</b>${esc(scenario.environment_agent?.explicit_goal)}</p>
        </div>
      </div>
      <div class="fact-grid">
        <div><span>关系结构</span><p>${esc(design.relationship_structure)}</p></div>
        <div><span>权力结构</span><p>${esc(design.power_structure)}</p></div>
        <div><span>目标冲突</span><p>${esc(design.goal_conflict)}</p></div>
        <div><span>信息不对称</span><p>${esc(design.information_asymmetry)}</p></div>
      </div>
      <div class="split-section">
        <div><h4>关键历史</h4>${listItems(design.relevant_history)}</div>
        <div><h4>合理选择空间</h4>${listItems(design.meaningful_choice_space)}</div>
      </div>
      <div class="private-research-card">
        <div><span>RESEARCHER-ONLY PERSONA</span><h4>环境角色完整 persona</h4></div>
        <div class="persona-grid">${flat(persona).map(([key, value]) =>
          `<div><span>${esc(key)}</span><strong>${esc(value)}</strong></div>`
        ).join('')}</div>
        <div class="hidden-intention"><b>Hidden intention · 作者侧私有</b><p>${esc(scenario.environment_agent?.hidden_intention)}</p></div>
      </div>
    </section>

    <section class="panel content-panel">
      <div class="section-kicker">LONGITUDINAL PLAN</div>
      <h3>20 轮中的互动片段、时间与事件来源</h3>
      ${longitudinal ? `<p class="instruction">同一组人物与关系共享完整历史；时间单位 ${esc(longitudinal.time_unit)}。时间本身不代表履约。下列内容只是场景冻结的外生事件候选，不是对话池或动作池；模型每轮仍自由生成。</p>
        <div class="trigger-grid">${(longitudinal.segments || []).map((segment, index) => `<article class="trigger-card"><div class="trigger-title"><strong>${esc(segment.segment_id)}</strong><span>${esc(segment.min_turns)}–${esc(segment.max_turns)} 轮 ${index ? `· +${esc(segment.advance_by)} ${esc(longitudinal.time_unit)}` : '· 起点'}</span></div><p>${esc(segment.reason)}</p><small>${esc(segment.public_time_record || '初始互动')}<br>${esc(segment.opening_response || scenario.opening_response || '')}</small></article>`).join('')}</div>
        ${(longitudinal.event_pools || []).map((pool) => `<div class="rationale"><b>冻结的外生事件候选 ${esc(pool.event_pool_id)} · 仅在触发条件满足时发生；T3 分支共享</b>${listItems((pool.outcomes || []).map((outcome) => `${outcome.outcome_id} / ${outcome.commitment_effect}：${outcome.public_record}`))}</div>`).join('')}` : '<div class="empty">当前场景尚未作者化多片段时间线，按单段连续互动运行。</div>'}
    </section>

    <section class="panel content-panel model-contract">
      <div class="section-kicker">EVALUATED MODEL INPUT</div>
      <h3>被测模型实际收到的角色卡与 Prompt</h3>
      <div class="contract-banner">
        <strong>${esc(modelContract.prompt_id)} · ${esc(modelContract.horizon_turns)} 轮</strong>
        <p>${esc(modelContract.boundary_note)}</p>
      </div>
      <div class="two-column">
        <div class="role-card agent">
          <span>模型身份</span>
          <strong>${esc(modelContract.role_card?.name)}</strong>
          <p>${esc(modelContract.role_card?.role)}</p>
          <p><b>全程目标：</b>${esc(modelContract.role_card?.explicit_goal)}</p>
        </div>
        <div class="role-card boundary">
          <span>明确排除的私有信息</span>
          ${listItems(modelContract.private_author_fields_excluded)}
        </div>
      </div>
      <details class="prompt-preview" open>
        <summary>查看固定 Prompt 模板</summary>
        <pre>${esc(modelContract.prompt_template)}</pre>
      </details>
      <details class="prompt-preview">
        <summary>查看第 0 轮实际完整输入（含角色卡 JSON）</summary>
        <pre>${esc(modelContract.rendered_initial_prompt)}</pre>
      </details>
    </section>

    <section class="panel content-panel">
      <div class="section-kicker">INITIALIZATION</div>
      <h3>S0 / D0 候选状态</h3>
      <div class="state-columns">
        <div><h4>人物内部状态 · 0–10</h4>${stateBars(scenario.initial_state)}</div>
        <div><h4>互动动力 · 0–10</h4>${stateBars(scenario.initial_dynamics)}</div>
      </div>
      <div class="rationale"><b>初始化说明</b><p>${esc(Object.values(scenario.initialization_notes?.rationale || {}).join(' '))}</p></div>
    </section>

    <section class="panel content-panel">
      <div class="section-kicker">TALKING HEAD</div>
      <h3>视频触发阈值与样片</h3>
      <div class="trigger-grid">${(scenario.video_triggers || []).map((trigger) => {
        const asset = assets.find((item) => item.trigger_label === trigger.trigger_id && item.status === 'generated');
        const conditions = Object.entries(trigger.conditions || {}).map(([key, value]) =>
          `<span>${esc(key)} ${esc(value.operator)} <b>${esc(value.threshold)}</b></span>`
        ).join('');
        const changes = Object.entries(trigger.change_conditions || {}).map(([key, value]) =>
          `<span>Δ ${esc(key)} ${esc(value.operator)} <b>${esc(value.threshold)}</b></span>`
        ).join('');
        return `<article class="trigger-card"><div class="trigger-title"><strong>${esc(trigger.trigger_id)}</strong><span>P${esc(trigger.priority)} · ${esc(trigger.trigger_mode)}</span></div>
          <div class="condition-list">${conditions}${changes}</div>
          <p>${esc(trigger.observable_expression?.facial_expression)} · ${esc(trigger.observable_expression?.prosody)}</p>
          ${asset ? `<video controls preload="metadata" src="${esc(asset.url)}"></video>
            <small>${esc(asset.utterance)} · ${esc(asset.duration_seconds)}s</small>
            <small class="media-tech">${esc(asset.voice)} · ${esc(asset.synthesis?.profile || '未记录韵律')} · 语速 ${esc(asset.synthesis?.rate_pct ?? '—')}% · 音高 ${esc(asset.synthesis?.pitch_hz ?? '—')}Hz · ${esc((asset.synthesis?.sample_rate_hz || 0) / 1000)}kHz</small>` : '<div class="media-pending">视频未生成</div>'}
        </article>`;
      }).join('')}</div>
    </section>`;
  renderScenarioAnnotation();
}

function publicEventCards(events) {
  if (!events?.length) return '';
  return `<div class="public-events">${events.map((event) => `<div class="public-event"><span>${esc(event.evidence_id || event.event_id || 'EVENT')} · +${esc(event.elapsed_time ?? '—')} ${esc(event.time_unit || '')}</span><p>${esc(event.text)}</p></div>`).join('')}</div>`;
}

function dialogueHistory(history, compact = false) {
  if (!history?.length) return '<div class="empty">无历史：这是初始检查点</div>';
  return `<div class="dialogue-history ${compact ? 'compact' : ''}">${history.map((turn) => `
    <article class="dialogue-turn">
      <div class="timeline-meta">${esc(turn.segment_id || 'single_interaction')} · 片段内 ${esc(turn.segment_turn_id ?? '—')} · ${esc(turn.elapsed_time_before ?? 0)}→${esc(turn.elapsed_time_after ?? 0)}</div>
      <div class="speaker action"><span>${esc(turn.turn_id)}</span><p>${esc(turn.policy_action?.text)}</p></div>
      <div class="speaker response"><span>环境角色</span><p>${esc(turn.environment_response)}</p></div>
      ${publicEventCards(turn.public_events_after)}
    </article>`).join('')}</div>`;
}

function deltaChips(delta) {
  const values = flat(delta).filter(([, value]) => Number(value) !== 0);
  return values.length
    ? values.map(([key, value]) => `<span class="delta ${value > 0 ? 'up' : 'down'}">${esc(key)} ${value > 0 ? '+' : ''}${esc(value)}</span>`).join('')
    : '<span class="muted">本轮无数值变化</span>';
}

function scoreGrid(screening) {
  const scores = screening?.scores || {};
  return `<div class="score-grid">${Object.entries(scores).map(([key, value]) =>
    `<div><span>${esc(label(key))}</span><strong>${esc(value)}</strong><small>/ 5</small></div>`
  ).join('')}</div>`;
}

function screeningEvidence(screening) {
  if (!screening) return '<div class="empty">该轨迹没有协议筛选记录</div>';
  const evidence = screening.turn_evidence || {};
  const reasons = screening.human_review_reasons || [];
  return `<section class="panel content-panel screening-panel">
    <div class="screening-title">
      <div><div class="section-kicker">SCREENING PROTOCOL V1</div><h3>自动筛选证据</h3></div>
      <div class="screening-badges">
        <span class="decision ${esc(screening.automatic_decision?.toLowerCase())}">${esc(screening.automatic_decision)}</span>
        ${screening.provisional_selected ? '<span class="decision winner">建议赢家 · 待人工确认</span>' : ''}
      </div>
    </div>
    ${scoreGrid(screening)}
    <div class="screening-facts">
      <div><span>均分</span><strong>${esc(screening.mean_quality_score ?? '缺失')}</strong></div>
      <div><span>来源阶段</span><strong>${esc(screening.source_stage)}</strong></div>
      <div><span>演化结果</span><strong>${esc(screening.observed_outcome)}</strong></div>
      <div><span>Judge 证据</span><strong>${evidence.judge_turn_evidence_complete ? 'turn-ID 完整' : '缺 turn-ID'}</strong></div>
    </div>
    <div class="evidence-copy"><b>Judge 理由</b><p>${esc(screening.judge_rationale || '没有可用 Judge 理由')}</p></div>
    <div class="evidence-copy"><b>历史证据</b><p>关键事件：${esc((evidence.history_probe_critical_events || []).join(', ') || '缺失')} · checkpoint：${esc(evidence.history_probe_checkpoint || '缺失')}</p></div>
    <div class="audit-callout"><b>为什么需要人工看</b>${reasons.length ? `<ul>${reasons.map((item) => `<li>${esc(item)}</li>`).join('')}</ul>` : '<p>不在协议人工队列。</p>'}</div>
    ${(screening.hard_failures || []).length ? `<div class="hard-list"><b>Hard reject</b>${screening.hard_failures.map((item) => `<span>${esc(label(item))}</span>`).join('')}</div>` : ''}
  </section>`;
}

function beforeAfterRows(before, after, delta) {
  const left = Object.fromEntries(flat(before || {}));
  const right = Object.fromEntries(flat(after || {}));
  const changes = Object.fromEntries(flat(delta || {}));
  const keys = [...new Set([...Object.keys(left), ...Object.keys(right)])];
  return `<div class="state-comparison">${keys.map((key) => {
    const change = Number(changes[key] || 0);
    return `<div><span>${esc(key)}</span><b>${esc(left[key] ?? '—')} → ${esc(right[key] ?? '—')}</b><i class="${change > 0 ? 'up' : change < 0 ? 'down' : ''}">${change > 0 ? '+' : ''}${esc(change)}</i></div>`;
  }).join('')}</div>`;
}

function turnInputSummary(turn) {
  const observation = turn.observation || {};
  const longitudinal = observation.longitudinal_context || {};
  const segment = longitudinal.segment || {};
  const latest = observation.current_response || '这是本片段的首次行动';
  const questions = segment.live_questions || [];
  const obligation = observation.conversation_progress?.latest_obligation || null;
  return `<div class="turn-input">
    <div><span>本轮开始时对方上一句</span><p>${esc(latest)}</p></div>
    <div><span>当前片段目标</span><p>${esc(segment.interaction_goal || turn.segment_id || '—')}</p></div>
    <div><span>仍待处理的问题</span>${questions.length ? `<ul>${questions.map((item) => `<li>${esc(item)}</li>`).join('')}</ul>` : '<p>没有记录中的待处理问题</p>'}</div>
    <div><span>当前欠谁一个回应</span><p>${esc(obligation ? JSON.stringify(obligation) : '无')}</p></div>
  </div>`;
}

function appraisalPanel(turn) {
  const appraisal = turn.appraisal || {};
  const diagnostics = appraisal.dialogue_diagnostics || {};
  return `<details class="turn-detail" open><summary>① Structured Appraisal · 独立 LLM 调用</summary>
    <div class="evidence-grid">
      <div><span>意图</span><p>${esc(appraisal.speaker_intent || '—')}</p></div>
      <div><span>social act</span><p>${esc(appraisal.social_act || '—')}</p></div>
      <div><span>新颖度</span><p>${esc(diagnostics.substantive_novelty?.label || '—')} · ${esc(diagnostics.substantive_novelty?.evidence_span || '')}</p></div>
      <div><span>继续/收尾判断</span><p>${esc(diagnostics.continuation?.status || '—')} · ${esc(diagnostics.continuation?.evidence_span || '')}</p></div>
    </div>
    <div class="two-column compact-json"><div><h5>状态影响与证据</h5><pre>${esc(JSON.stringify(appraisal.state_impacts || [], null, 2))}</pre></div><div><h5>动力影响与 ledger 抽取</h5><pre>${esc(JSON.stringify({dynamics_impacts: appraisal.dynamics_impacts || [], ledger_events: appraisal.ledger_events || [], evidence_turn_ids: turn.evidence_turn_ids || []}, null, 2))}</pre></div></div>
  </details>`;
}

function deterministicUpdatePanel(turn) {
  const appraisalStateAfter = turn.state_after || {};
  const appraisalDynamicsAfter = turn.dynamics_after || {};
  const publicStateAfter = turn.state_after_public_events || appraisalStateAfter;
  const publicDynamicsAfter = turn.dynamics_after_public_events || appraisalDynamicsAfter;
  const publicEventChanged = JSON.stringify(appraisalStateAfter) !== JSON.stringify(publicStateAfter)
    || JSON.stringify(appraisalDynamicsAfter) !== JSON.stringify(publicDynamicsAfter);
  return `<details class="turn-detail" open><summary>② 确定性校准与数值更新 · 无 LLM</summary>
    <div class="turn-diagnostics">
      <div><h5>Appraisal 状态 before → after</h5>${beforeAfterRows(turn.state_before, appraisalStateAfter, turn.numeric_state_delta)}</div>
      <div><h5>Appraisal 动力 before → after</h5>${beforeAfterRows(turn.dynamics_before, appraisalDynamicsAfter, turn.numeric_dynamics_delta)}</div>
    </div>
    ${publicEventChanged ? `<details open><summary>片段公开事件的后续确定性更新</summary><pre>${esc(JSON.stringify({state_before_public_events: appraisalStateAfter, state_after_public_events: publicStateAfter, dynamics_before_public_events: appraisalDynamicsAfter, dynamics_after_public_events: publicDynamicsAfter}, null, 2))}</pre></details>` : ''}
    <details><summary>语义 delta 与 calibration 记录</summary><pre>${esc(JSON.stringify({state_delta: turn.state_delta || {}, dynamics_delta: turn.dynamics_delta || {}, calibration: turn.calibration || {}}, null, 2))}</pre></details>
  </details>`;
}

function responseAndLedgerPanel(turn) {
  const ledger = turn.interaction_ledger_after_public_events || turn.interaction_ledger_after || {};
  return `<details class="turn-detail"><summary>③ Response 与 ledger · 第二次独立 LLM 调用后结构记录</summary>
    <pre>${esc(JSON.stringify({response_events: turn.environment_response_ledger_events || [], response_normalizations: turn.environment_response_ledger_event_normalizations || [], latest_obligation: ledger.latest_obligation || null, active_proposals: ledger.active_proposals || [], commitments: ledger.commitments || [], performances: ledger.performances || [], requests: ledger.requests || []}, null, 2))}</pre>
  </details>`;
}

function renderRolloutView() {
  const rollouts = state.detail.rollouts || [];
  const trajectory = rollouts.find((item) => item.trajectory_id === state.trajectoryId) || rollouts[0];
  if (!trajectory) {
    $('#viewToolbar').innerHTML = '';
    $('#viewContent').innerHTML = '<div class="empty">这个场景目前没有 rollout。场景审核仍可完成，但没有逐轮内容可看。</div>';
    $('#annotationPanel').innerHTML = '';
    return;
  }
  state.trajectoryId = trajectory.trajectory_id;
  const index = rollouts.indexOf(trajectory);
  const provenance = trajectory.policy_provenance || {};
  const screening = trajectory.screening || {};
  const diagnostic = trajectory.diagnostic_review || {};
  const endingLabel = diagnostic.classification || trajectory.ending?.reason || 'no_recorded_ending';
  const requests = trajectory.actual_request_counts || {};
  const currentScenarioVersion = trajectory.scenario_version_matches_current === true;
  $('#viewToolbar').innerHTML = `
    <div class="toolbar-group">
      <button class="icon-button" data-nav-rollout="-1" ${index === 0 ? 'disabled' : ''}>← 上一条</button>
      <select id="trajectorySelect">${rollouts.map((item, i) => `<option value="${esc(item.trajectory_id)}" ${item.trajectory_id === trajectory.trajectory_id ? 'selected' : ''}>${i + 1}/${rollouts.length} · ${item.scenario_version_matches_current === true ? '当前场景版' : '历史诊断版'} · ${esc(item.screening?.candidate_classification || item.screening?.automatic_decision || 'PENDING')} · ${item.turns?.length || 0}轮 · ${esc(item.policy_id || item.policy_provenance?.model)}</option>`).join('')}</select>
      <button class="icon-button" data-nav-rollout="1" ${index === rollouts.length - 1 ? 'disabled' : ''}>下一条 →</button>
    </div>
    <div class="toolbar-note mono">全部 accepted、short、budget-truncated、generation-error 与 rejected 轨迹均可见 · ${esc(trajectory.trajectory_id)}</div>`;
  const turnLinks = (trajectory.turns || []).map((turn) => `<a href="#turn-${esc(turn.turn_id)}">${esc(turn.turn_id)}</a>`).join('');
  $('#viewContent').innerHTML = `
    ${currentScenarioVersion ? '' : '<section class="audit-callout"><b>历史诊断轨迹</b><p>这条 rollout 生成于本轮 20 场景强化之前，可用于逐轮诊断，但不能作为当前场景版本的 Gate 3 候选。</p></section>'}
    <section class="rollout-summary panel">
      <div><span>模型</span><strong>${esc(provenance.model || trajectory.policy_id)}</strong></div>
      <div><span>轮数</span><strong>${trajectory.turns?.length || 0}</strong></div>
      <div><span>候选类型</span><strong>${esc(screening.candidate_classification || screening.automatic_decision || 'PENDING')}</strong></div>
      <div><span>结束类型</span><strong>${esc(endingLabel)}</strong></div>
      <div><span>生成版本</span><strong>${esc(trajectory.quality_version || '历史未记录')}</strong></div>
      <div><span>数据来源</span><strong>${esc(screening.source_root || 'diagnostic')}</strong></div>
      <div><span>物理请求</span><strong>${esc(requests.total ?? '未记录')}</strong></div>
      <div><span>policy/appraisal/response</span><strong>${esc(requests.policy ?? '—')} / ${esc(requests.appraisal ?? '—')} / ${esc(requests.response ?? '—')}</strong></div>
    </section>
    <section class="panel turn-index"><b>跳到具体轮次</b><div>${turnLinks || '无完整轮次'}</div><p>每轮固定按 appraisal → 确定性更新 → response 展示；重试已计入物理请求数。</p></section>
    ${screeningEvidence(screening)}
    <section class="trajectory">${(trajectory.turns || []).map((turn) => `
      <article class="turn-card" id="turn-${esc(turn.turn_id)}">
        <header><b>${esc(turn.turn_id)} · ${esc(turn.segment_id || 'single_interaction')} / 片段内第 ${esc(turn.segment_turn_id ?? '—')} 轮</b><span>时间 ${esc(turn.elapsed_time_before ?? 0)} → ${esc(turn.elapsed_time_after ?? 0)} ${(turn.trigger_events || []).length ? '· VIDEO TRIGGER' : ''}</span></header>
        ${turnInputSummary(turn)}
        <div class="chat-pair">
          <div class="chat action"><span>被评估 Agent 行动</span><p>${esc(turn.policy_action?.text || '缺失')}</p></div>
          <div class="chat response"><span>Environment 角色回应</span><p>${esc(turn.environment_response || '缺失')}</p></div>
        </div>
        ${appraisalPanel(turn)}
        ${deterministicUpdatePanel(turn)}
        ${responseAndLedgerPanel(turn)}
        ${publicEventCards(turn.segment_transition_after?.public_events)}
        ${turn.segment_transition_after ? `<div class="segment-boundary"><b>本轮后片段推进</b><p>${esc(turn.segment_transition_after.from_segment_id)} → ${esc(turn.segment_transition_after.to_segment_id || '轨迹结束')} · ${esc(turn.segment_transition_after.boundary_reason)}</p></div>` : ''}
        <details class="turn-detail"><summary>可观察表情、语音与触发事件</summary><pre>${esc(JSON.stringify({observable_expression: turn.observable_expression || {}, trigger_events: turn.trigger_events || [], media: turn.media || {}}, null, 2))}</pre></details>
      </article>`).join('')}</section>
    <section class="panel ending-card"><b>轨迹结束记录</b><pre>${esc(JSON.stringify({ending: trajectory.ending || null, diagnostic: trajectory.diagnostic_review || null, actual_request_counts: requests}, null, 2))}</pre></section>`;
  renderRolloutAnnotation(trajectory);
}

function taskName(type) {
  return ({
    T1_state_tracking: 'T1 · 当前状态跟踪',
    T2_history_sensitive_merge: 'T2 · 历史敏感合流',
    T3_counterfactual_choice_effect: 'T3 · 选择影响'
  })[type] || type;
}

function filteredTasks() {
  const tasks = state.detail.instances || [];
  return state.taskType === 'all' ? tasks : tasks.filter((item) => item.task_type === state.taskType);
}

function observationCard(observation, title = '当前可观察信息') {
  if (!observation) return '<div class="empty">无观察数据</div>';
  const longitudinal = observation.longitudinal_context || {};
  const segment = longitudinal.segment || {};
  const time = longitudinal.time || {};
  return `<div class="observation-card"><span>${esc(title)}</span>
    <div class="timeline-meta">${esc(segment.segment_id || 'single_interaction')} · 片段内 ${esc(segment.segment_turn_id ?? 0)} · 已经过 ${esc(time.elapsed ?? 0)} ${esc(time.unit || '')}<br>${esc(segment.reason || '')}</div>
    <p>${esc(observation.current_response || '尚无当前回应')}</p>
    <small>表情：${esc(observation.observable_expression?.facial_expression || '—')}<br>
    视线：${esc(observation.observable_expression?.gaze || '—')}<br>
    韵律：${esc(observation.observable_expression?.prosody || '—')}</small>
    ${publicEventCards((longitudinal.public_timeline || []).slice(-4))}
  </div>`;
}

function machineProposalPanel(task) {
  return `<details class="panel document-panel machine-proposal"><summary>独立作答后再展开 · 机器建议答案与分支诊断（不是 GT）</summary><pre>${esc(JSON.stringify({proposal: task.machine_proposal || {status: 'not_generated'}, counterfactual_diagnostics: task.counterfactual_diagnostics || []}, null, 2))}</pre></details>`;
}

function renderTaskBody(task) {
  const input = task.input || {};
  const targets = task.target_spec?.target_state_ids || [];
  const selection = state.detail.task_source_selection || {};
  const taskKey = task.task_type.startsWith("T1_") ? "t1" : task.task_type.startsWith("T2_") ? "t2" : "t3";
  const sourceIds = task.metadata?.source_trajectory_ids || [task.metadata?.source_trajectory_id].filter(Boolean);
  const sourceScores = selection.scores?.[taskKey] || {};
  const sourceAudit = "<div class=\"task-source-note\"><b>任务专项选源</b><span>先过质量门；模型不计分、无配额</span><small>" + sourceIds.map((id) => esc(id) + " · " + esc(sourceScores[id] ?? "pair-level")).join("<br>") + "</small></div>";
  const heading = `<div class="task-heading"><div><div class="section-kicker">${esc(task.task_type)}</div><h3>${esc(task.instance_id)}</h3></div>
    <div class="target-chips">${targets.map((item) => `<span>${esc(item)}</span>`).join('')}</div></div>` + sourceAudit;

  if (task.task_type === 'T1_state_tracking') {
    return `<section class="panel content-panel">${heading}<p class="instruction">阅读截至检查点的公开对话，判断目标环境角色当前各状态的强度，并写出对话证据。</p>
      ${dialogueHistory(input.history)}
      ${observationCard(input.current_checkpoint)}
    </section>${machineProposalPanel(task)}`;
  }

  if (task.task_type === 'T2_history_sensitive_merge') {
    const shared = input.shared_observation || input.shared_current_observation || input.current_observation;
    return `<section class="panel content-panel">${heading}<p class="instruction">比较两段自然历史；在相同 O* 下判断目标角色状态是 A 更高、相近、B 更高，还是无法确定。</p>
      <div class="history-compare">
        <div><h4>历史 A</h4>${dialogueHistory(input.history_a, true)}</div>
        <div><h4>历史 B</h4>${dialogueHistory(input.history_b, true)}</div>
      </div>
      ${observationCard(shared, '共享当前观察 O*')}
    </section>${machineProposalPanel(task)}`;
  }

  return `<section class="panel content-panel">${heading}<p class="instruction">从同一真实检查点比较候选行动对目标环境角色的即时与 ${esc(task.target_spec?.delayed_horizon)} 轮延迟影响；同时核对实际经过时间和跨越事件，外生事件计划必须在候选间保持一致。</p>
    ${dialogueHistory(input.history)}
    ${observationCard(input.current_observation)}
    <div class="candidate-list">${(input.candidate_actions || []).map((action, index) =>
      `<article><span>OPTION ${index + 1}</span><p>${esc(action.text)}</p></article>`
    ).join('')}</div>
  </section>${machineProposalPanel(task)}`;
}

function renderTaskView() {
  const tasks = filteredTasks();
  let task = tasks.find((item) => item.instance_id === state.taskId) || tasks[0];
  state.taskId = task?.instance_id || null;
  const index = task ? tasks.indexOf(task) : -1;
  const counts = Object.fromEntries(['T1_state_tracking', 'T2_history_sensitive_merge', 'T3_counterfactual_choice_effect'].map(
    (type) => [type, (state.detail.instances || []).filter((item) => item.task_type === type).length]
  ));
  $('#viewToolbar').innerHTML = `
    <div class="task-filters">
      <button class="${state.taskType === 'all' ? 'active' : ''}" data-task-filter="all">全部 ${state.detail.instances?.length || 0}</button>
      ${Object.entries(counts).map(([type, count]) => `<button class="${state.taskType === type ? 'active' : ''}" data-task-filter="${type}">${esc(taskName(type).split(' · ')[0])} ${count}</button>`).join('')}
    </div>
    <div class="toolbar-group">
      <button class="icon-button" data-nav-task="-1" ${index <= 0 ? 'disabled' : ''}>←</button>
      <select id="taskSelect">${tasks.map((item, i) => `<option value="${esc(item.instance_id)}" ${item.instance_id === state.taskId ? 'selected' : ''}>${i + 1}. ${esc(taskName(item.task_type))}</option>`).join('')}</select>
      <button class="icon-button" data-nav-task="1" ${index < 0 || index === tasks.length - 1 ? 'disabled' : ''}>→</button>
    </div>`;
  if (!task) {
    $('#viewContent').innerHTML = '<div class="empty">该筛选下没有 task</div>';
    $('#annotationPanel').innerHTML = '';
    return;
  }
  $('#viewContent').innerHTML = renderTaskBody(task);
  renderTaskAnnotation(task);
}

function ratingRows(kind, id, dimensions, record) {
  return dimensions.map((key) => `<label class="form-row"><span>${esc(label(key))}</span>
    <select data-kind="${kind}" data-id="${esc(id)}" data-path="ratings/${esc(key)}">
      <option value="">未评分</option>
      ${[1,2,3,4,5].map((value) => `<option value="${value}" ${Number(record.ratings?.[key]) === value ? 'selected' : ''}>${value} / 5</option>`).join('')}
    </select></label>`).join('');
}

function triStateRows(kind, id, dimensions, record, field = 'checks') {
  return dimensions.map((key) => `<label class="form-row"><span>${esc(label(key))}</span>
    <select data-kind="${kind}" data-id="${esc(id)}" data-path="${field}/${esc(key)}">
      ${[['','待判断'],['pass','通过'],['revise','需修改'],['fail','不通过']].map(([value, text]) =>
        `<option value="${value}" ${record[field]?.[key] === value ? 'selected' : ''}>${text}</option>`
      ).join('')}
    </select></label>`).join('');
}

function annotationHeader(title, kind, id, record) {
  return `<div class="annotation-head"><div><div class="section-kicker">LOCAL REVIEW DRAFT</div><h3>${esc(title)}</h3></div><span class="draft-badge">浏览器草稿</span></div>
    <div class="status-picker">
      ${[['pending','待处理'],['approved','通过'],['revise','需修改'],['rejected','淘汰']].map(([value, text]) =>
        `<button class="${record.status === value ? 'active' : ''} ${value}" data-status="${value}" data-kind="${kind}" data-id="${esc(id)}">${text}</button>`
      ).join('')}
    </div>`;
}

function notesField(kind, id, record, title = '审核备注') {
  return `<label class="notes-field"><span>${title}</span><textarea data-kind="${kind}" data-id="${esc(id)}" data-path="notes" placeholder="记录问题、证据或修改建议…">${esc(record.notes || '')}</textarea></label>
    <div class="saved-note">${record.updated_at ? `最后保存 ${esc(new Date(record.updated_at).toLocaleString())}` : '尚未保存'}</div>`;
}


function inlineReviewForm(kind, id, title, record, dimensions = []) {
  return `<div class="form-section inline-audit"><h4>${esc(title)}</h4>
    <label class="form-row"><span>审核结论</span><select data-kind="${esc(kind)}" data-id="${esc(id)}" data-path="status">
      ${[['pending','待处理'],['approved','通过'],['revise','需修改'],['rejected','不通过']].map(([value, labelText]) => `<option value="${value}" ${record.status === value ? 'selected' : ''}>${labelText}</option>`).join('')}
    </select></label>
    ${dimensions.length ? triStateRows(kind, id, dimensions, record) : ''}
    ${notesField(kind, id, record, '结论、证据与修改建议')}
  </div>`;
}

function gate2MachineState(record) {
  if (record.human_attestation) return {label: 'HUMAN SIGNED', css: 'pass'};
  const hasScreen = Object.prototype.hasOwnProperty.call(record, 'machine_screen_passed');
  const hasPassed = Object.prototype.hasOwnProperty.call(record, 'passed');
  if ((hasScreen && record.machine_screen_passed) || (hasPassed && record.passed)) {
    return {label: 'AUTO READY · 待人审', css: 'review'};
  }
  if ((hasScreen && !record.machine_screen_passed) || (hasPassed && !record.passed)) {
    return {label: 'AUTO FAIL · 需处理', css: 'reject'};
  }
  return {label: 'PENDING HUMAN', css: 'review'};
}

function scenarioReviewCompletion(record) {
  const ratingKeys = state.contract.scenario_rating_scale.dimensions;
  const checkKeys = state.contract.scenario_checks;
  const attestationKeys = ['variables_relevant','values_justified','no_policy_effect_baked_in','initial_triggers_inactive','multiple_future_paths_possible','shared_across_models_and_seeds'];
  const ratingsDone = ratingKeys.filter((key) => Number(record.ratings?.[key]) >= 1).length;
  const checksDone = checkKeys.filter((key) => ['pass','revise','fail'].includes(record.checks?.[key])).length;
  const attestationsDone = attestationKeys.filter((key) => record.attestations?.[key]).length;
  return {ratingsDone, checksDone, attestationsDone, ratingTotal: ratingKeys.length, checkTotal: checkKeys.length, attestationTotal: attestationKeys.length};
}

function issueField(id, record, key, title) {
  return `<label class="notes-field compact-note"><span>${esc(title)}</span><textarea data-kind="scenario" data-id="${esc(id)}" data-path="issues/${esc(key)}" placeholder="没有问题可留空；若需修改，请写明具体位置和建议…">${esc(record.issues?.[key] || '')}</textarea></label>`;
}

function renderScenarioAnnotation() {
  const id = state.scenarioId;
  const record = currentRecord('scenario', id);
  const completion = scenarioReviewCompletion(record);
  const attestationKeys = ['variables_relevant','values_justified','no_policy_effect_baked_in','initial_triggers_inactive','multiple_future_paths_possible','shared_across_models_and_seeds'];
  const media = state.detail.media_assets || [];
  const mediaChecks = media.map((asset) => {
    const mediaRecord = currentRecord('media', asset.asset_id);
    return `<details class="media-review"><summary>${esc(asset.trigger_label)} · ${esc(asset.status)}</summary>
      ${annotationHeader('视频审核', 'media', asset.asset_id, mediaRecord)}
      <video controls preload="metadata" src="${esc(asset.url)}"></video>
      <small class="media-tech">${esc(asset.utterance)} · ${esc(asset.voice)} · ${esc(asset.synthesis?.profile || '未记录韵律')} · ${esc(asset.duration_seconds)}s · 尾停顿 ${esc(asset.synthesis?.tail_silence_ms ?? '—')}ms</small>
      ${['expression_state_consistency','temporal_continuity','speech_naturalness','multimodal_utility'].map((key) => `<label class="check-line"><input type="checkbox" data-kind="media" data-id="${esc(asset.asset_id)}" data-path="checks/${key}" ${mediaRecord.checks?.[key] ? 'checked' : ''}> ${esc(label(key))}</label>`).join('')}
      ${notesField('media', asset.asset_id, mediaRecord, '视频问题与证据')}
    </details>`;
  }).join('');
  $('#annotationPanel').innerHTML = `${annotationHeader('Scenario 审核', 'scenario', id, record)}
    <div class="audit-callout"><b>本条完成度</b><p>质量评分 ${completion.ratingsDone}/${completion.ratingTotal} · Gate 1 ${completion.checksDone}/${completion.checkTotal} · 冻结确认 ${completion.attestationsDone}/${completion.attestationTotal}</p><small class="mono">SHA-256 ${esc(record.scenario_sha256 || state.detail.gate1_review_packet?.scenario_sha256 || 'missing')}</small></div>
    <div class="form-section"><h4>核心质量 · 1–5</h4>${ratingRows('scenario', id, state.contract.scenario_rating_scale.dimensions, record)}</div>
    <div class="form-section"><h4>Gate 1 全部检查</h4>${triStateRows('scenario', id, state.contract.scenario_checks, record)}</div>
    <div class="form-section"><h4>S0 / D0 正式冻结确认</h4>${attestationKeys.map((key) => `<label class="check-line"><input type="checkbox" data-kind="scenario" data-id="${esc(id)}" data-path="attestations/${esc(key)}" ${record.attestations?.[key] ? 'checked' : ''}> ${esc(label(key))}</label>`).join('')}</div>
    <div class="form-section"><h4>按组件记录需修改内容</h4>
      ${issueField(id, record, 'story', '人物、冲突与权力结构')}
      ${issueField(id, record, 'history', '历史、信息不对称与原创性')}
      ${issueField(id, record, 'longitudinal', '10–20 轮片段、时间与事件')}
      ${issueField(id, record, 's0_d0', 'S0 / D0 数值与理由')}
      ${issueField(id, record, 'tasks', 'T1–T4 可回答性与区分度')}
      ${issueField(id, record, 'triggers', '视频触发阈值与可达性')}
    </div>
    <label class="check-line final-attestation"><input type="checkbox" data-kind="scenario" data-id="${esc(id)}" data-path="human_attestation" ${record.human_attestation ? 'checked' : ''}> 我已查看本场景全部材料，以上结论由真人作出</label>
    ${notesField('scenario', id, record, '总体结论与下一轮修改优先级')}
    <div class="form-section"><h4>Talking Head 逐视频审核（可在场景审核后单独完成）</h4>${mediaChecks || '<div class="empty">没有视频资产</div>'}</div>`;
}

function renderRolloutAnnotation(trajectory) {
  const id = trajectory.trajectory_id;
  const record = currentRecord('rollout', id);
  const auto = trajectory.screening || {};
  const selectionAllowed = ['PASS', 'REVIEW'].includes(auto.automatic_decision);
  const selected = selectionAllowed && (
    record.selection?.selected ?? auto.provisional_selected
  );
  const selectionText = selected ? '✓ 当前场景保留此条' : selectionAllowed ? '将此条设为场景唯一赢家' : auto.automatic_decision === 'REJECT' ? 'REJECT 不可设为 winner' : '待 Judge / History，暂不可选择';
  $('#annotationPanel').innerHTML = `${annotationHeader('Rollout 协议审核', 'rollout', id, record)}
    <button class="button ${selected ? 'primary' : ''} wide" data-select-winner="${esc(id)}" ${selectionAllowed ? '' : 'disabled'}>${selectionText}</button>
    <p class="selection-warning">只有PASS/REVIEW候选可进入人工比较；选择另一条会取消此前选择，导出后仍需实名、时间和哈希绑定。</p>
    <div class="form-section"><h4>协议五问</h4>
      <label class="form-row"><span>1. 自动 decision 正确吗</span><select data-kind="rollout" data-id="${esc(id)}" data-path="audit/automatic_decision_correct">
        ${[['','待判断'],['yes','正确'],['no','错误'],['unsure','不确定']].map(([v,t]) => `<option value="${v}" ${record.audit?.automatic_decision_correct === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      <div class="dimension-checks"><span>2. 哪些 dimension 判断错了</span>${state.contract.rollout_quality_dimensions.map((key) => `<label class="check-line"><input type="checkbox" data-kind="rollout" data-id="${esc(id)}" data-path="audit/incorrect_dimensions/${esc(key)}" ${record.audit?.incorrect_dimensions?.[key] ? 'checked' : ''}>${esc(label(key))}</label>`).join('')}</div>
      <label class="notes-field compact"><span>3. 错误原因</span><textarea data-kind="rollout" data-id="${esc(id)}" data-path="audit/error_reason">${esc(record.audit?.error_reason || '')}</textarea></label>
      <label class="form-row"><span>4. 单例还是系统问题</span><select data-kind="rollout" data-id="${esc(id)}" data-path="audit/issue_scope">${[['','待判断'],['isolated','单例'],['systematic','系统性'],['none','无错误']].map(([v,t]) => `<option value="${v}" ${record.audit?.issue_scope === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      <label class="notes-field compact"><span>5. rule / prompt 应如何修改</span><textarea data-kind="rollout" data-id="${esc(id)}" data-path="audit/rule_or_prompt_revision">${esc(record.audit?.rule_or_prompt_revision || '')}</textarea></label>
    </div>
    <div class="form-section"><h4>人工六维复评分 · 1–5</h4>${ratingRows('rollout', id, state.contract.rollout_quality_dimensions, record)}</div>
    <div class="form-section"><h4>Hard reject 复核</h4>
      ${state.contract.rollout_hard_reject_reasons.map((key) => `<label class="check-line danger"><input type="checkbox" data-kind="rollout" data-id="${esc(id)}" data-path="hard_rejects/${esc(key)}" ${record.hard_rejects?.[key] ? 'checked' : ''}> ${esc(label(key))}</label>`).join('')}
    </div>
    <div class="form-section"><h4>观察到的演化结果</h4>
      <select class="wide-select" data-kind="rollout" data-id="${esc(id)}" data-path="outcome">
        ${['','successful_negotiation','gradual_deterioration','stalemate','failed_repair','successful_repair','goal_success_relationship_damage','relationship_preserved_partial_failure','strategy_change','withdrawal'].map((value) =>
          `<option value="${value}" ${record.outcome === value ? 'selected' : ''}>${value ? label(value) : '请选择'}</option>`
        ).join('')}
      </select>
    </div>
    ${notesField('rollout', id, record)}`;
}

function taskLabelFields(task, record) {
  const id = task.instance_id;
  const targets = task.target_spec?.target_state_ids || [];
  if (task.task_type === 'T1_state_tracking') {
    return `<div class="label-grid">${targets.map((key) => `<label><span>${esc(key)}</span><input type="number" min="0" max="10" step="1" data-kind="task" data-id="${esc(id)}" data-path="labels/states/${esc(key)}" value="${esc(record.labels?.states?.[key] ?? '')}" placeholder="0–10"></label>`).join('')}</div>`;
  }
  if (task.task_type === 'T2_history_sensitive_merge') {
    return targets.map((key) => `<label class="form-row"><span>${esc(key)}</span><select data-kind="task" data-id="${esc(id)}" data-path="labels/comparison/${esc(key)}">
      ${[['','未标注'],['A_higher','A 更高'],['similar','相近'],['B_higher','B 更高'],['cannot_determine','无法确定']].map(([value, text]) => `<option value="${value}" ${record.labels?.comparison?.[key] === value ? 'selected' : ''}>${text}</option>`).join('')}
    </select></label>`).join('');
  }
  const actions = task.input?.candidate_actions || [];
  return actions.map((action, actionIndex) => `<details class="option-label"><summary>Option ${actionIndex + 1} · ${esc(action.text.slice(0, 24))}…</summary>
    ${['immediate','delayed'].map((horizon) => `<h5>${horizon === 'immediate' ? '即时影响' : '延迟影响'}</h5>${targets.map((key) => `<label class="form-row"><span>${esc(key)}</span><select data-kind="task" data-id="${esc(id)}" data-path="labels/options/${actionIndex}/${horizon}/${esc(key)}">
      ${[['','未标注'],['decrease','下降'],['similar','不变/相近'],['increase','上升'],['cannot_determine','无法确定']].map(([value, text]) => `<option value="${value}" ${record.labels?.options?.[actionIndex]?.[horizon]?.[key] === value ? 'selected' : ''}>${text}</option>`).join('')}
    </select></label>`).join('')}`).join('')}
  </details>`).join('');
}

function renderTaskAnnotation(task) {
  const id = task.instance_id;
  const record = currentRecord('task', id);
  const checks = state.contract.task_review_ratings[task.task_type] || [];
  $('#annotationPanel').innerHTML = `${annotationHeader(taskName(task.task_type), 'task', id, record)}
    <div class="form-section"><h4>人工标签草稿</h4>${taskLabelFields(task, record)}
      <label class="notes-field compact"><span>证据句 / turn ID</span><textarea data-kind="task" data-id="${esc(id)}" data-path="labels/evidence" placeholder="必须引用公开对话证据">${esc(record.labels?.evidence || '')}</textarea></label>
    </div>
    <div class="form-section"><h4>Gate 4 专属检查</h4>${triStateRows('task', id, checks, record)}</div>
    ${notesField('task', id, record)}`;
}

function renderManualReviewView() {
  const review = state.data.manual_review || {};
  const workspace = state.data.review_workspace || {};
  const staffing = workspace.staffing_plan || review.staffing_plan || {};
  const modelStack = workspace.model_stack || review.model_stack || {};
  const longRun = review.long_rollout_generation || {};
  const r3Diagnostic = review.r3_current_diagnostic_review || {};
  const stabilization = workspace.environment_stabilization_regression || {};
  const stabilizationRecord = stabilization.record || {};
  const distribution = stabilization.state_distribution || {};
  const distributionChange = distribution.change || {};
  const staffCards = [
    ['Gate 1', staffing.gate1?.reviewers_required, '1 人全量检查 scenario 与 S0/D0'],
    ['Gate 2', staffing.gate2?.reviewers_required, '1 人复核 E1–E5；E3/E4/E5 已自动实验'],
    ['Gate 3', `${staffing.gate3?.primary_reviewers || 1}+${staffing.gate3?.secondary_audit_reviewers || 1}`, `1 人主审 + 第 2 人 ${Math.round((staffing.gate3?.secondary_audit_fraction || .2) * 100)}% audit`],
    ['Gate 4', staffing.gate4?.independent_reviewers, '两人看相同样本；分歧才找第 3 人'],
    ['Video', staffing.video?.reviewers_required, '1 人检查全部 talking-head 视频']
  ];
  const environment = modelStack.environment || {};
  const policies = modelStack.evaluated_agent_policies || [];
  const gate2Cards = Object.entries(workspace.gate2 || {}).map(([experimentId, payload]) => {
    const record = payload.record || {};
    const items = payload.review_items || payload.records || [];
    const activity = record.backbone_activity_by_model_family || {};
    const activityLabel = Object.entries(activity).map(([family, value]) =>
      `${family} active ${value.active_record_count || 0}/${record.matched_checkpoint_count || 0}`
    ).join(' · ');
    const metric = experimentId === 'E1' ? `${record.transition_count || 0} transitions`
      : experimentId === 'E2' ? `${record.trajectory_count || 0} trajectories`
      : experimentId === 'E3' ? `${record.matched_checkpoint_count || 0} checkpoints`
      : experimentId === 'E4' ? `${record.pair_count || 0} pairs · overall ${record.overall_dimension_direction_agreement ?? '—'} · state ${record.state_direction_agreement ?? '—'} · dynamics ${record.dynamics_direction_agreement ?? '—'} · reversal ${record.true_sign_reversal_rate ?? '—'}`
      : experimentId === 'E5' ? `${record.checkpoint_count || 0} checkpoints`
      : `${record.matched_checkpoint_count || 0} checkpoints · exact ${record.mean_exact_direction_agreement ?? '—'} · change/no-change ${record.mean_change_no_change_agreement ?? '—'} · reversal ${record.mean_true_sign_reversal_rate ?? '—'} · ${activityLabel || 'activity unavailable'}`;
    const machineState = gate2MachineState(record);
    const experimentDraft = currentRecord(`gate2_${experimentId}`, experimentId);
    const itemHtml = items.map((item, index) => {
      const itemId = `${experimentId}:${item.review_id || item.record_id || item.scenario_id || item.source_trajectory_id || index + 1}:${item.turn_id || item.checkpoint_turn_id || index + 1}`;
      const itemDraft = currentRecord('gate2_item', itemId);
      return `<details><summary>${esc(item.scenario_id || item.review_id || item.source_trajectory_id || `item ${index + 1}`)} · ${esc(item.turn_id || item.checkpoint_turn_id || '')}</summary>
        ${inlineReviewForm('gate2_item', itemId, '该实验项抽查', itemDraft)}
        <details class="document-panel"><summary>展开机器实验记录</summary><pre>${esc(JSON.stringify(item, null, 2))}</pre></details>
      </details>`;
    }).join('');
    return `<article class="panel review-block"><div class="screening-title"><div><div class="section-kicker">GATE 2 · ${esc(experimentId)}</div><h3>${esc(metric)}</h3></div><span class="decision ${machineState.css}">${esc(machineState.label)}</span></div>
      <p class="annotation-copy">${experimentId === 'E1' ? '人根据 persona/history/action 独立判断状态方向，再展开机器方向比较。' : experimentId === 'E2' ? '人通读整段轨迹，评 persona、history、state continuity 与 response-state consistency。' : experimentId === 'E3' ? '固定 persona/state/action，只移除关键历史事件；应出现合理变化。' : experimentId === 'E4' ? '语义相同、措辞不同；状态方向应基本一致。' : experimentId === 'E5' ? '同一 checkpoint 注入多个合理动作；检查相对变化是否可信。' : '不同 environment backbone 的 matched replay；失败指标不能被人工签字掩盖。'}</p>
      ${inlineReviewForm(`gate2_${experimentId}`, experimentId, `${experimentId} 总体复核`, experimentDraft)}
      <div class="review-item-list">${itemHtml || '<div class="empty">尚无逐项实验记录</div>'}</div></article>`;
  }).join('');
  const gate4 = workspace.gate4 || {};
  const gate4Records = gate4.records || [];
  const gate3 = workspace.gate3 || {};
  $('#viewToolbar').innerHTML = '<div><span class="toolbar-title">完整人工工作面</span><span class="toolbar-note">人员分工、模型职责、实验样本和抽查题全部可见</span></div>';
  $('#viewContent').innerHTML = `<section class="panel content-panel"><div class="section-kicker">HUMAN STAFFING · 20 → 150 SCENARIOS</div><h3>统一人审配置</h3><div class="staff-grid">${staffCards.map(([name, count, note]) => `<article><span>${esc(name)}</span><strong>${esc(count ?? '—')}</strong><small>${esc(note)}</small></article>`).join('')}</div></section>
    <section class="panel content-panel model-stack"><div class="section-kicker">CURRENT MODEL STACK</div><h3>当前是谁在作出反应</h3><div class="model-role environment-role"><b>LLM call 1: appraisal · deterministic calibration/update · LLM call 2: visible response</b><code>${esc(environment.model || 'unknown')}</code><p>${esc(environment.note || '')}</p></div><div class="model-policy-grid">${policies.map((item) => `<div><b>${esc(item.model_family || 'model')}</b><code>${esc(item.model || 'unknown')}</code><span>${esc(item.runs || 1)} runs</span></div>`).join('')}</div><div class="audit-callout"><b>实验边界</b><p>${esc(modelStack.warning || '')}</p></div></section>
    <section class="panel content-panel"><div class="section-kicker">LIVE 20-TURN GENERATION</div><h3>${esc(longRun.completed_slot_count || 0)} / ${esc(longRun.expected_slot_count || 0)} 槽位</h3><p class="annotation-copy">状态：${esc(longRun.status || 'not_started')} · 每条 ${esc(longRun.required_turns || 20)} 轮 · 机器拒绝尝试 ${esc(longRun.machine_rejected_attempt_count || 0)} · 生成错误 ${esc(longRun.generation_error_count || 0)}</p></section>
    <section class="panel content-panel"><div class="screening-title"><div><div class="section-kicker">CURRENT R3 DIAGNOSTIC · ${esc(r3Diagnostic.quality_version || 'not_generated')}</div><h3>短样例 ${esc(r3Diagnostic.short_appraisal_probe?.passed_case_count ?? 0)} / ${esc(r3Diagnostic.short_appraisal_probe?.case_count ?? 0)} · 联合短测 ${esc(r3Diagnostic.two_stage_environment_probe?.status || 'not_run')}</h3></div><span class="decision reject">待人工诊断</span></div><p class="annotation-copy">${esc(r3Diagnostic.summary || '尚无当前诊断包')}</p><div class="audit-callout"><b>当前卡点</b><p>${esc(r3Diagnostic.two_stage_environment_probe?.established_failed_check || '—')}：${esc((r3Diagnostic.two_stage_environment_probe?.failure_reasons || []).join('；') || '—')}</p><p>${esc(r3Diagnostic.two_stage_environment_probe?.semantic_observation || '')}</p></div><div class="audit-callout"><b>多轮正式约束</b><p>offline 最多 20 轮、允许自然结束；片段长度可变；时间到达不等于履约；appraisal 与 response 是两次独立 LLM 调用，中间状态、动力和 ledger 确定性更新。</p></div><p class="annotation-copy">人工轨迹：${esc(r3Diagnostic.human_review_candidate?.scenario_id || '—')} · ${esc(r3Diagnostic.human_review_candidate?.turn_count || 0)} 轮 · ${esc(r3Diagnostic.human_review_candidate?.classification || '—')}。请在左侧选 IA003，再进入“Rollout 轨迹”查看逐轮证据并填写草稿。</p></section>
    <section class="panel content-panel"><div class="screening-title"><div><div class="section-kicker">ENVIRONMENT R3 + R4 REGRESSION</div><h3>${esc(stabilizationRecord.machine_precheck_passed_count || 0)} / ${esc(stabilizationRecord.trajectory_count || 0)} 条机器预检通过 · ${esc(stabilizationRecord.rejected_trajectory_count || 0)} 条 rejected 可展开</h3></div><span class="decision review">${esc(stabilizationRecord.review_status || 'not_generated')}</span></div><p class="annotation-copy">R4 状态：${esc(distribution.comparison_status || 'not_generated')} · 相比旧池 similar ratio ${esc(distributionChange.similar_ratio ?? '—')} · 每轮变化变量 ${esc(distributionChange.mean_changed_variables_per_turn ?? '—')} · oscillation ${esc(distributionChange.oscillation_rate ?? '—')} · saturation ${esc(distributionChange.saturation_ratio ?? '—')}。空样本不计算差值，这些指标也不替代真人自然度判断。</p><div class="review-item-list">${(stabilization.records || []).map((item) => { const itemDraft = currentRecord('stabilization_r3', item.trajectory_id); return `<details><summary>${esc(item.scenario_id)} · ${esc(item.trajectory_id)} · constraints ${esc(item.constraint_language_candidates?.length || 0)} · escalation flags ${esc(item.institutional_escalation_candidates?.length || 0)}</summary>${inlineReviewForm('stabilization_r3', item.trajectory_id, 'R3 完整轨迹自然度复核', itemDraft)}<pre>${esc(JSON.stringify(item, null, 2))}</pre></details>`; }).join('') || '<div class="empty">当前没有达到机器预检要求的完整轨迹</div>'}${(stabilization.rejected_records || []).map((item) => `<details><summary>REJECTED · ${esc(item.scenario_id)} · ${esc(item.trajectory_id)} · ${esc((item.failed_checks || []).join(', '))}</summary><p class="annotation-copy">仅作失败诊断，不进入正式人工标注。</p><pre>${esc(JSON.stringify(item, null, 2))}</pre></details>`).join('')}</div></section>
    <section class="manual-grid">${(review.categories || []).map((item) => `
    <article class="panel manual-card"><div class="screening-title"><h3>${esc(item.title)}</h3><span class="decision ${item.status === 'passed' ? 'pass' : item.status === 'rejected' ? 'reject' : 'review'}">${esc(item.status)}</span></div>
      <p>${esc(item.description)}</p><div class="manual-count"><strong>${esc(item.available)}</strong><span>/ ${esc(item.required)} 可用</span></div><small>查看位置：${esc(item.location)}</small></article>`).join('')}</section>
    <section class="panel content-panel"><div class="screening-title"><div><div class="section-kicker">GATE 3 · HUMAN REVIEW SPLIT</div><h3>主审 ${esc(gate3.primary_count || 0)} · 第二人 audit ${esc(gate3.secondary_audit_count || 0)}</h3></div><span class="decision review">${esc(Math.round((gate3.secondary_audit_fraction || .2) * 100))}% DETERMINISTIC</span></div><p class="annotation-copy">主审工作面在“Rollout 轨迹”；第二人只看下列固定 trajectory。被拒 archive 保留作 failure analysis，不计入两天内主审负担。</p><div class="review-item-list">${(gate3.secondary_audit_records || []).map((item) => `<details><summary>${esc(item.scenario_id)} · ${esc(item.trajectory_id)} · ${esc(item.automatic_decision)}</summary><pre>${esc(JSON.stringify(item, null, 2))}</pre></details>`).join('') || '<div class="empty">尚未生成 audit 清单</div>'}</div></section>
    <section class="review-stack">${gate2Cards}</section>
    <section class="panel content-panel"><div class="screening-title"><div><div class="section-kicker">GATE 4 · SAME-SAMPLE DOUBLE AUDIT</div><h3>${esc(gate4.sampling?.sample_count || 0)} / ${esc(gate4.sampling?.population_count || 0)} 个 task 抽查</h3></div><span class="decision review">A/B 独立 · 分歧才仲裁</span></div><p class="annotation-copy">按 task type 各抽 ${esc(Math.round((gate4.sampling?.fraction_per_task_type || .1) * 100))}%；当前 ${Object.entries(gate4.sampling?.sample_counts || {}).map(([key, value]) => `${key.replace(/^T(\d).*/, 'T$1')}=${value}`).join(' · ')}。先看 blind packet，再展开机器建议答案；机器建议不是正式 GT。</p>
      <div class="review-item-list gate4-list">${gate4Records.map((item) => {
        const dimensions = state.contract.task_review_ratings[item.task_type] || [];
        const reviewerA = currentRecord('gate4_a', item.instance_id);
        const reviewerB = currentRecord('gate4_b', item.instance_id);
        const judge = currentRecord('gate4_judge', item.instance_id);
        return `<details><summary>${esc(item.scenario_id)} · ${esc(item.task_type.replace(/^T(\d).*/, 'T$1'))} · ${esc(item.instance_id)}</summary>
          <div class="packet-columns"><div><h4>盲审题面</h4><pre>${esc(JSON.stringify(item.blind_packet, null, 2))}</pre></div><div><h4>机器建议（抽查用）</h4><pre>${esc(JSON.stringify(item.machine_proposal, null, 2))}</pre></div></div>
          <div class="packet-columns">${inlineReviewForm('gate4_a', item.instance_id, 'Reviewer A · 独立抽查', reviewerA, dimensions)}${inlineReviewForm('gate4_b', item.instance_id, 'Reviewer B · 独立抽查', reviewerB, dimensions)}</div>
          <details><summary>仅 A/B 分歧时填写第三人仲裁</summary>${inlineReviewForm('gate4_judge', item.instance_id, 'Reviewer C · 仲裁', judge, dimensions)}</details>
        </details>`;
      }).join('') || '<div class="empty">新 60-task pipeline 尚未生成；这里不会显示旧 180-task 样本。</div>'}</div></section>
    <details class="panel document-panel"><summary>SocialFlux Rollout Screening Protocol v1 全文</summary><pre>${esc(review.protocol_document || '')}</pre></details>`;
  $('#annotationPanel').innerHTML = `<div class="annotation-head"><div><div class="section-kicker">NO HIDDEN TODO</div><h3>人工审核边界</h3></div></div>
    <p class="annotation-copy">本页把所有人需要看的材料集中展示。具体 scenario、rollout 与视频仍可在对应页面逐项查看；自动结果不会替代实名、时间戳和 hash-bound 真人确认。</p>
    <div class="audit-callout"><b>两天内推荐顺序</b><ol><li>Gate 1：1 人冻结 20 个 scenario/S0/D0</li><li>Gate 2：1 人审 E1/E2 抽样与 E3/E4/E5 自动实验</li><li>Gate 3：主审全量，第二人只 audit 20% 与 borderline</li><li>Gate 4：两人独立审同一 6 题，分歧才找第三人</li><li>Video：1 人检查全部 60 个资产</li></ol></div><p class="muted">${esc(workspace.warning || '')}</p>`;
}

function renderMaterialsView() {
  $('#viewToolbar').innerHTML = '<div><span class="toolbar-title">生成材料</span><span class="toolbar-note">用于复核，不直接作为正式答案</span></div>';
  $('#viewContent').innerHTML = `
    <details class="panel document-panel" open><summary>Scenario 自然语言说明</summary><pre>${esc(state.detail.documentation || '无')}</pre></details>
    <details class="panel document-panel"><summary>完整 rollout 对话</summary><pre>${esc(state.detail.rollout_dialogues || '无')}</pre></details>
    <details class="panel document-panel"><summary>T1/T2/T3 人工抽查文档</summary><pre>${esc(state.detail.task_review || '无')}</pre></details>
    <details class="panel document-panel"><summary>Scenario JSON</summary><pre>${esc(JSON.stringify(state.detail.scenario, null, 2))}</pre></details>`;
  $('#annotationPanel').innerHTML = `<div class="annotation-head"><div><div class="section-kicker">REFERENCE ONLY</div><h3>材料说明</h3></div></div>
    <p class="annotation-copy">左侧材料包含 pipeline 自动生成的说明和私有诊断。正式 task 标注必须先依据公开题面独立判断，不能把 simulator 私有状态直接抄作 Ground Truth。</p>
    <button class="button primary wide" data-view-jump="task">前往 Task 标注</button>`;
}

function renderScale20PilotView() {
  const pilot = state.pilot || {};
  const candidates = [...(pilot.candidates || []), ...(pilot.v2_candidates || [])];
  const candidate = candidates.find((item) => item.trajectory_id === state.pilotTrajectoryId) || candidates[0];
  const v2 = pilot.v2_revision || {};
  if (!candidate) {
    $('#viewToolbar').innerHTML = '<div><span class="toolbar-title">Scale20 人工审核</span></div>';
    $('#viewContent').innerHTML = '<div class="empty">Pilot 报告尚未生成。</div>';
    $('#annotationPanel').innerHTML = '';
    return;
  }
  state.pilotTrajectoryId = candidate.trajectory_id;
  const trajectory = candidate.trajectory || {};
  const index = candidates.indexOf(candidate);
  const requests = candidate.actual_request_counts || {};
  const semanticReview = candidate.model_semantic_review || {};
  const semanticLabel = typeof semanticReview === 'object' ? semanticReview.label : semanticReview;
  const semanticNote = typeof semanticReview === 'object' ? semanticReview.note : '';
  const issueCards = (candidate.issues || []).map((item) => `<li><b>${esc((item.turn_ids || []).join(', ') || 'trajectory')}</b> · ${esc(item.issue)}</li>`).join('') || (semanticNote ? `<li><b>模型提示</b> · ${esc(semanticNote)}</li>` : '');
  const results = pilot.scenario_results || candidates.map((item) => ({scenario_id: item.scenario_id, turn_count: item.turn_count, generation_status: item.generation_status, model_semantic_review: item.model_semantic_review, human_review: item.human_review}));
  const machineLabel = candidate.machine_precheck?.passed === true ? 'pass' : candidate.machine_precheck?.passed === false ? 'not-pass' : candidate.generation_status;
  $('#viewToolbar').innerHTML = `<div class="toolbar-group">
    <button class="icon-button" data-nav-pilot="-1" ${index === 0 ? 'disabled' : ''}>←</button>
    <select id="pilotTrajectorySelect">${candidates.map((item, i) => `<option value="${esc(item.trajectory_id)}" ${item.trajectory_id === candidate.trajectory_id ? 'selected' : ''}>${i + 1}/${candidates.length} · ${esc(item.configuration_version || scale20_v1)} · ${esc(item.scenario_id)} · ${esc(item.turn_count)}轮 · ${esc(item.generation_status || item.classification)}</option>`).join('')}</select>
    <button class="icon-button" data-nav-pilot="1" ${index === candidates.length - 1 ? 'disabled' : ''}>→</button>
  </div><div class="toolbar-note mono">模型语义复核，不是人工验收 · ${esc(candidate.trajectory_id)}</div>`;
  const turnLinks = (trajectory.turns || []).map((turn) => `<a href="#pilot-turn-${esc(turn.turn_id)}">${esc(turn.turn_id)}</a>`).join('');
  $('#viewContent').innerHTML = `
    <section class="audit-callout"><b>v1：20 个场景均有旧版单次轨迹</b><p>共 ${esc(pilot.total_turns || 0)} 轮，继续原样保留作人工反馈证据；不会冒充 v2 验证。</p></section>
    <section class="audit-callout"><b>v2：${esc(v2.scenario_count || 0)} 个场景已强化 · ${esc(v2.evidence_node_scenario_count || 0)} 个含作者化证据节点</b><p>状态 ${esc(v2.status || not_loaded)} · 当前下拉列表末尾附有 IA001/IA002 的 v2 代表性 pilot。最终代码短测 ${esc(v2.final_code_validation?.passed || 0)}/${esc(v2.final_code_validation?.related_test_count || 0)}；其余 v2 rollout 尚未生成，不会显示成已验证。</p></section>
    <details class="panel document-panel"><summary>v2 20 个场景：背景、片段与公开事件</summary><pre>${esc(JSON.stringify(v2.scenarios || [], null, 2))}</pre></details>
    <details class="panel document-panel"><summary>v1 20 个旧轨迹逐项状态</summary><pre>${esc(JSON.stringify(results, null, 2))}</pre></details>
    <section class="rollout-summary panel">
      <div><span>场景</span><strong>${esc(candidate.scenario_id)}</strong></div>
      <div><span>轮数</span><strong>${esc(candidate.turn_count)}</strong></div>
      <div><span>机器预检</span><strong>${esc(machineLabel)}</strong></div>
      <div><span>模型语义复核</span><strong>${esc(semanticLabel)}</strong></div>
      <div><span>结束类型</span><strong>${esc(candidate.ending?.reason || candidate.generation_status || candidate.classification)}</strong></div>
      <div><span>实际请求</span><strong>${esc(requests.total ?? '—')}</strong></div>
      <div><span>policy/appraisal/response</span><strong>${esc(requests.policy ?? '—')} / ${esc(requests.appraisal ?? '—')} / ${esc(requests.response ?? '—')}</strong></div>
      <div><span>人工状态</span><strong>${esc(candidate.human_review)}</strong></div>
    </section>
    <section class="panel content-panel"><div class="section-kicker">MODEL SEMANTIC REVIEW</div><h3>可定位问题</h3><ul>${issueCards || '<li>未记录问题</li>'}</ul></section>
    <section class="panel turn-index"><b>跳到具体轮次</b><div>${turnLinks || '无完整轮次'}</div><p>每轮正文、Structured Appraisal、确定性数值更新、Response ledger 均直接读取保存的原始轨迹。</p></section>
    <section class="trajectory">${(trajectory.turns || []).map((turn) => `
      <article class="turn-card" id="pilot-turn-${esc(turn.turn_id)}">
        <header><b>${esc(turn.turn_id)} · ${esc(turn.segment_id || 'single_interaction')} / 片段内第 ${esc(turn.segment_turn_id ?? '—')} 轮</b><span>时间 ${esc(turn.elapsed_time_before ?? 0)} → ${esc(turn.elapsed_time_after ?? 0)}</span></header>
        ${turnInputSummary(turn)}
        <div class="chat-pair">
          <div class="chat action"><span>被评估 Agent 行动</span><p>${esc(turn.policy_action?.text || '缺失')}</p></div>
          <div class="chat response"><span>Environment 角色回应</span><p>${esc(turn.environment_response || '缺失')}</p></div>
        </div>
        ${appraisalPanel(turn)}
        ${deterministicUpdatePanel(turn)}
        ${responseAndLedgerPanel(turn)}
        ${publicEventCards(turn.segment_transition_after?.public_events)}
        ${turn.segment_transition_after ? `<div class="segment-boundary"><b>本轮后片段推进</b><p>${esc(turn.segment_transition_after.from_segment_id)} → ${esc(turn.segment_transition_after.to_segment_id || '轨迹结束')} · ${esc(turn.segment_transition_after.boundary_reason)}</p></div>` : ''}
      </article>`).join('')}</section>
    <section class="panel ending-card"><b>原始结束记录与模型复核</b><pre>${esc(JSON.stringify({ending: trajectory.ending || candidate.ending, diagnostic_review: trajectory.diagnostic_review || {}, actual_request_counts: requests}, null, 2))}</pre></section>`;
  if (trajectory.trajectory_id) renderRolloutAnnotation(trajectory);
  else $('#annotationPanel').innerHTML = '<div class="empty">原始轨迹缺失，无法标注。</div>';
}

function renderCurrentView() {
  $$('.view-tab').forEach((button) => button.classList.toggle('active', button.dataset.view === state.view));
  if (state.view === 'scenario') renderScenarioView();
  if (state.view === 'rollout') renderRolloutView();
  if (state.view === 'task') renderTaskView();
  if (state.view === 'manual') renderManualReviewView();
  if (state.view === 'materials') renderMaterialsView();
  if (state.view === 'scale20') renderScale20PilotView();
}

async function selectScenario(id) {
  state.scenarioId = id;
  state.detail = await get(`/api/scenarios/${encodeURIComponent(id)}`);
  state.trajectoryId = state.detail.rollouts?.[0]?.trajectory_id || null;
  state.taskType = 'all';
  state.taskId = state.detail.instances?.[0]?.instance_id || null;
  renderScenarioList();
  renderHeader();
  renderCurrentView();
}

function navigateCollection(kind, direction) {
  const collection = kind === 'rollout' ? state.detail.rollouts : filteredTasks();
  const currentId = kind === 'rollout' ? state.trajectoryId : state.taskId;
  const key = kind === 'rollout' ? 'trajectory_id' : 'instance_id';
  const index = collection.findIndex((item) => item[key] === currentId);
  const next = collection[index + direction];
  if (!next) return;
  if (kind === 'rollout') state.trajectoryId = next[key];
  else state.taskId = next[key];
  renderCurrentView();
}

async function importDrafts(file) {
  const payload = JSON.parse(await file.text());
  if (payload.format !== 'socialflux_browser_annotation_export_v1' || !Array.isArray(payload.records)) {
    throw new Error('不是有效的 SocialFlux 标注草稿');
  }
  const records = {};
  payload.records.forEach((record) => {
    if (!record.record_type || !record.record_id) return;
    records[`${record.record_type}:${record.record_id}`] = record;
  });
  state.drafts = {reviewer: payload.reviewer || '', records};
  saveDrafts();
  $('#reviewerId').value = state.drafts.reviewer;
  renderOverview();
  renderScenarioList();
  renderCurrentView();
  showToast(`已导入 ${Object.keys(records).length} 条草稿`);
}

function exportDrafts() {
  const payload = {
    format: 'socialflux_browser_annotation_export_v1',
    exported_at_utc: new Date().toISOString(),
    reviewer: state.drafts.reviewer,
    warning: state.contract.warning,
    record_count: Object.keys(state.drafts.records).length,
    records: Object.values(state.drafts.records)
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {type: 'application/json'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `socialflux-annotations-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
  showToast(`已导出 ${payload.record_count} 条本地草稿`);
}

document.addEventListener('click', async (event) => {
  const r3Button = event.target.closest('[data-r3-review]');
  if (r3Button) {
    await selectScenario('IA_PIPE_003');
    state.view = 'rollout';
    renderCurrentView();
    return;
  }
  const scenarioButton = event.target.closest('[data-scenario]');
  if (scenarioButton) {
    await selectScenario(scenarioButton.dataset.scenario);
    return;
  }
  const viewButton = event.target.closest('[data-view]');
  if (viewButton) {
    state.view = viewButton.dataset.view;
    renderCurrentView();
    return;
  }
  const jumpButton = event.target.closest('[data-view-jump]');
  if (jumpButton) {
    state.view = jumpButton.dataset.viewJump;
    renderCurrentView();
    return;
  }
  const statusButton = event.target.closest('[data-status]');
  if (statusButton) {
    if (statusButton.dataset.kind === 'scenario' && statusButton.dataset.status === 'approved') {
      const record = currentRecord('scenario', statusButton.dataset.id);
      const completion = scenarioReviewCompletion(record);
      const complete = completion.ratingsDone === completion.ratingTotal
        && completion.checksDone === completion.checkTotal
        && completion.attestationsDone === completion.attestationTotal
        && record.human_attestation && state.drafts.reviewer;
      if (!complete) {
        showToast('通过前需填写标注员、全部评分/检查/冻结确认及真人确认');
        return;
      }
    }
    updateRecord(statusButton.dataset.kind, statusButton.dataset.id, 'status', statusButton.dataset.status);
    renderCurrentView();
    showToast('状态已保存到当前浏览器');
    return;
  }
  const winnerButton = event.target.closest('[data-select-winner]');
  if (winnerButton) {
    (state.detail.rollouts || []).forEach((item) => {
      updateRecord('rollout', item.trajectory_id, 'selection/selected', item.trajectory_id === winnerButton.dataset.selectWinner);
    });
    renderRolloutView();
    showToast('本场景唯一赢家已更新到浏览器草稿');
    return;
  }
  const scenarioNav = event.target.closest('[data-nav-scenario]');
  if (scenarioNav) {
    const index = state.data.scenarios.findIndex((item) => item.scenario_id === state.scenarioId);
    const next = state.data.scenarios[index + Number(scenarioNav.dataset.navScenario)];
    if (next) await selectScenario(next.scenario_id);
    return;
  }
  const rolloutNav = event.target.closest('[data-nav-rollout]');
  if (rolloutNav) navigateCollection('rollout', Number(rolloutNav.dataset.navRollout));
  const pilotNav = event.target.closest('[data-nav-pilot]');
  if (pilotNav) {
    const candidates = [...(state.pilot?.candidates || []), ...(state.pilot?.v2_candidates || [])];
    const index = candidates.findIndex((item) => item.trajectory_id === state.pilotTrajectoryId);
    const next = candidates[index + Number(pilotNav.dataset.navPilot)];
    if (next) { state.pilotTrajectoryId = next.trajectory_id; renderScale20PilotView(); }
  }
  const taskNav = event.target.closest('[data-nav-task]');
  if (taskNav) navigateCollection('task', Number(taskNav.dataset.navTask));
  const filter = event.target.closest('[data-task-filter]');
  if (filter) {
    state.taskType = filter.dataset.taskFilter;
    state.taskId = filteredTasks()[0]?.instance_id || null;
    renderTaskView();
  }
});

document.addEventListener('change', (event) => {
  const element = event.target;
  if (element.id === 'trajectorySelect') {
    state.trajectoryId = element.value;
    renderRolloutView();
    return;
  }
  if (element.id === 'pilotTrajectorySelect') {
    state.pilotTrajectoryId = element.value;
    renderScale20PilotView();
    return;
  }
  if (element.id === 'taskSelect') {
    state.taskId = element.value;
    renderTaskView();
    return;
  }
  if (element.dataset.kind && element.dataset.path) {
    let value = element.type === 'checkbox' ? element.checked : element.value;
    if (element.type === 'number' || (element.tagName === 'SELECT' && /^\d+$/.test(value))) value = Number(value);
    updateRecord(element.dataset.kind, element.dataset.id, element.dataset.path, value);
    showToast('草稿已自动保存');
  }
});

document.addEventListener('input', (event) => {
  if (event.target.id === 'scenarioSearch') {
    state.search = event.target.value;
    renderScenarioList();
  }
  if (event.target.id === 'reviewerId') {
    state.drafts.reviewer = event.target.value.trim();
    saveDrafts();
  }
  if (event.target.matches('textarea[data-kind]')) {
    clearTimeout(event.target._saveTimer);
    event.target._saveTimer = setTimeout(() => {
      updateRecord(event.target.dataset.kind, event.target.dataset.id, event.target.dataset.path, event.target.value);
    }, 350);
  }
});

async function refreshLiveSummary() {
  try {
    state.data = await get('/api/summary');
    renderOverview();
    renderProgress();
    renderScenarioList();
    const editing = document.activeElement?.matches('input, textarea, select');
    if (state.view === 'manual' && !editing) renderManualReviewView();
  } catch (error) {
    console.warn('live summary refresh failed', error);
  }
}

async function boot() {
  try {
    [state.data, state.contract, state.pilot] = await Promise.all([get('/api/summary'), get('/api/annotation-contract'), get('/api/scale20-review')]);
    state.pilotTrajectoryId = state.pilot.candidates?.[0]?.trajectory_id || null;
    $('#reviewerId').value = state.drafts.reviewer;
    renderOverview();
    renderProgress();
    state.scenarioId = state.data.scenarios[0]?.scenario_id;
    renderScenarioList();
    if (state.scenarioId) await selectScenario(state.scenarioId);
    $('#exportButton').onclick = exportDrafts;
    $('#importButton').onclick = () => $('#importFile').click();
    $('#importFile').onchange = async (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      try { await importDrafts(file); }
      catch (error) { showToast(`导入失败：${error.message}`); }
      event.target.value = '';
    };
    setInterval(refreshLiveSummary, 30000);
  } catch (error) {
    document.body.innerHTML = `<main class="fatal"><h1>无法加载标注工作台</h1><pre>${esc(error.message)}</pre></main>`;
  }
}

boot();
