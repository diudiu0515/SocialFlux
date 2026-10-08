'use strict';
const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={emotion:'情绪',behavioral_disposition:'行为倾向',relationship:'关系判断',consequence_risk:'后果风险',dynamics:'互动条件',boundary_assertion:'边界主张',decision_readiness:'决策准备度',autonomy_loss_risk:'自主权丧失风险',coordination_stability:'协调稳定性',anxiety:'焦虑',frustration:'挫败',hope:'希望',anger:'愤怒',sadness:'悲伤',guilt:'内疚',shame:'羞耻',gratitude:'感激',trust:'信任',perceived_responsiveness:'感知回应性',perceived_fairness:'感知公平性',role_legitimacy:'角色正当性',respect:'尊重',closeness:'亲近',psychological_safety:'心理安全感',safety:'安全感',cooperation_readiness:'合作意愿',disclosure_willingness:'披露意愿',evidence_seeking:'证据寻求',assertiveness:'主张意愿',avoidance:'回避',goal_failure_risk:'目标失败风险',institutional_harm_risk:'机构损害风险',decision_error_risk:'决策错误风险',relationship_damage_risk:'关系受损风险',deadline_pressure:'期限压力',resource_scarcity:'资源稀缺',information_asymmetry:'信息不对称',negotiation_openness:'协商开放度',institutional_constraint:'制度约束'};
const statuses={queued:'排队中',running:'生成中',completed:'生成完成 · 待审',call_or_validation_failure:'调用中断',runner_failure:'执行中断',interrupted:'已中断',waiting_for_rollouts:'等待生成结束',running_gate2:'自动检查进行中',automatic_finished:'自动检查已结束',blocked_insufficient_trajectories:'样本不足 · 人工包已准备',gate2_error:'检查执行出错',not_started:'尚未开始'};
const judgments={ordinary_new_evidence:'普通新增证据',decisive_new_evidence:'决定性新增证据',repeated_evidence_only:'重复证据',no_relevant_evidence:'无相关证据'};
const palette=['#1e7963','#c48736','#5884ba','#a96791','#739348','#9b6455'];
let overview=null,selected=null,detail=null,versionKey=null,family='relationship',signature='',requestId=0,busy=false;
function flat(o,p=''){let r={};Object.entries(o||{}).forEach(([k,v])=>{let key=p?p+'.'+k:k;if(v!==null&&typeof v==='object')Object.assign(r,flat(v,key));else r[key]=v;});return r;}
function label(key){return key.split('.').map(x=>names[x]||x).join(' · ');}
function badge(status){return `<span class="badge ${status==='completed'?'completed':status==='running'?'running':status.includes('failure')?'failed':''}">${esc(statuses[status]||status)}</span>`;}
async function get(url){const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw Error('数据读取失败：'+r.status);return r.json();}
function error(e){$('error').textContent=e.message||String(e);$('error').hidden=false;}
function renderSummary(){const c=overview.counts;const data=[['场景',overview.expected_count,'每个场景一条 rollout'],['生成完成',c.completed,'完成不代表人工通过'],['生成中',c.running,'新轮次自动显示'],['当前可读',c.readable,'含未完成的部分轨迹'],['待执行 / 中断',`${c.queued} / ${c.failed}`,'失败记录保留']];$('summary').innerHTML=data.map(([t,n,h])=>`<div class="metric"><span>${esc(t)}</span><strong>${esc(n)}</strong><span>${esc(h)}</span></div>`).join('');$('updated').textContent='每 10 秒刷新 · '+new Date(overview.updated_at).toLocaleTimeString('zh-CN');}
function gateBadges(item) {
  const review = item?.gate3 || {}, errors = item?.gate2_errors || [];
  let html = '';
  if (review.decision === 'reject') html += '<span class="badge failed" data-gate3="reject">Gate3 模型未通过</span>';
  else if (review.decision === 'approve') html += `<span class="badge ${review.partial ? '' : 'completed'}" data-gate3="approve">${review.partial ? 'Gate3 正文通过 · 轨迹不完整' : 'Gate3 模型通过 · 人工待审'}</span>`;
  else if (review.status === 'source_changed') html += '<span class="badge">Gate3 结果与当前轨迹不匹配</span>';
  if (errors.length) html += '<span class="badge failed" data-gate2="error">Gate2 执行出错</span>';
  return html;
}
function renderList() {
  const q = $('search').value.toLowerCase(), gateFilter = $('gateFilter').value;
  const rows = overview.scenarios.filter(s =>
    (!$('readableOnly').checked || s.history_available)
    && (gateFilter !== 'rejected' || s.gate3?.decision === 'reject')
    && (gateFilter !== 'errors' || s.gate2_errors?.length)
    && [s.scenario_id,s.title,s.policy_name,s.environment_name].join(' ').toLowerCase().includes(q));
  $('scenarios').innerHTML = rows.map(s => `<button class="scenario-button ${s.scenario_id === selected ? 'active' : ''}" data-id="${esc(s.scenario_id)}"><span class="id">${esc(s.scenario_id)}</span><strong>${esc(s.title)}</strong><small>${esc(statuses[s.status] || s.status)} · 当前 ${s.turn_count} 轮${!s.readable && s.history_available ? ' · 有历史记录' : ''}</small><small>${gateBadges(s)}</small></button>`).join('') || '<p class="subtle">没有匹配场景</p>';
}
const scoreNames = {dialogue_coherence:'对话连贯性',history_dependence:'历史依赖',character_consistency:'人物一致性',state_response_consistency:'可见表达与回应一致性',interaction_progression:'互动推进',naturalness:'自然度'};
function renderGate3(version) {
  const review = version?.gate3 || {}, issues = version?.gate2_errors || [];
  const pending = {historical_not_reviewed:'这条历史记录没有本批 Gate3 审核结果。',no_trajectory:'当前场景没有可审核正文。',source_changed:'轨迹已变化，旧审核结果不适用于当前记录。'};
  let body = gateBadges(version);
  if (review.status === 'reviewed') {
    body += `<p class="subtle">审核模型：${esc(review.model || '')}。${review.partial ? '仅审核了已有部分正文，轨迹仍不完整。' : ''}模型结论不代表人工通过。</p>`;
    const scores = Object.entries(review.scores || {});
    body += `<div class="table-wrap"><table><thead><tr><th>维度</th><th>评分 / 5</th><th>通过要求</th><th>证据轮次</th></tr></thead><tbody>${scores.map(([key,value]) => {
      const minimum = ['history_dependence','character_consistency','naturalness'].includes(key) ? 4 : 3;
      return `<tr><td>${esc(scoreNames[key] || key)}</td><td>${esc(value)}${value < minimum ? ' <span class="badge failed">低于要求</span>' : ''}</td><td>≥ ${minimum}</td><td>${esc((review.evidence?.[key] || []).join(', '))}</td></tr>`;
    }).join('')}</tbody></table></div>`;
    if (review.hard_reject_reasons?.length) body += `<p class="error-line">硬性拒绝原因：${esc(review.hard_reject_reasons.join(', '))}</p>`;
    body += `<p class="background" lang="en">${esc(review.rationale || '')}</p>`;
  } else body += `<p class="subtle">${esc(pending[review.status] || 'Gate3 尚无审核结论。')}</p>`;
  if (issues.length) body += issues.map(issue => `<p class="error-line">${esc(issue.stage)} · ${esc(issue.checkpoint_turn_id || '')}：${esc(issue.message)}（${esc(issue.type)}）。这是执行错误，不是质量拒绝。</p>`).join('');
  return `<section id="qualitySection" class="panel"><h3>Gate3 质量审核 · 人工待审</h3>${body}</section>`;
}
function stateTable(before,after,judged=[]){const a=flat(before),b=flat(after);const js=Object.fromEntries(judged.map(j=>[j.variable,j]));return `<div class="table-wrap"><table><thead><tr><th>变量</th><th>更新前</th><th>更新后</th><th>变化</th><th>判断与依据</th></tr></thead><tbody>${Object.entries(a).map(([k,v])=>{const delta=Number(b[k]??v)-Number(v),j=js[k]||{};return `<tr><td title="${esc(k)}">${esc(label(k))}</td><td>${esc(v)}</td><td>${esc(b[k]??v)}</td><td class="${delta>0?'up':delta<0?'down':'same'}">${delta>0?'+':''}${delta}</td><td class="reason">${esc(judgments[j.judgment]||'')} ${j.evidence_span?'<br>引用：'+esc(j.evidence_span):''}${j.rationale?'<br>'+esc(j.rationale):''}</td></tr>`;}).join('')}</tbody></table></div>`;}
function initialTable(state){return `<div class="table-wrap"><table><tbody>${Object.entries(flat(state)).map(([k,v])=>`<tr><td>${esc(label(k))}</td><td>${esc(v)}</td></tr>`).join('')}</tbody></table></div>`;}
function currentVersion(){return detail?.versions.find(v=>v.key===versionKey)||detail?.versions[0];}
// Build every series from the selected trajectory; never fabricate missing samples.
function chartSeries(version, scenario, group) {
  const turns = version?.turns || [];
  const read = (turn, when) => group === 'dynamics' ? turn['dynamics_' + when] : turn['state_' + when]?.[group];
  const initial = (group === 'dynamics' ? version?.initial_dynamics : version?.initial_state?.[group])
    ?? read(turns[0] || {}, 'before')
    ?? (group === 'dynamics' ? scenario.initial_dynamics : scenario.initial_state?.[group]) ?? {};
  const keys = [...new Set([Object.keys(initial), ...turns.map(t => Object.keys(read(t, 'after') || {}))].flat())];
  const numeric = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
  return {ticks: ['初始', ...turns.map(t => t.turn_id)], series: keys.map((key, index) => ({
    key, color: palette[index % palette.length],
    values: [numeric(initial[key]), ...turns.map(t => numeric(read(t, 'after')?.[key]))]
  }))};
}
let chartVariable = '';
function drawChart() {
  const v = currentVersion(), ts = v?.turns || [], s = detail.scenario;
  if (!ts.length) {
    $('chartTabs').innerHTML = '';
    $('chart').innerHTML = '<p class="subtle">当前记录没有已完成的对话轮次，下面仅为场景预设的初始数值，没有发生 state 转换。</p>' + initialTable(v?.initial_state || s.initial_state) + initialTable(v?.initial_dynamics || s.initial_dynamics);
    $('legend').innerHTML = '';
    return;
  }
  const groups = [...new Set([...Object.keys(v?.initial_state || s.initial_state || {}), ...ts.flatMap(t => Object.keys(t.state_after || {})), 'dynamics'])];
  if (!groups.includes(family)) family = groups[0];
  $('chartTabs').innerHTML = groups.map(g => `<button class="${g === family ? 'active' : ''}" data-family="${esc(g)}">${esc(names[g] || g)}</button>`).join('');
  const {ticks, series} = chartSeries(v, s, family);
  if (!series.some(item => item.key === chartVariable)) chartVariable = '';
  const visible = series.filter(item => !chartVariable || item.key === chartVariable);
  const X = i => 42 + i * 820 / Math.max(ts.length, 1), Y = n => 208 - n * 18;
  const patterns = ['', '7 4', '2 4', '10 3 2 3', '1 3', '5 3 1 3'];
  let svg = `<svg viewBox="0 0 890 242" role="img" aria-label="${esc(names[family] || family)}逐轮状态曲线">`;
  for (let n = 0; n <= 10; n += 2) svg += `<line x1="42" x2="862" y1="${Y(n)}" y2="${Y(n)}" stroke="#e7ece8"/><text x="16" y="${Y(n) + 4}" fill="#8a978e" font-size="11">${n}</text>`;
  ticks.forEach((tick, i) => { svg += `<text x="${X(i)}" y="230" text-anchor="middle" fill="#7d8c83" font-size="10">${esc(tick)}</text>`; });
  visible.forEach(item => {
    const segments = []; let segment = [];
    item.values.forEach((value, i) => {
      if (value === null) { if (segment.length) segments.push(segment); segment = []; }
      else segment.push(`${X(i)},${Y(value)}`);
    });
    if (segment.length) segments.push(segment);
    const dash = patterns[series.indexOf(item) % patterns.length];
    svg += `<g data-state-variable="${esc(item.key)}">`;
    segments.forEach(points => { svg += `<polyline fill="none" stroke="${item.color}" stroke-width="2" stroke-dasharray="${dash}" points="${points.join(' ')}"/>`; });
    item.values.forEach((value, i) => {
      if (value !== null) svg += `<circle cx="${X(i)}" cy="${Y(value)}" r="3.5" fill="${item.color}"><title>${esc(label(item.key))} · ${esc(ticks[i])}：${value}</title></circle>`;
    });
    svg += '</g>';
  });
  svg += '</svg>';
  const overlaps = series.flatMap((item, i) => series.slice(i + 1)
    .filter(other => item.values.every((v, j) => v === other.values[j]))
    .map(other => `${label(item.key)} / ${label(other.key)}`));
  const missing = series.some(item => item.values.includes(null));
  const table = `<details><summary>查看全部 ${series.length} 个变量的逐轮数值</summary><div class="table-wrap"><table><thead><tr><th>变量</th>${ticks.map(t => `<th>${esc(t)}</th>`).join('')}</tr></thead><tbody>${series.map(item => `<tr><td>${esc(label(item.key))}</td>${item.values.map(value => `<td>${value === null ? '缺失' : value}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
  $('chart').innerHTML = `<label class="subtle" for="chartVariable">查看变量 </label><select id="chartVariable"><option value="">全部 ${series.length} 个变量</option>${series.map(item => `<option value="${esc(item.key)}" ${item.key === chartVariable ? 'selected' : ''}>${esc(label(item.key))}</option>`).join('')}</select><p class="subtle">初始值 + ${ts.length} 轮，共 ${ticks.length} 个时间点。同值线段会重叠，可选择单个变量核对；窄屏可左右滚动。${overlaps.length ? '<br>全程重合：' + esc(overlaps.join('；')) + '。' : ''}${missing ? '<br>缺失的数值保留为空，不补成 0。' : ''}</p>${svg}${table}`;
  $('chartVariable').onchange = event => { chartVariable = event.target.value; drawChart(); };
  $('legend').innerHTML = visible.map(item => `<span><i style="background:${item.color};"></i>${esc(label(item.key))}</span>`).join('');
}
function renderDetail(){const s=detail.scenario,v=currentVersion(),role=s.evaluated_agent_role||{},env=s.environment_agent||{},persona=env.persona||{},entry=overview.scenarios.find(x=>x.scenario_id===selected),gate=detail.gate2||{};const turns=v?.turns||[];
const previousMedia=$('multimodalSection');
LiveMultimodal.remember(previousMedia);
$('main').innerHTML=`<section class="panel"><div class="heading-row"><div class="subtle">${esc(s.scenario_id)} · 审核视图</div><div>${badge(entry.status)}</div></div><h2>${esc(s.title)}</h2><div class="versions" id="scenarioGateStatus">${gateBadges(v)}${v?.gate3?.decision==='reject'?'<a href="#qualitySection" id="showGateReasons">查看未通过原因</a>':''}</div><p class="background">${esc(s.shared_background||s.background)}</p><div class="roles"><div class="role"><span class="subtle">被测方 · GPT</span><b>${esc(role.name)}</b><p>${esc(role.role)}</p><p>目标：${esc(role.explicit_goal)}</p><details><summary>查看被测方可见背景</summary><p>${esc(s.policy_background)}</p></details></div><div class="role"><span class="subtle">环境方 · Fable</span><b>${esc(persona.name)}</b><p>${esc(persona.role)}</p><p>目标：${esc(env.explicit_goal)}</p><details><summary>查看环境方可见背景与私有意图</summary><p>${esc(s.environment_background)}</p><p>${esc(env.hidden_intention)}</p></details></div></div><details><summary>完整场景背景、历史与初始状态</summary><p class="subtle">以下为作者视图，可能包含任一角色尚不知道的信息。</p><p class="background">${esc(s.background)}</p><ul>${(s.narrative_design?.relevant_history||[]).map(h=>`<li class="background">${esc(h)}</li>`).join('')}</ul>${initialTable(s.initial_state)}${initialTable(s.initial_dynamics)}</details><div class="versions"><button id="showRollout">查看 Rollout 对话 · ${turns.length} 轮</button><button id="showMultimodal">查看多模态 · 视频与声音</button><button id="showState">${turns.length?"查看 State 变化":"查看初始 State"}</button></div><div class="versions"><label for="version">轨迹记录</label><select id="version">${detail.versions.length?detail.versions.map(x=>`<option value="${esc(x.key)}" ${x.key===versionKey?'selected':''}>${esc(x.label)} · ${x.turn_count} 轮</option>`).join(''):'<option>尚无轨迹</option>'}</select><button id="download">下载场景与当前轨迹 JSON</button></div>${v?`<div class="notice ${v.current?'current':''}">${esc(v.label)} · ${turns.length} 个已完成轮次。${v.invalid_configuration?'此记录使用过错误的结束轮数配置，已排除，不作为当前批次成果。':v.current?'每完成一轮即展示；生成与机器检查均不等于人工审核通过。':'这是历史中断记录，用于检查和追溯。'}${v.error?`<div class="error-line">${esc(v.error)}</div>`:''}</div>`:''}</section>
${renderGate3(v)}
<section id="multimodalSection" class="panel mm-panel" aria-label="多模态视频与触发证据"></section>
<section id="rolloutSection" class="panel"><div class="heading-row"><h3>Rollout 对话 <span class="subtle">${turns.length} 轮</span></h3><span class="subtle">${v?.ending?'结束：'+esc(v.ending.reason):turns.length?'部分轨迹 · 尚未结束':'尚无对话轮次'}</span></div>${turns.length?turns.map(t=>{const changes=Object.entries(flat(t.numeric_state_delta)).filter(([,d])=>Number(d)!==0);return `<article class="turn"><div class="turn-head">${esc(t.turn_id)} · ${changes.length?changes.map(([k,d])=>`<span class="delta-pill">${esc(label(k))} ${Number(d)>0?'+':''}${esc(d)}</span>`).join(''):'state 保持不变'}</div><div class="utterance"><b>${esc(role.name)} · 被测方</b><p>${esc(t.policy_action?.text)}</p></div><div class="utterance environment"><b>${esc(persona.name)} · 环境方</b><p>${esc(t.environment_response)}</p></div><details><summary>查看本轮全部 state 数值、引用与判断依据</summary>${stateTable(t.state_before,t.state_after,t.state_judgments||[])}<h4>互动条件</h4>${stateTable(t.dynamics_before,t.dynamics_after,t.dynamics_judgments||[])}</details></article>`;}).join(''):'<div class="empty">此场景尚无已完成轮次。<br>场景内容和初始 state 已可查看，生成结果会自动出现。</div>'}</section>
<section id="stateSection" class="panel"><h3>${turns.length?"State 逐轮变化":"初始 State · 尚无转换"}</h3><p class="subtle">状态主体：${esc(persona.name)}（环境方）。每轮列出更新前后数值和对应证据。</p><div id="chartTabs" class="tabs"></div><div id="chart" class="chart"></div><div id="legend" class="legend"></div>${turns.length?'<p class="subtle">纵轴 0–10；与上方当前选中 rollout 的对话轮次一一对应。</p>':''}</section>
<section class="panel"><h3>Gate2 与人工审核</h3><p>${esc(statuses[gate.status]||gate.status)} · ${gate.machine_ready?'自动证据已齐备':'尚无自动通过结论'}</p><div class="gate-grid">${(gate.packets||[]).map(p=>`<span>${esc(p.id)}：${p.items} 项 · ${esc(p.status)}</span>`).join('')}</div><p class="subtle">这里显示当前批次状态。E1 状态方向、E2 对话合理性、E9 变化速度及其他语义判断保留给人工；本页面不自动签署结论。</p></section>`;
if(previousMedia){$('multimodalSection').replaceWith(previousMedia);}
LiveMultimodal.mount($('multimodalSection'),{scenarioId:s.scenario_id,version:v});
$('showMultimodal').onclick=()=>$('multimodalSection').scrollIntoView({behavior:'smooth',block:'start'});
if($('showGateReasons'))$('showGateReasons').onclick=event=>{event.preventDefault();$('qualitySection').scrollIntoView({behavior:'smooth',block:'start'});};
drawChart();$('showRollout').onclick=()=>$('rolloutSection').scrollIntoView({behavior:'smooth',block:'start'});$('showState').onclick=()=>$('stateSection').scrollIntoView({behavior:'smooth',block:'start'});$('version').onchange=()=>{versionKey=$('version').value;signature='';renderDetail();};$('chartTabs').onclick=e=>{const button=e.target.closest('[data-family]');if(button){family=button.dataset.family;chartVariable='';drawChart();}};$('download').onclick=()=>{const blob=new Blob([JSON.stringify({scenario:s,rollout:currentVersion()||null,human_review_status:'pending'},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=s.scenario_id+'_review.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};}
async function select(id){selected=id;versionKey=null;signature='';location.hash=id;renderList();await refreshDetail(true);}
async function refreshDetail(force=false){if(!selected)return;const id=++requestId,requested=selected;const d=await get('/api/gpt50-live/'+encodeURIComponent(requested));if(id!==requestId||requested!==selected)return;detail=d;if(!d.versions.some(x=>x.key===versionKey))versionKey=d.versions[0]?.key||null;const mark=JSON.stringify([requested,versionKey,d.versions.map(x=>[x.key,x.modified_at,x.status,x.gate3,x.gate2_errors]),d.gate2,overview.scenarios.find(x=>x.scenario_id===requested)?.status]);if(force||mark!==signature){signature=mark;renderDetail();}}
async function refresh(){if(busy)return;busy=true;try{overview=await get('/api/gpt50-live');renderSummary();if(!selected){const hash=decodeURIComponent(location.hash.slice(1));selected=overview.scenarios.find(s=>s.scenario_id===hash)?.scenario_id||overview.scenarios.find(s=>s.readable)?.scenario_id||overview.scenarios[0]?.scenario_id;}renderList();await refreshDetail();$('error').hidden=true;}catch(e){error(e);}finally{busy=false;}}
$('gateFilter').onchange=()=>overview&&renderList();
$('search').oninput=()=>overview&&renderList();$('readableOnly').onchange=()=>overview&&renderList();$('scenarios').onclick=e=>{const b=e.target.closest('[data-id]');if(b)select(b.dataset.id).catch(error);};$('refresh').onclick=refresh;
refresh();setInterval(refresh,10000);
