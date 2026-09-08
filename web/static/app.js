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
  return state.drafts.records[key] || {
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
  const done = records.filter((item) => statusDone(item.status)).length;
  const categories = state.data.manual_review?.categories || [];
  const tracked = new Set(['gate1_scenario', 'gate3_rollout', 'gate4_tasks', 'media']);
  const expected = categories.filter((item) => tracked.has(item.id))
    .reduce((sum, item) => sum + Number(item.available || 0), 0);
  $('#localProgress').textContent = `${done} / ${expected} 个可用审核单元 · 本机草稿`;
}

function renderOverview() {
  const manifest = state.data.pipeline_manifest || {};
  const totals = manifest.totals || {};
  const gate = state.data.acceptance.gate || {};
  $('#scenarioCount').textContent = state.data.scenario_count;
  $('#gateBadge').textContent = gate.research_acceptance ? 'RESEARCH GATE · PASS' : 'RESEARCH GATE · PENDING';
  const screening = state.data.screening || {};
  const values = [
    ['SCENARIOS', state.data.scenario_count, '情节与 S0/D0'],
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
      <i class="review-dot ${statusDone(record.status) ? 'done' : ''}"></i>
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
      <div class="header-counts"><b>1</b> 最终 rollout <b>${state.detail.rollouts?.length || 0}</b> 人工候选 <b>${summary.task_count}</b> task <b>${summary.trigger_count}</b> video</div>
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
  const assets = state.detail.media_assets || [];
  $('#viewToolbar').innerHTML = `<div><span class="toolbar-title">情节全貌</span><span class="toolbar-note">先判断故事是否值得进入 benchmark，再审核 S0/D0 与视频阈值</span></div>`;
  $('#viewContent').innerHTML = `
    <section class="panel content-panel">
      <div class="section-kicker">STORY MAP</div>
      <h3>冲突结构与人物目标</h3>
      <div class="two-column">
        <div class="role-card agent"><span>被评估对话参与者</span><strong>${esc(scenario.evaluated_agent_role?.name)}</strong><p>${esc(scenario.evaluated_agent_role?.explicit_goal)}</p></div>
        <div class="role-card environment"><span>环境角色 / 状态目标</span><strong>${esc(scenario.environment_agent?.persona?.name)}</strong><p>${esc(scenario.environment_agent?.explicit_goal)}</p></div>
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
        return `<article class="trigger-card"><div class="trigger-title"><strong>${esc(trigger.trigger_id)}</strong><span>${esc(trigger.trigger_mode)}</span></div>
          <div class="condition-list">${conditions}${changes}</div>
          <p>${esc(trigger.observable_expression?.facial_expression)} · ${esc(trigger.observable_expression?.prosody)}</p>
          ${asset ? `<video controls preload="metadata" src="${esc(asset.url)}"></video><small>${esc(asset.utterance)} · ${esc(asset.duration_seconds)}s</small>` : '<div class="media-pending">视频未生成</div>'}
        </article>`;
      }).join('')}</div>
    </section>`;
  renderScenarioAnnotation();
}

function dialogueHistory(history, compact = false) {
  if (!history?.length) return '<div class="empty">无历史：这是初始检查点</div>';
  return `<div class="dialogue-history ${compact ? 'compact' : ''}">${history.map((turn) => `
    <article class="dialogue-turn">
      <div class="speaker action"><span>${esc(turn.turn_id)}</span><p>${esc(turn.policy_action?.text)}</p></div>
      <div class="speaker response"><span>环境角色</span><p>${esc(turn.environment_response)}</p></div>
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

function renderRolloutView() {
  const rollouts = state.detail.rollouts || [];
  const trajectory = rollouts.find((item) => item.trajectory_id === state.trajectoryId) || rollouts[0];
  if (!trajectory) {
    $('#viewToolbar').innerHTML = '';
    $('#viewContent').innerHTML = '<div class="empty">没有需要人工审核的 rollout</div>';
    $('#annotationPanel').innerHTML = '';
    return;
  }
  state.trajectoryId = trajectory.trajectory_id;
  const index = rollouts.indexOf(trajectory);
  const provenance = trajectory.policy_provenance || {};
  const screening = trajectory.screening || {};
  $('#viewToolbar').innerHTML = `
    <div class="toolbar-group">
      <button class="icon-button" data-nav-rollout="-1" ${index === 0 ? 'disabled' : ''}>←</button>
      <select id="trajectorySelect">${rollouts.map((item, i) => `<option value="${esc(item.trajectory_id)}" ${item.trajectory_id === trajectory.trajectory_id ? 'selected' : ''}>${i + 1}/${rollouts.length} · ${item.screening?.provisional_selected ? '★ ' : ''}${esc(item.screening?.automatic_decision || 'PENDING')} · ${esc(item.policy_id || item.policy_provenance?.model)}</option>`).join('')}</select>
      <button class="icon-button" data-nav-rollout="1" ${index === rollouts.length - 1 ? 'disabled' : ''}>→</button>
    </div>
    <div class="toolbar-note mono">全部人工候选均在此 · ${esc(trajectory.trajectory_id)}</div>`;
  $('#viewContent').innerHTML = `
    <section class="rollout-summary panel">
      <div><span>模型</span><strong>${esc(provenance.model || trajectory.policy_id)}</strong></div>
      <div><span>轮数</span><strong>${trajectory.turns?.length || 0}</strong></div>
      <div><span>自动决策</span><strong>${esc(screening.automatic_decision || 'PENDING')}</strong></div>
      <div><span>最终池</span><strong>${screening.provisional_selected ? '建议保留 1 条' : '候选/审计档案'}</strong></div>
    </section>
    ${screeningEvidence(screening)}
    <section class="trajectory">${(trajectory.turns || []).map((turn) => `
      <article class="turn-card">
        <header><b>${esc(turn.turn_id)}</b><span>${(turn.trigger_events || []).length ? 'VIDEO TRIGGER' : 'STATEFUL TURN'}</span></header>
        <div class="chat-pair">
          <div class="chat action"><span>对话参与者</span><p>${esc(turn.policy_action?.text)}</p></div>
          <div class="chat response"><span>环境角色</span><p>${esc(turn.environment_response)}</p></div>
        </div>
        <details><summary>查看状态变化与可观察表现</summary>
          <div class="turn-diagnostics">
            <div><h5>状态变化</h5><div class="delta-wrap">${deltaChips(turn.numeric_state_delta)}</div></div>
            <div><h5>外显表现</h5><p>${esc(turn.observable_expression?.facial_expression || '—')}<br>${esc(turn.observable_expression?.gaze || '—')}<br>${esc(turn.observable_expression?.prosody || '—')}</p></div>
          </div>
        </details>
      </article>`).join('')}</section>`;
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
  return `<div class="observation-card"><span>${esc(title)}</span>
    <p>${esc(observation.current_response || '尚无当前回应')}</p>
    <small>表情：${esc(observation.observable_expression?.facial_expression || '—')}<br>
    视线：${esc(observation.observable_expression?.gaze || '—')}<br>
    韵律：${esc(observation.observable_expression?.prosody || '—')}</small>
  </div>`;
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
    </section>`;
  }

  if (task.task_type === 'T2_history_sensitive_merge') {
    const shared = input.shared_observation || input.shared_current_observation || input.current_observation;
    return `<section class="panel content-panel">${heading}<p class="instruction">比较两段自然历史；在相同 O* 下判断目标角色状态是 A 更高、相近、B 更高，还是无法确定。</p>
      <div class="history-compare">
        <div><h4>历史 A</h4>${dialogueHistory(input.history_a, true)}</div>
        <div><h4>历史 B</h4>${dialogueHistory(input.history_b, true)}</div>
      </div>
      ${observationCard(shared, '共享当前观察 O*')}
    </section>`;
  }

  return `<section class="panel content-panel">${heading}<p class="instruction">从同一真实检查点比较候选行动对目标环境角色的即时与 ${esc(task.target_spec?.delayed_horizon)} 轮延迟影响。</p>
    ${dialogueHistory(input.history)}
    ${observationCard(input.current_observation)}
    <div class="candidate-list">${(input.candidate_actions || []).map((action, index) =>
      `<article><span>OPTION ${index + 1}</span><p>${esc(action.text)}</p></article>`
    ).join('')}</div>
  </section>`;
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
      <button class="${state.taskType === 'all' ? 'active' : ''}" data-task-filter="all">全部 9</button>
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

function renderScenarioAnnotation() {
  const id = state.scenarioId;
  const record = currentRecord('scenario', id);
  const media = state.detail.media_assets || [];
  const mediaChecks = media.map((asset) => {
    const mediaRecord = currentRecord('media', asset.asset_id);
    return `<details class="media-review"><summary>${esc(asset.trigger_label)} · ${esc(asset.status)}</summary>
      ${annotationHeader('视频审核', 'media', asset.asset_id, mediaRecord)}
      ${['expression_state_consistency','temporal_continuity','speech_naturalness','multimodal_utility'].map((key) => `<label class="check-line"><input type="checkbox" data-kind="media" data-id="${esc(asset.asset_id)}" data-path="checks/${key}" ${mediaRecord.checks?.[key] ? 'checked' : ''}> ${esc(label(key))}</label>`).join('')}
      ${notesField('media', asset.asset_id, mediaRecord, '视频问题与证据')}
    </details>`;
  }).join('');
  $('#annotationPanel').innerHTML = `${annotationHeader('Scenario 审核', 'scenario', id, record)}
    <div class="form-section"><h4>核心质量 · 1–5</h4>${ratingRows('scenario', id, state.contract.scenario_rating_scale.dimensions, record)}</div>
    <div class="form-section"><h4>Gate 1 检查</h4>${triStateRows('scenario', id, state.contract.scenario_checks, record)}</div>
    <div class="form-section"><h4>冻结确认</h4>
      <label class="check-line"><input type="checkbox" data-kind="scenario" data-id="${esc(id)}" data-path="freeze/s0_reviewed" ${record.freeze?.s0_reviewed ? 'checked' : ''}> S0 数值与人物背景一致</label>
      <label class="check-line"><input type="checkbox" data-kind="scenario" data-id="${esc(id)}" data-path="freeze/d0_reviewed" ${record.freeze?.d0_reviewed ? 'checked' : ''}> D0 动力合理</label>
      <label class="check-line"><input type="checkbox" data-kind="scenario" data-id="${esc(id)}" data-path="freeze/triggers_reviewed" ${record.freeze?.triggers_reviewed ? 'checked' : ''}> 视频阈值可达且不在初始状态误触发</label>
    </div>
    ${notesField('scenario', id, record)}
    <div class="form-section"><h4>Talking Head 逐视频审核</h4>${mediaChecks || '<div class="empty">没有视频资产</div>'}</div>`;
}

function renderRolloutAnnotation(trajectory) {
  const id = trajectory.trajectory_id;
  const record = currentRecord('rollout', id);
  const auto = trajectory.screening || {};
  const selected = record.selection?.selected ?? auto.provisional_selected;
  $('#annotationPanel').innerHTML = `${annotationHeader('Rollout 协议审核', 'rollout', id, record)}
    <button class="button ${selected ? 'primary' : ''} wide" data-select-winner="${esc(id)}">${selected ? '✓ 当前场景保留此条' : '将此条设为场景唯一赢家'}</button>
    <p class="selection-warning">选择另一条会自动取消本场景此前的选择；导出后仍需实名、时间和哈希绑定。</p>
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
  $('#viewToolbar').innerHTML = '<div><span class="toolbar-title">完整人工工作面</span><span class="toolbar-note">可做、未生成、被前序 Gate 阻塞的项目全部列出</span></div>';
  $('#viewContent').innerHTML = `<section class="manual-grid">${(review.categories || []).map((item) => `
    <article class="panel manual-card"><div class="screening-title"><h3>${esc(item.title)}</h3><span class="decision review">${esc(item.status)}</span></div>
      <p>${esc(item.description)}</p><div class="manual-count"><strong>${esc(item.available)}</strong><span>/ ${esc(item.required)} 可用</span></div><small>查看位置：${esc(item.location)}</small></article>`).join('')}</section>
    <section class="panel content-panel"><div class="section-kicker">GATE 2 FILES</div><h3>Environment 人工证据</h3>
      <div class="file-status-list">${Object.entries(review.environment_files || {}).map(([name, value]) => `<div><code>${esc(name)}</code><span>${value.human_attestation ? '已实名签署' : value.exists ? '文件存在但未人工通过' : '尚未生成'}</span></div>`).join('')}</div></section>
    <details class="panel document-panel"><summary>SocialFlux Rollout Screening Protocol v1 全文</summary><pre>${esc(review.protocol_document || '')}</pre></details>`;
  $('#annotationPanel').innerHTML = `<div class="annotation-head"><div><div class="section-kicker">NO HIDDEN TODO</div><h3>人工审核边界</h3></div></div>
    <p class="annotation-copy">本页列出所有人工阶段。具体情节、轨迹、题目和视频在对应页面直接标注；尚未生成的 E1–E5、holdout 和 formal GT 仍显示为 pending，不会从界面消失。</p>
    <div class="audit-callout"><b>推荐顺序</b><ol><li>Gate 1 冻结 scenario/S0/D0</li><li>完成 Gate 2 E1–E5</li><li>审核 rollout 协议队列并每场景确认 1 条</li><li>重建正式 tasks 后做 Gate 4</li><li>三人盲标、仲裁与 agreement</li></ol></div>`;
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

function renderCurrentView() {
  $$('.view-tab').forEach((button) => button.classList.toggle('active', button.dataset.view === state.view));
  if (state.view === 'scenario') renderScenarioView();
  if (state.view === 'rollout') renderRolloutView();
  if (state.view === 'task') renderTaskView();
  if (state.view === 'manual') renderManualReviewView();
  if (state.view === 'materials') renderMaterialsView();
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
  const rolloutNav = event.target.closest('[data-nav-rollout]');
  if (rolloutNav) navigateCollection('rollout', Number(rolloutNav.dataset.navRollout));
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

async function boot() {
  try {
    [state.data, state.contract] = await Promise.all([get('/api/summary'), get('/api/annotation-contract')]);
    $('#reviewerId').value = state.drafts.reviewer;
    renderOverview();
    renderProgress();
    state.scenarioId = state.data.scenarios[0]?.scenario_id;
    renderScenarioList();
    if (state.scenarioId) await selectScenario(state.scenarioId);
    $('#exportButton').onclick = exportDrafts;
  } catch (error) {
    document.body.innerHTML = `<main class="fatal"><h1>无法加载标注工作台</h1><pre>${esc(error.message)}</pre></main>`;
  }
}

boot();
