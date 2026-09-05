const $ = (selector) => document.querySelector(selector);
const state = {data:null, detail:null, scenarioId:null, trajectoryId:null};
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const flat = (obj, prefix='') => Object.entries(obj || {}).flatMap(([key,value]) => typeof value === 'object' && value !== null ? flat(value, prefix ? `${prefix}.${key}` : key) : [[prefix ? `${prefix}.${key}` : key, value]]);
const deltaClass = (value) => value > 0 ? 'up' : value < 0 ? 'down' : '';
const deltaText = (value) => value > 0 ? `+${value}` : `${value}`;

async function get(path){const response=await fetch(path); if(!response.ok) throw new Error(await response.text()); return response.json();}
function renderOverview(){
  const manifest=state.data.pipeline_manifest || {}; const totals=manifest.totals || {}; const gate=state.data.acceptance.gate || {};
  $('#scenarioCount').textContent=state.data.scenario_count;
  $('#gateBadge').textContent=gate.research_acceptance ? 'RESEARCH GATE · PASS' : 'RESEARCH GATE · PENDING';
  $('#overview').innerHTML=[
    ['SCENARIOS',state.data.scenario_count,'canonical worlds'],
    ['NATURAL ROLLOUTS',totals.trajectories ?? state.data.scenarios.reduce((n,s)=>n+s.pipeline.trajectory_count,0),'free-form model interaction'],
    ['OFFLINE SLICES',totals.instances ?? '—',`T1 ${totals.t1 ?? '—'} · T2 ${totals.t2 ?? '—'} · T3 ${totals.t3 ?? '—'}`],
    ['SOURCE MIX',Object.values(state.data.source_counts||{}).join(' / ')||'—','narrative-derived / synthetic-script']
  ].map(x=>`<div class="metric"><div class="label">${x[0]}</div><div class="value">${esc(x[1])}</div><div class="label">${esc(x[2])}</div></div>`).join('');
}
function renderScenarioList(){
  $('#scenarioList').innerHTML=state.data.scenarios.map(item=>`<button class="scenario-item ${item.scenario_id===state.scenarioId?'active':''}" data-scenario="${esc(item.scenario_id)}"><strong>${esc(item.scenario_id)}</strong><small>${esc(item.title)}</small></button>`).join('');
  document.querySelectorAll('[data-scenario]').forEach(el=>el.onclick=()=>selectScenario(el.dataset.scenario));
}
function renderHeader(){const s=state.detail.scenario, p=s.environment_agent?.persona||{}, summary=state.detail.summary;
  $('#scenarioHeader').innerHTML=`<div><div class="eyebrow">${esc(s.scenario_id)} · ${esc(s.mechanism||'social interaction')}</div><div class="scenario-title">${esc(s.title||s.scenario_id)}</div><div class="scenario-meta"><span class="tag">${esc(s.source?.type||'unknown source')}</span><span class="tag">${esc(s.construction_status?.initial_state||'unknown S0')}</span><span class="tag">${esc(s.max_turns||20)} turn horizon</span><span class="tag">${esc(summary.rollout_bundle)}</span></div><p class="scenario-copy">${esc(s.background||'')}</p></div><div class="persona-box"><div class="eyebrow">ENVIRONMENT PERSONA</div><strong>${esc(p.name||'—')}</strong><p>${esc(p.role||'')}<br><span class="muted">goal: ${esc(s.environment_agent?.explicit_goal||'—')}</span></p></div>`;
  $('#scenarioDoc').textContent=state.detail.documentation||'No paired Markdown'; $('#rolloutDialogues').textContent=state.detail.rollout_dialogues||'尚无完整 rollout 对话文档'; $('#taskReview').textContent=state.detail.task_review||'尚无 T1/T2/T3 人工抽查文档'; $('#rawScenario').textContent=JSON.stringify(s,null,2);
}
function renderSelect(){
  const rollouts=state.detail.rollouts;
  $('#trajectorySelect').innerHTML=rollouts.map(t=>{const p=t.policy_provenance||{};return `<option value="${esc(t.trajectory_id)}">${esc(p.model||t.policy_id)} · seed ${esc(p.sampling?.seed??'—')}</option>`}).join('');
  if(state.trajectoryId) $('#trajectorySelect').value=state.trajectoryId;
}
function stateRows(obj){return flat(obj).map(([key,value])=>`<div class="state-row"><span class="name">${esc(key)}</span><span class="bar"><i class="${key.includes('anger')||key.includes('hostility')||key.includes('risk')?'hot':key.includes('trust')||key.includes('hope')?'good':''}" style="width:${Math.max(0,Math.min(100,Number(value)*10))}%"></i></span><span>${esc(value)}</span></div>`).join('');}
function renderState(turn){const initial=turn?.state_after||state.detail.scenario.initial_state; const dynamics=turn?.dynamics_after||state.detail.scenario.initial_dynamics; $('#turnLabel').textContent=turn ? turn.turn_id : 'initial'; $('#statePanel').innerHTML=`<div class="subbox"><div class="subbox-label">state · 0—10</div>${stateRows(initial)}</div><div class="subbox" style="margin-top:10px"><div class="subbox-label">interaction dynamics</div>${stateRows(dynamics)}</div>`;}
function renderTriggerPanel(){
  const rules=state.detail.scenario.video_triggers||[], assets=state.detail.media_assets||[];
  $('#triggerPanel').innerHTML=rules.length?rules.map(rule=>{
    const asset=assets.find(item=>item.trigger_label===rule.trigger_id&&item.status==='generated');
    const media=asset?'<video class="talking-video" controls preload="metadata" src="'+esc(asset.url)+'"></video><small class="asset-note">'+esc(asset.utterance)+' · '+esc(asset.duration_seconds)+'s</small>':'<div class="media-pending">video pending</div>';
    const conditions=Object.entries(rule.conditions||{}).map(([key,value])=>esc(key)+' '+esc(value.operator)+' '+esc(value.threshold)).join(' · ');
    return '<div class="trigger-rule"><strong>'+esc(rule.trigger_id)+'</strong><p>'+esc(rule.trigger_mode)+' · cooldown '+esc(rule.cooldown_turns??0)+' turns<br>'+conditions+'</p>'+media+'</div>';
  }).join(''):'<div class="empty">No trigger rules</div>';
}
function renderTrajectory(){const trajectory=state.detail.rollouts.find(t=>t.trajectory_id===state.trajectoryId)||state.detail.rollouts[0]; if(!trajectory){$('#trajectory').innerHTML='<div class="empty">尚无自然模型轨迹。完成 scenario/S0 人工审核后，使用 rollout config 运行 pipeline。</div>';renderState(null);return;} $('#trajectory').innerHTML=trajectory.turns.map(turn=>{const deltas=flat(turn.numeric_state_delta); const media=(turn.media||[]).length; const expr=turn.observable_expression||{}; return `<article class="turn-card"><div class="turn-head"><strong>${esc(turn.turn_id)}</strong><span class="turn-action">${esc(turn.policy_action?.text)}</span></div><div class="turn-body"><p class="response">${esc(turn.environment_response)}</p><div class="turn-grid"><div class="subbox"><div class="subbox-label">model-appraised state transition</div>${deltas.filter(([,v])=>v!==0).slice(0,8).map(([k,v])=>`<span class="delta-chip ${deltaClass(v)}" style="display:inline-block;margin:2px">${esc(k)} ${deltaText(v)}</span>`).join('') || '<span class="muted">no numeric change</span>'}</div><div class="subbox"><div class="subbox-label">observable expression ${media?'· media spec':''}</div><div class="expr"><b>face</b> ${esc(expr.facial_expression||'—')}<br><b>gaze</b> ${esc(expr.gaze||'—')}<br><b>prosody</b> ${esc(expr.prosody||'—')}</div>${(turn.trigger_events||[]).map(e=>`<div class="trigger"><small>TRIGGERED · ${esc(e.trigger_id)}</small>state crossing</div>`).join('')}</div></div></div></article>`}).join(''); renderState(trajectory.turns[trajectory.turns.length-1]);}
async function selectScenario(id){state.scenarioId=id; renderScenarioList(); state.detail=await get(`/api/scenarios/${encodeURIComponent(id)}`); state.trajectoryId=state.detail.rollouts[0]?.trajectory_id||null; renderHeader(); renderSelect(); renderTriggerPanel(); renderTrajectory();}
async function boot(){try{state.data=await get('/api/summary'); renderOverview(); state.scenarioId=state.data.scenarios[0]?.scenario_id; renderScenarioList(); if(state.scenarioId) await selectScenario(state.scenarioId); $('#trajectorySelect').onchange=e=>{state.trajectoryId=e.target.value;renderTrajectory();};}catch(error){document.body.innerHTML=`<main class="main"><div class="panel error">无法加载 pipeline：${esc(error.message)}</div></main>`;}}
boot();
