'use strict';
const labFetch = window.socialfluxLabRequest;
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statuses = {planned:'待开展',running:'进行中',blocked:'受阻',review:'待复核',human_only:'仅需人工',completed:'已完成',archived:'已归档'};
const priorities = {P0:'P0 · 优先',P1:'P1 · 常规',P2:'P2 · 后续'};
const views = {
  overview:['实验总览','让每一次实验，都有据可循。','从研究问题到实验结果，在这里连接每一步。'],
  matrix:['实验矩阵','主实验、消融与 Gate2，一起追踪。','实验条件、目标规模、现有数据与下一步安排。'],
  paper:['论文表格','把方法和证据，整理成论文表格。','Gate 定义、验证方法、实际指标和各批次对照结果。'],
  human:['人工与 GT','独立判断，形成可追溯的 GT。','统一分配、盲答、私有证据核对和五维评分校准。'],
  plans:['实验计划','把下一步，变成具体的实验。','研究问题、执行方法、完成标准和结果，持续记录。'],
  results:['实时结果','每一个结果，都保留它的上下文。','按批次查看实际数据，追踪有效样本、失败与证据缺口。'],
  library:['报告与数据','研究的来路，都在这里。','检索实验报告、数据快照与历史记录，查看原始来源。']
};
const metricNames = {goal_achievement:'目标达成',state_adaptation:'状态适应',risk_management:'风险管理',recovery:'恢复',relationship_outcome:'关系结果',five_dimension_mean:'五维完整子集'};
const outcomeNames = {completed:'有效完成',failed:'失败',delegated_to_run:'已移交',unsupported_video_input:'不支持视频',completed_without_video_exposure:'未收到视频',source_unavailable:'来源不可用'};
const runStatuses = {running:'运行中',completed_with_recorded_outcomes:'槽位已归档',all_pairs_complete:'配对已补齐',request_budget_exhausted:'请求额度已用完',needs_repair:'待修复后续跑',stopped_health_gate:'已停止',historical_complete:'历史评分',paused_by_user:'已暂停',pending:'待完成'};
const evidenceStatuses={planned:'待开展',materials_ready:'已有材料 · 待独立评测',results_available:'已有分批结果',machine_evidence:'已有机器证据',unavailable:'证据暂缺',waiting_provider_authorization:'已准备，待外发授权',pilot_running:'真实调用试跑中',stopped_pilot_failed:'试跑失败，已停止',running:'真实补测进行中',finished:'机器执行完成，待人工判读',finished_with_failures:'执行结束，含失败',interrupted:'进程退出，未完成',stopped_diagnostics:'补测已暂停，故障排查中'};
const conditionNames={text_only:'text',text_video:'text+video',text_caption:'text+caption',original_s0:'原 S0',replaced_s0:'替换 S0',dynamic_state:'正常动态状态',fixed_s0_no_update_prompt:'始终 S0 · 无更新 prompt'};
let snapshot = null, busy = false, view = 'overview', planStatus = '', editing = null, source = null, sourceRequest = 0, toastTimer;

function dateText(value, withTime = false) {
  if (!value) return '—';
  const d = new Date(value.length === 10 ? value + 'T00:00:00+08:00' : value);
  if (!Number.isFinite(d.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',...(withTime?{hour:'2-digit',minute:'2-digit'}:{})}).format(d);
}
function badge(status){return `<span class="badge ${esc(status)}">${esc(statuses[status] || status)}</span>`;}
function empty(title, description = '试试其他关键词或筛选条件。'){return `<div class="empty"><strong>${esc(title)}</strong>${esc(description)}</div>`;}
function stat(label,value,unit,foot,icon){return `<article class="stat-card"><div class="stat-top">${esc(label)}<span class="stat-icon">${icon}</span></div><div class="stat-value">${esc(value ?? '—')}<small>${esc(unit)}</small></div><div class="stat-foot">${foot}</div></article>`;}
function runStatus(run){return run.reported_status === 'running' && !run.process_alive ? '运行状态待核实' : runStatuses[run.reported_status] || run.reported_status;}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3200);}
function download(content,name,type){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}
async function api(url,options){const response=await labFetch(url,{cache:'no-store',...options});let data;try{data=await response.json();}catch{throw Error('服务器没有返回有效数据，请稍后重试。');}if(!response.ok)throw Error(data.error||'请求失败（'+response.status+'）');return data;}
function table(headers,rows){return `<div class="table-wrap"><table><thead><tr>${headers.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(cell=>`<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
function sourceButton(path,label){return `<button type="button" class="source-link" data-source="${esc(path)}">${esc(label||path)} ↗</button>`;}
function csvDownload(rows,name){
  const quote=value=>{let s=String(value??'');if(/^\s*[=+\-@]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};
  download('\ufeff'+rows.map(row=>row.map(quote).join(',')).join('\r\n'),name,'text/csv;charset=utf-8');
}
function renderMatrix(){
  const matrix=snapshot.matrix;
  $('matrix-note').textContent=matrix?.note||'正在等待实验矩阵。';
  $('gate2-relation').textContent=matrix?.gate2_relation||'';
  $('research-matrix').innerHTML=['主实验','Gate2 核心验证','Gate2 补充消融'].map(group=>{
    const rows=(matrix?.experiments||[]).filter(r=>r.group===group);
    return `<section class="panel matrix-panel"><div class="section-heading"><h2>${esc(group)} <span class="badge">${rows.length} 项</span></h2>${group==='主实验'?'<a href="#results">查看分批结果 →</a>':''}</div>${table(['实验 / 条件','目标规模','实际数据 / 下一步','计划'],rows.map(r=>[
      `<strong>${esc(r.title)}</strong><small>${esc(r.conditions.map(c=>conditionNames[c]||c).join(' / '))}</small><details class="method-detail"><summary>验证什么 / 具体做法</summary><p>${esc(r.hypothesis)}</p><p>${esc(r.method)}</p>${r.measurement?`<p>指标：${esc(r.measurement)}</p>`:''}<p>要求：${esc(r.acceptance)}</p></details>`,
      esc(r.target),
      `<span class="badge">${esc(evidenceStatuses[r.evidence_status]||r.evidence_status)}</span><p>${esc(r.evidence_summary)}</p>${r.gate_id?`<small>正式状态：${esc(r.evidence.status||'pending')} · ${r.human_required?'人工签署：'+(r.evidence.human_attestation?'已签署':'待完成'):'协议不要求人工签署'}</small>`:''}<small>下一步：${esc(r.next_step)}</small>`,
      `${badge(r.plan_status)}<br><button class="text-button" data-edit="${esc(r.id)}">方法 / 记录 ↗</button>`
    ]))}</section>`;
  }).join('');
  const design=snapshot.environment_validation;
  if(design){
    const progress=r=>[
      r.progress?.counts?Object.entries(r.progress.counts).map(([k,v])=>`${outcomeNames[k]||k} ${v}`).join(' / '):'',
      r.progress?.expected!=null?`场景 ${r.progress.recorded||0}/${r.progress.expected}`:'',
      r.requests?`${r.requests.scope==='shared_suite'?'共享批次':r.requests.scope==='policy'?'策略调用':'实际调用'} ${r.requests.count}/${r.requests.limit}`:''
    ].filter(Boolean).join(' · ');
    $('research-matrix').insertAdjacentHTML('afterbegin',`<section class="panel matrix-panel"><div class="section-heading"><h2>六维实验设计 · ${esc(design.experiments.length)} 项</h2></div><p>${esc(design.note)}</p>${table(['实验','执行状态','已有证据 / 下一步'],design.experiments.map(r=>[
      `<strong>${esc(r.id)} · ${esc(r.name)}</strong><small>维度 ${esc(r.dimension)}</small>`,
      `${badge(r.status)}<small>${esc(progress(r))}</small>`,
      `${esc(r.evidence_summary||'')}<small>${esc(r.next_step||'')}</small>${(r.machine_subtasks||[]).map(s=>`<small>${badge(s.status)} ${esc(s.name)} · ${esc(s.evidence)}</small>`).join('')}`
    ]))}</section>`);
  }
  const files=matrix?.inventory||[];
  $('inventory-count').textContent=`展开 ${files.length} 个来源文件 · ${files.filter(f=>f.status!=='available').length} 个缺失或不可读`;
  $('data-inventory').innerHTML=table(['文件','关联实验','状态 / 大小 / SHA-256'],files.map(f=>[
    `<code>${esc(f.path)}</code>`,esc(f.experiments.join(' / ')),
    `${esc({available:'可读取',missing:'缺失',unreadable:'不可读取'}[f.status]||f.status)}${f.bytes!==null?` · ${(f.bytes/1024).toFixed(1)} KB`:''}<small class="source-hash">${esc(f.sha256||'—')}</small>`
  ]));
}
function selectedPaperTable(){return (snapshot?.paper_tables||[]).find(t=>t.id===$('paper-select').value);}
function renderPaperTable(){
  const selected=selectedPaperTable();
  $('paper-title').textContent=selected?.title||'暂无可用表格';
  $('paper-table').innerHTML=selected?table(selected.columns,selected.rows.map(row=>row.map(esc))):empty('暂无可用表格');
  $('paper-notes').innerHTML=(selected?.notes||[]).map(note=>`<p>${esc(note)}</p>`).join('');
  $('paper-sources').innerHTML=(selected?.sources||[]).map(path=>`<p class="report-path">${esc(path)}</p>`).join('');
}
function renderPaper(){
  const selected=$('paper-select').value;
  $('paper-select').replaceChildren(...(snapshot.paper_tables||[]).map(t=>new Option(t.title,t.id)));
  if((snapshot.paper_tables||[]).some(t=>t.id===selected))$('paper-select').value=selected;
  else if((snapshot.paper_tables||[]).some(t=>t.id==='gate2-results'))$('paper-select').value='gate2-results';
  renderPaperTable();
}

function navigate(){
  view=Object.hasOwn(views,location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
  document.querySelectorAll('[data-view]').forEach(a=>{a.classList.toggle('active',a.dataset.view===view);if(a.dataset.view===view)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  document.querySelectorAll('.view').forEach(section=>section.hidden=!snapshot||section.id!==view+'-view');
  const [crumb,title,subtitle]=views[view];$('crumb').textContent=crumb;$('page-title').textContent=title;$('page-subtitle').textContent=subtitle;
  document.title='SocialFlux · '+crumb;
}
function renderOverview(){
  const d=snapshot, r=d.records, live=d.live;
  const inventory=live?.dataset_counts;
  const datasetTable=id=>(d.paper_tables||[]).find(t=>t.id===id);
  for(const id of ['dataset-overview','offline-counts','t4hard-candidates']){
    const t=datasetTable(id);
    $(id).innerHTML=t?table(t.columns,t.rows.map(row=>row.map(esc)))+(id==='offline-counts'?`<div class="paper-notes">${t.notes.slice(1).map(note=>`<p>${esc(note)}</p>`).join('')}</div>`:''):empty('数据暂不可读','请查看页面提示并刷新。');
  }
  $('dataset-updated').textContent=inventory?'更新于 '+dateText(inventory.generated_at,true)+'（北京时间） · 随页面每 30 秒刷新':'';
  $('dataset-notes').innerHTML=(datasetTable('dataset-overview')?.notes||[]).slice(1).map(note=>`<p>${esc(note)}</p>`).join('');
  const pairing=datasetTable('t4-counts'),latest=pairing?.rows[0]?.[0];
  $('t4-counts-current').innerHTML=pairing?table(pairing.columns,pairing.rows.filter(row=>row[0]===latest).map(row=>row.map(esc))):empty('暂无可读批次');
  $('t4-counts-all').innerHTML=pairing?table(pairing.columns,pairing.rows.map(row=>row.map(esc))):'';
  $('t4-counts-note').textContent='上方为最近登记的续跑批次。有效配对需同批、同场景、同模型的两条件均完成，且视频实际送达。各批含继承结果，不跨批相加；失败槽位不等于失败场景。';
  $('export-dataset').disabled=!datasetTable('dataset-overview');
  $('export-t4-counts').disabled=!pairing;
  const todo=r.filter(x=>['planned','blocked','review','human_only'].includes(x.status)), running=r.filter(x=>x.status==='running');
  $('plan-count').textContent=r.filter(x=>!['completed','archived'].includes(x.status)).length;
  $('stats').innerHTML=[
    stat('实验计划',r.filter(x=>x.status!=='archived').length,'项',`<b>${running.length} 项进行中</b> · ${r.filter(x=>x.status==='completed').length} 项已完成`,'☷'),
    stat('待推进事项',todo.length,'项',`<b>${todo.filter(x=>x.priority==='P0').length} 项优先处理</b> · 按计划状态统计`,'↗'),
    stat('已收录实验文件',d.reports.length,'份','报告、数据快照与可追溯来源','▤'),
    stat(inventory?.offline?.release?'当前标注题库':'当前开发题库',inventory?.offline?.total??live?.offline?.item_count,'题',inventory?.offline?`普通 ${esc(inventory.offline.ordinary)} · Hard ${esc(inventory.offline.hard)} · 音视频配对 ${esc(inventory.offline.pairs??'待核对')}`:`人工标签 ${esc(live?.offline?.human_labeled??'—')} · 正式准入 ${esc(live?.offline?.formal_admitted??'—')}`,'◫')
  ].join('');
  $('next-plans').innerHTML=todo.slice(0,5).map(x=>`<button class="next-row" data-edit="${esc(x.id)}"><span class="priority-dot ${esc(x.priority)}"></span><div class="row-main"><div class="row-title">${esc(x.title)}</div><div class="row-sub"><span>${esc(x.category)}</span><span>·</span><span>${esc(x.owner||'待分配')}</span>${x.due_date?`<span>· ${esc(dateText(x.due_date))}</span>`:''}</div></div>${badge(x.status)}<span class="row-arrow">↗</span></button>`).join('')||empty(snapshot.public_snapshot?'登录后查看研究计划':'暂时没有待推进事项');
  $('recent-runs').innerHTML=(live?.t4_runs||[]).slice(0,3).map(run=>{
    const pct=run.planned_slots ? Math.min(100,100*(run.finished_slots||0)/run.planned_slots):0;
    return `<div class="mini-run"><div class="mini-run-heading"><div><h3>${esc(run.title)}</h3><p>${esc(run.id)}</p></div><span class="badge ${run.process_alive?'running':''}">${esc(runStatus(run))}</span></div><div class="progress" aria-hidden="true"><span style="width:${pct}%"></span></div><div class="progress-label"><span>已记录槽位（含失败／移交）</span><span>${esc(run.finished_slots??'—')} / ${esc(run.planned_slots??'—')}</span></div></div>`;
  }).join('')||empty('暂无可读批次',d.live_error||'等待批次生成摘要。');
  $('gate-summary').innerHTML=(live?.gates||[]).map((gate,i)=>`<div class="gate-step"><span class="gate-number">0${i+1}</span><div><h3>${esc(gate.id)} · ${esc(gate.name)}</h3><p>${esc(['来源与初始状态冻结','干预实验与有效性证据','唯一轨迹的质量与审计','独立人工审核与任务真值'][i])}</p></div><span class="badge">${gate.formal_status==='pending'?'待核验':esc(gate.formal_status)}</span></div>`).join('')||empty('Gate 状态暂不可读','稍后刷新重试。');
  $('recent-reports').innerHTML=d.reports.filter(x=>['MD','TXT'].includes(x.format)&&!x.archived).sort((a,b)=>b.date.localeCompare(a.date)||b.path.localeCompare(a.path)).slice(0,4).map(r=>`<button class="report-mini" data-source="${esc(r.path)}"><strong>${esc(r.title)}</strong><small>${esc(dateText(r.date))} &nbsp;·&nbsp; ${esc(r.category)}</small></button>`).join('')||empty('尚无报告');
}
function renderPlans(){
  const all=snapshot.records,search=$('plan-search').value.trim().toLowerCase(),category=$('plan-category').value,priority=$('plan-priority').value;
  $('plan-tabs').innerHTML=Object.entries({'':'全部',...statuses}).map(([s,label])=>`<button data-status="${s}" class="${s===planStatus?'active':''}" aria-pressed="${s===planStatus}">${label}<small>${all.filter(x=>!s||x.status===s).length}</small></button>`).join('');
  const rows=all.filter(r=>(!planStatus||r.status===planStatus)&&(!category||r.category===category)&&(!priority||r.priority===priority)&&(!search||[r.title,r.owner,r.hypothesis,r.method,r.notes,...r.sources].join(' ').toLowerCase().includes(search)));
  $('plan-list').innerHTML=rows.map(r=>`<article class="plan-card" data-record="${esc(r.id)}"><div class="plan-card-top"><span class="badge ${esc(r.priority)}">${esc(priorities[r.priority])}</span>${badge(r.status)}</div><h3>${esc(r.title)}</h3><p>${esc(r.hypothesis||'还没有填写研究问题。')}</p><div class="row-sub"><span>${esc(r.category)}</span>${r.metrics.length?`<span>· ${r.metrics.length} 个结果指标</span>`:''}</div><div class="plan-card-bottom"><span>${esc(r.owner||'待分配')}${r.due_date?' · '+esc(dateText(r.due_date)):''}</span><button class="text-button" data-edit="${esc(r.id)}">查看 / 编辑 ↗</button></div></article>`).join('')||empty(snapshot.public_snapshot?'登录后查看研究计划':'没有符合条件的实验');
}
function metric(value){
  if(!value?.n||value.mean===null||value.mean===undefined)return 'N/A<small>n=0</small>';
  return `${Number(value.mean).toFixed(2)}<small>n=${esc(value.n)}</small>`;
}
function renderResults(){
  const live=snapshot.live;
  if(!live){$('offline-summary').innerHTML='';$('gate2-results').innerHTML=empty('当前结果暂不可读',snapshot.live_error);$('run-results').innerHTML='';$('historical-gate2').innerHTML='';return;}
  const o=live.offline;
  const current=live.dataset_counts?.offline;
  $('score-note').textContent=live.score_note;
  $('offline-summary').innerHTML=[
    stat('当前题库场景',current?.scenarios??'—','个',`T1 / T2 / T3：${esc(current?.tasks?.T1?.total??'—')} / ${esc(current?.tasks?.T2?.total??'—')} / ${esc(current?.tasks?.T3?.total??'—')}`,'◫'),
    stat('文字 / 音视频配对',current?.pairs??'—','对',`素材齐全 ${esc(current?.media_coverage?.complete??'—')} · 缺失 ${esc(current?.media_coverage?.missing??'—')}`,'⇄'),
    stat('T2 待回放场景',o.t2_replay_pending_scenes,'个','公开证据核验与状态回放分列','↻'),
    stat('正式准入',o.formal_admitted,'题',`已有人工作答标签 ${esc(o.human_labeled)} 题`,'◇')
  ].join('');
  $('gate2-results').innerHTML=table(['实验','正式状态','已有证据 / 待办'],(live.gates[1]?.experiments||[]).map(e=>[
    `<strong>${esc(e.id)}</strong> ${esc(e.name)}`,
    `<span class="badge">${esc(e.status==='pending'?'待核验':e.status)}</span>`,
    e.raw_partial?`${esc(e.raw_partial.records)} 条已执行 · ${esc(e.raw_partial.screen_passed)} 条机器筛查通过`:
      e.review_items?`${esc(e.review_items)} 项人工包`:
      e.machine_record?.machine_reviewed_nodes!==undefined?`${esc(e.machine_record.machine_reviewed_nodes)} 个视频节点已检查 · 音频语义待人工`:
      e.machine_records?`${esc(e.machine_records)} 组机器记录`:e.evidence_present?'已有记录，待核验':'缺当前批次完整证据'
  ]));
  const ft=snapshot.paper_tables?.find(t=>t.id==='gate2-followup');
  const fc=snapshot.paper_tables?.find(t=>t.id==='gate2-followup-coverage');
  $('gate2-followup').innerHTML=ft?table(ft.columns,ft.rows.map(row=>row.map(esc)))+ft.notes.map(n=>`<p class="subtle">${esc(n)}</p>`).join('')+(fc?`<details><summary>执行覆盖与失败分母</summary>${table(fc.columns,fc.rows.map(row=>row.map(esc)))}${fc.notes.map(n=>`<p class="subtle">${esc(n)}</p>`).join('')}</details>`:''):empty('补测尚未开始');
  const history=live.historical_gate2;
  $('historical-gate2').innerHTML=history?`<details class="inventory-details"><summary>历史 Gate2 · ${esc(history.date||'旧批次')}（独立保留）</summary><p class="subtle">${esc(history.note)} · ${esc(history.status||'状态待核验')}</p>${table(['检查','历史记录'],Object.entries(history.checks||{}).map(([key,value])=>[esc(key),esc(JSON.stringify(value))]))}</details>`:'';
  $('run-results').innerHTML=live.t4_runs.map(run=>{
    const rows=[],pairs=[],counts=[];
    for(const [model,value] of Object.entries(run.models)){
      for(const [condition,c] of Object.entries(value.conditions)){
        rows.push([esc(model),condition==='text_only'?'文字':'文字＋媒体',...Object.keys(metricNames).map(k=>metric(c.metrics[k]))]);
      }
      pairs.push([esc(model),...Object.keys(metricNames).map(k=>metric(value.paired_differences[k])+(value.paired_differences[k]?.bootstrap_ci95?`<small>95% CI [${value.paired_differences[k].bootstrap_ci95.map(n=>Number(n).toFixed(2)).join(', ')}]</small>`:''))]);
      counts.push(`<span>${esc(model)}：${Object.entries(value.status_counts).map(([s,n])=>`${esc(outcomeNames[s]||s)} ${esc(n)}`).join(' / ')} · 有效配对 ${esc(value.matched_scenarios)}</span>`);
    }
    return `<section class="panel run-panel"><div class="section-heading"><h2>${esc(run.title)}</h2><span class="badge ${run.process_alive?'running':''}">${esc(runStatus(run))}</span></div><p class="run-note">${esc(run.note)}<br>已记录槽位 ${esc(run.finished_slots??'—')} / ${esc(run.planned_slots??'—')} · 更新 ${esc(dateText(run.updated_at,true))}</p><div class="run-info">${counts.join('')}</div>${rows.length?table(['模型','条件',...Object.values(metricNames)],rows):empty('本批次暂未产生指标','等待实际评测摘要。')}<details><summary>查看同批次有效配对：媒体 − 文字</summary>${table(['模型',...Object.values(metricNames)],pairs)}</details></section>`;
  }).join('')||empty('暂无 T4 批次');
}
function renderLibrary(){
  const search=$('report-search').value.trim().toLowerCase(),category=$('report-category').value,format=$('report-format').value;
  const rows=snapshot.reports.filter(r=>(!category||r.category===category)&&(!format||r.format===format)&&(!search||[r.title,r.excerpt,r.path].join(' ').toLowerCase().includes(search))).sort((a,b)=>b.date.localeCompare(a.date)||b.path.localeCompare(a.path));
  $('scope').textContent=snapshot.scope;
  $('report-count').textContent=`显示 ${rows.length} / ${snapshot.reports.length} 个文件 · 报告日期为文件名中的实验日期；历史文件保留原批次。`;
  $('report-list').innerHTML=rows.map(r=>`<article class="report-entry"><div class="file-icon">${esc(r.format)}</div><div class="row-main"><h3>${esc(r.title)}</h3><div class="row-sub"><span>${esc(dateText(r.date))}</span><span>· ${esc(r.category)}</span>${r.archived?'<span class="badge archived">历史归档</span>':''}<span>· ${(r.bytes/1024).toFixed(1)} KB</span></div>${r.excerpt?`<p>${esc(r.excerpt)}</p>`:''}<p class="report-path">${esc(r.path)}</p></div><button class="text-button" data-source="${esc(r.path)}">查看来源 ↗</button></article>`).join('')||empty('没有符合条件的报告');
}
function renderHuman(){
  const h=snapshot.human_annotation||{};
  const cohorts=h.dataset_cohorts||[];
  $('human-summary').innerHTML=[stat('全部版本已导入',h.total_sessions??h.sessions??0,'份',`当前版本 ${h.sessions||0} 份 · 当前版本最终提交 ${h.submitted||0}`,'◇'),stat('当前版本共识 GT',h.gt_consensus||0,'题',`待裁决 ${h.gt_disputed||0}`,'✓'),stat('T4 固定抽样',50,'场景','完整轨迹池 182 / 总体 200','▥'),stat('Claude 对照已备',h.claude_available||0,'/ 50',`失败 ${h.claude_status?.failed||0} · 待完成 ${h.claude_status?.pending||0} · 详情见论文覆盖表`,'↔')].join('');
  $('human-release-note').textContent=`下方 GT 和环境核对统计使用版本：${h.release||'待准备'}。其他版本的记录保留在本表。`;
  $('human-release-cohorts').innerHTML=cohorts.length?table(['材料版本','统计范围','已导入','未最终提交','最终提交'],cohorts.map(c=>[esc(c.release),c.current?'当前版本':c.registered_candidate?'候选版本':'历史版本',esc(c.sessions),esc(c.sessions-c.submitted),esc(c.submitted)])):empty('暂无已登记版本');
  const t=h.tables?.find(t=>t.id==='human-t4-calibration');
  $('human-comparison').innerHTML=t?table(t.columns,t.rows.map(row=>row.map(esc))):empty('等待冻结标注批次');
  const gt=h.tables?.find(t=>t.id==='gate2-human-coverage');
  $('gate2-human-coverage').innerHTML=gt?table(gt.columns,gt.rows.map(row=>row.map(esc))):empty('环境核对包待准备');
  $('human-status').textContent=(h.errors||[]).join('；');
  const old=$('adjudication-item').value;
  $('adjudication-item').replaceChildren(...(h.disputes||[]).map(x=>new Option(x.instance_id,x.instance_id)));
  if((h.disputes||[]).some(x=>x.instance_id===old))$('adjudication-item').value=old;
  $('human-adjudication').hidden=!(h.disputes||[]).length;renderAdjudication();
}
function renderAdjudication(){
  const row=snapshot?.human_annotation?.disputes?.find(x=>x.instance_id===$('adjudication-item').value);if(!row)return;
  $('adjudication-evidence').innerHTML=`<p>${esc(row.question)}</p>`+table(['审核人','答案','质量','依据'],Object.entries(row.judgments).map(([who,r])=>[esc(who),esc(r.answer),esc(r.decision),esc(r.rationale)]));
  $('adjudication-answer').replaceChildren(new Option('请选择',''),...Object.entries(row.options).map(([key,text])=>new Option(key+' · '+text,key)),new Option('剔除题目','reject'));
}
$('adjudication-item').onchange=renderAdjudication;
$('human-adjudication-form').onsubmit=async e=>{
  e.preventDefault();const row=snapshot.human_annotation.disputes.find(x=>x.instance_id===$('adjudication-item').value),answer=$('adjudication-answer').value;if(!row||!answer)return;
  try{await api('/api/lab/human-adjudicate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({instance_id:row.instance_id,item_sha256:row.item_sha256,reviewer:$('adjudicator').value,rationale:$('adjudication-rationale').value,answer:answer==='reject'?null:answer,decision:answer==='reject'?'reject':'usable',human_attestation:$('adjudication-attest').checked})});$('adjudication-rationale').value='';$('adjudication-attest').checked=false;await refresh();$('human-status').textContent='裁决已保存，原始分歧仍保留。';}catch(error){$('human-status').textContent=error.message;}
};
$('human-import').onchange=async e=>{
  const files=Array.from(e.target.files||[]);let count=0;
  try{for(const file of files){if(file.size>1000000)throw new Error('单份回执超过 1 MB');const value=JSON.parse(await file.text());const response=await labFetch('/api/lab/human-import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});const result=await response.json();if(!response.ok)throw new Error(result.error);count++;}await refresh();$('human-status').textContent=`已导入 ${count} 份回执，按回执和标注人去重。`;}
  catch(error){$('human-status').textContent=`已导入 ${count} 份；${error.message}`;}finally{e.target.value='';}
};
function render(){renderHuman();renderOverview();renderMatrix();renderPaper();renderPlans();renderResults();renderLibrary();navigate();}
async function refresh(){
  if(busy)return;busy=true;$('refresh').disabled=true;
  try{
    snapshot=await api('/api/lab');
    if(!$('edit-category').options.length){
      for(const id of ['plan-category','report-category','edit-category'])for(const c of snapshot.categories)$(id).add(new Option(c,c));
      for(const [k,v] of Object.entries(statuses))$('edit-status').add(new Option(v,k));
    }
    $('loading').hidden=true;
    const errors=[snapshot.public_snapshot?'当前为已发布的汇总快照。实时数据、个人记录和保存操作需登录研究服务器。':null,snapshot.live_error,...(snapshot.catalog_errors.length?['部分报告不可读，目录列表可能不完整。']:[]),...((snapshot.live?.read_errors?.length||snapshot.matrix?.read_errors?.length)?['部分运行文件暂不可读，数据可能尚未完整。']:[])].filter(Boolean);
    $('error').textContent=errors.join(' ');$('error').hidden=!errors.length;
    $('sync-status').textContent=(snapshot.public_snapshot?'已发布汇总 · ':'已同步 ')+new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(snapshot.generated_at));
    render();
  }catch(error){$('error').textContent=(snapshot?'刷新失败，当前仍显示上次数据。':'')+error.message;$('error').hidden=false;$('loading').hidden=true;$('sync-status').textContent='连接失败';}
  finally{busy=false;$('refresh').disabled=false;}
}
async function openRecord(id){
  if(!snapshot){toast('请先等待实验数据读取完成。');return;}
  editing=id?snapshot.records.find(x=>x.id===id):null;
  if(id&&!editing){toast('找不到实验记录，请刷新后重试。');return;}
  const form=$('record-form');form.reset();
  $('record-dialog-title').textContent=editing?'实验记录':'新建实验';
  $('record-provenance').textContent=editing?`${editing.origin==='research_matrix_20261021'?'本轮整合的研究计划':editing.origin==='report_proposal'?'由项目文档整理的初始计划':'手动实验记录'} · v${editing.revision} · 更新 ${dateText(editing.updated_at,true)}`:'填写研究问题和方法，实验结果可以随时补充。';
  for(const name of ['title','category','status','priority','owner','due_date','hypothesis','method','acceptance','notes'])form.elements[name].value=editing?.[name]??({category:'其他',status:'planned',priority:'P1'}[name]||'');
  form.elements.sources_text.value=(editing?.sources||[]).join('\n');
  form.elements.metrics_text.value=(editing?.metrics||[]).map(m=>[m.name,m.value,m.unit,m.n].join(' | ')).join('\n');
  $('record-sources').innerHTML=(editing?.sources||[]).filter(s=>s.startsWith('reports/experiments/')||s==='DESIGN_CONTRACT.md').map(s=>sourceButton(s)).join('');
  $('save-error').textContent='';$('history-details').hidden=!editing;$('history-details').open=false;$('record-history').textContent='读取修改记录…';
  $('record-dialog').showModal();
  if(editing){
    const identity=editing.id;
    try{const {events}=await api('/api/lab/'+encodeURIComponent(identity)+'/history');if(editing?.id!==identity)return;
      $('record-history').innerHTML=events.map(e=>`<div class="history-item">${esc(dateText(e.at,true))} · ${e.action==='created'?'创建':'更新'}至 v${esc(e.after.revision)} · ${esc(statuses[e.after.status])}<br>${esc(e.after.notes||'未填写进展备注')}</div>`).join('')||'这是由项目文档整理的初始计划，尚无手动修改。';
    }catch(e){$('record-history').textContent=e.message;}
  }
}
$('record-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;const payload={};
  for(const name of ['title','category','status','priority','owner','due_date','hypothesis','method','acceptance','notes'])payload[name]=form.elements[name].value;
  payload.sources=form.elements.sources_text.value.split('\n').map(s=>s.trim()).filter(Boolean);
  const lines=form.elements.metrics_text.value.split('\n').filter(s=>s.trim());
  if(lines.some(line=>line.split('|').length<2||line.split('|').length>4)){$('save-error').textContent='指标格式：名称 | 数值 | 单位 | 有效样本数 n（后两项可留空）';return;}
  payload.metrics=lines.map(line=>{const [name,value,unit='',n='']=line.split('|').map(s=>s.trim());return {name,value,unit,n};});
  if(editing){payload.id=editing.id;payload.revision=editing.revision;}
  $('save-record').disabled=true;$('save-error').textContent='';
  try{const saved=await api('/api/lab/records',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});snapshot.records=snapshot.records.filter(x=>x.id!==saved.id);snapshot.records.push(saved);snapshot.records.sort((a,b)=>a.priority.localeCompare(b.priority)||a.created_at.localeCompare(b.created_at));render();$('record-dialog').close();toast('实验记录已保存到服务器');}
  catch(error){$('save-error').textContent=error.message;}
  finally{$('save-record').disabled=false;}
});
async function openSource(path){
  const request=++sourceRequest;source=null;$('source-title').textContent=path.split('/').pop();$('source-meta').textContent=path;$('source-content').textContent='正在读取来源…';$('download-source').disabled=true;
  if(!$('source-dialog').open)$('source-dialog').showModal();
  try{const data=await api('/api/lab/source?path='+encodeURIComponent(path));if(request!==sourceRequest)return;
    if(data.error)throw Error(data.error);source=data;
    $('source-meta').textContent=data.path+' · '+(data.bytes/1024).toFixed(1)+' KB\nSHA-256: '+data.sha256;
    const pre=document.createElement('pre');pre.textContent=data.content;$('source-content').replaceChildren(pre);$('download-source').disabled=false;
  }catch(error){if(request===sourceRequest)$('source-content').textContent=error.message;}
}
document.addEventListener('click',event=>{
  const edit=event.target.closest('[data-edit]'),doc=event.target.closest('[data-source]'),filter=event.target.closest('[data-status]'),close=event.target.closest('.close');
  if(edit)openRecord(edit.dataset.edit);else if(doc)openSource(doc.dataset.source);else if(filter){planStatus=filter.dataset.status;renderPlans();}else if(close)close.closest('dialog').close();
});
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
$('create').onclick=()=>openRecord();
$('refresh').onclick=refresh;
for(const [button,identity] of [['export-dataset','dataset-overview'],['export-t4-counts','t4-counts']]){
  $(button).onclick=()=>{const t=snapshot?.paper_tables?.find(t=>t.id===identity);if(t)download(t.exports.csv,identity+'.csv','text/csv;charset=utf-8');};
}
for(const id of ['plan-search','plan-category','plan-priority'])$(id).addEventListener(id.endsWith('search')?'input':'change',()=>snapshot&&renderPlans());
for(const id of ['report-search','report-category','report-format'])$(id).addEventListener(id.endsWith('search')?'input':'change',()=>snapshot&&renderLibrary());
$('download-source').onclick=()=>source&&download(source.content,source.path.split('/').pop(),'text/plain;charset=utf-8');
$('export-all').onclick=()=>snapshot&&download(JSON.stringify(snapshot,null,2),'socialflux-lab-'+new Date().toISOString().slice(0,10)+'.json','application/json');
$('export-plans').onclick=()=>{
  if(!snapshot)return;
  const rows=[['ID','实验名称','分类','状态','优先级','负责人','计划日期','研究问题','方法','完成标准','进展结论','结果指标','来源','更新时间'],...snapshot.records.map(r=>[r.id,r.title,r.category,statuses[r.status],r.priority,r.owner,r.due_date,r.hypothesis,r.method,r.acceptance,r.notes,JSON.stringify(r.metrics),r.sources.join('\n'),r.updated_at])];
  csvDownload(rows,'socialflux-experiment-plans.csv');
};
$('export-matrix').onclick=()=>snapshot&&csvDownload([['ID','实验','分组','条件','目标规模','计划状态','数据状态','实际证据','下一步','来源'],...snapshot.matrix.experiments.map(r=>[r.id,r.title,r.group,r.conditions.join(' / '),r.target,statuses[r.plan_status],evidenceStatuses[r.evidence_status],r.evidence_summary,r.next_step,r.sources.join('\n')])],'socialflux-experiment-matrix.csv');
$('export-inventory').onclick=()=>snapshot&&csvDownload([['文件','状态','字节','SHA-256','关联实验'],...snapshot.matrix.inventory.map(f=>[f.path,f.status,f.bytes,f.sha256,f.experiments.join(' / ')])],'socialflux-data-inventory.csv');
$('paper-select').onchange=renderPaperTable;
for(const [format,extension,mime] of [['csv','csv','text/csv'],['markdown','md','text/markdown'],['latex','tex','text/x-tex']]){
  $('paper-'+format).onclick=()=>{const t=selectedPaperTable();if(t)download(t.exports[format],t.id+'.'+extension,mime+';charset=utf-8');};
}
window.addEventListener('hashchange',navigate);
window.addEventListener('beforeunload',event=>{
  if($('record-dialog').open){event.preventDefault();event.returnValue='';}
});
window.addEventListener('socialflux-login',refresh);navigate();refresh();setInterval(()=>{if(!document.hidden&&!$('record-dialog').open&&!$('source-dialog').open)refresh();},30000);
