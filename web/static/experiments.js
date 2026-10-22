'use strict';
const $=id=>document.getElementById(id);
const e=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={goal_achievement:'目标达成',state_adaptation:'状态适应',risk_management:'风险管理',recovery:'恢复',relationship_outcome:'关系结果',five_dimension_mean:'五维完整子集均分'};
const models={gpt:'GPT',claude:'Claude',deepseek:'DeepSeek',qwen:'Qwen',gpt_source:'原 GPT 策略轨迹'};
const statuses={queued_after_recovery:'待传输恢复结束后启动',preparing_video_frames:'准备视频帧',probing_model_media_inputs:'核验媒体输入',running:'运行中',machine_checks_in_progress:'本次机器检查进行中',machine_checks_executed:'本次机器检查已执行（通过与失败分列）',completed_with_recorded_outcomes:'槽位已归档（含失败／移交）',stopped_health_gate:'已按运行条件停止',historical_complete:'历史评分',paused_by_user:'按此前要求暂停',pending:'待完成'};
const outcomeLabels={completed:'轨迹与评分完成',failed:'失败',delegated_to_run:'移交其他批次',unsupported_video_input:'不支持视频',completed_without_video_exposure:'完成但未收到视频',source_unavailable:'来源不可用'};
let snapshot=null,busy=false;
function table(headers,rows){return '<div class="table-wrap"><table><thead><tr>'+headers.map(x=>'<th>'+e(x)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';}
function metric(v){if(!v||!v.n||v.mean===null||v.mean===undefined)return 'N/A <small>n=0</small>';return Number(v.mean).toFixed(2)+' <small>n='+e(v.n)+'</small>';}
function diff(v){return metric(v)+(v?.bootstrap_ci95?'<small>95% 区间 ['+v.bootstrap_ci95.map(n=>Number(n).toFixed(2)).join(', ')+']</small>':'');}
function renderRun(run){
 const rows=[],pairs=[];
 for(const [model,value] of Object.entries(run.models)){
  for(const [condition,c] of Object.entries(value.conditions))rows.push([e(models[model]||model),condition==='text_only'?'文字':'文字＋视频条件',...Object.keys(labels).map(k=>metric(c.metrics[k]))]);
  pairs.push([e(models[model]||model),...Object.keys(labels).map(k=>diff(value.paired_differences[k]))]);
 }
 const live=run.reported_status==='running'?(run.process_alive?' · 已核对进程存活':' · 未检测到匹配进程，运行状态待核实'):'';
 const counts=Object.entries(run.models).map(([m,v])=>'<p class="muted">'+e(models[m]||m)+'：'+Object.entries(v.status_counts).map(([s,n])=>e(outcomeLabels[s]||s)+' '+e(n)).join('，')+'；完整配对 '+e(v.matched_scenarios)+'</p>').join('');
 return '<article data-run="'+e(run.id)+'"><h3>'+e(run.title)+'</h3><p class="status">'+e(statuses[run.reported_status]||run.reported_status)+e(live)+(run.kind==='transport_recovery'?' · 已处理恢复项 ':' · 已记录槽位 ')+e(run.finished_slots)+' / '+e(run.planned_slots)+'</p><p class="muted">'+e(run.note)+' 更新时间：'+e(run.updated_at)+'</p>'+counts+table(['被测策略','条件',...Object.values(labels)],rows)+'<details><summary>同批次完整配对：视频条件 − 文字</summary>'+table(['被测策略',...Object.values(labels)],pairs)+'</details></article>';
}
async function refresh(){
 if(busy)return;busy=true;
 try{
  const response=await fetch('/api/experiment-status',{cache:'no-store'});if(!response.ok)throw Error('读取失败：'+response.status);
  const d=await response.json();snapshot=d;
  $('updated').textContent='读取时间：'+d.generated_at+' · 每 30 秒刷新；机器结果与人工结论分开记录';
  $('gates').innerHTML=d.gates.map(g=>'<article><h2>'+e(g.id)+' · '+e(g.name)+'</h2><p>'+e(g.purpose)+'</p><p class="muted">'+e(g.review_setting)+'</p><p class="status">正式状态：待人工／证据核验</p>'+(g.machine_decisions?'<p>模型审核 '+e(g.machine_reviewed)+' 条：通过 '+e(g.machine_decisions.approve||0)+'，未通过 '+e(g.machine_decisions.reject||0)+'；另 '+e(g.missing_sources)+' 个场景无可审正文。</p>':'')+
    (g.machine_audit?.scenario_count?'<p>场景结构检查 '+e(g.machine_audit.schema_passed)+' / '+e(g.machine_audit.scenario_count)+' 通过。</p>':'')+
    (g.independent_audit?.reviewed?'<p>第二模型独立复核 '+e(g.independent_audit.reviewed)+' / '+e(g.independent_audit.expected_audit_count)+'；与主审分歧 '+e(g.independent_audit.disagreements?.length||0)+' 条。</p>':'')+
    (g.oracle_check?.authored_items?'<p>上帝视角候选 '+e(g.oracle_check.authored_items)+' / 300；独立私有证据核验 '+e(g.oracle_check.independently_checked_items)+'；公开盲答 '+e(g.oracle_check.public_blind_checked_items)+'。</p>':'')+'</article>').join('');
  const c=d.rollouts.counts;
  $('rollouts').textContent=`${d.rollouts.expected} 个场景：完整轨迹 ${c.completed}，失败 ${c.failed}；当前有正文 ${c.readable}，历史正文 ${c.history_readable}。失败保留在原始分母中。`;
  const g=d.gates[1];
  $('gate2Status').textContent=`Gate2 作业：${statuses[g.run_status]||g.run_status}；来源合同状态：${g.source_contract_status}。原始干预日志 ${g.raw_intervention_records} 条，其中执行错误 ${g.raw_execution_errors} 条；部分日志不等于完整有效性结论。`;
  if(g.run_status==='machine_checks_executed'&&!g.machine_evidence_ready) $('gate2Status').textContent+=' 本轮机器证据尚未达到准入要求。';
  $('gate2Table').innerHTML=table(['实验','当前准入状态','机器结果／人工包'],g.experiments.map(x=>[e(x.id+' '+x.name),e(x.status==='pending'?'待人工／证据核验':x.status),
    x.id==='E8'&&x.machine_record?.machine_reviewed_nodes!==undefined?e('视频帧检查 '+x.machine_record.machine_reviewed_nodes+' / '+x.machine_record.matched_node_count+'；可见线索全部通过 '+x.machine_record.visual_passed_nodes+'；音频语义待人工'):
    x.raw_partial?e(x.raw_partial.records+' 条已执行，机器筛查 '+x.raw_partial.screen_passed+' 条通过；人工仍待确认'):
    x.id==='E6'&&x.machine_records?e(x.machine_records+' 组双模型回放；结果 '+JSON.stringify(x.machine_record)):
    x.review_items?e(x.review_items+' 项人工包，尚未签署'):e(x.evidence_present?'已有记录，待核验':'缺当前批次完整证据')]));
  const o=d.offline;
  $('offline').innerHTML='<p>'+e(o.scenario_count)+' 个场景，'+e(o.item_count)+' 题；T1 / T2 / T3 各 '+e(o.tasks?.T1)+' 题；每场景每任务 2 题。</p><p>当前题面 API 盲试答覆盖 '+e(o.blind_reviewed_items)+' 题；仍有机器问题标记 '+e(o.machine_flagged_ids?.length||0)+' 题。文字／视频帧配对 '+e(o.modality_pairs)+' 对。</p><p class="status">待补受控状态回放的 T2：'+e(o.t2_replay_pending_scenes)+' 个场景；已有人工真值 '+e(o.human_labeled)+' 题，正式准入 '+e(o.formal_admitted)+' 题。</p><p class="muted">'+e(o.interpretation)+'</p>'+(o.machine_flagged_ids?.length?'<p>待审题号：'+e(o.machine_flagged_ids.join('、'))+'</p>':'');
  if(o.oracle_progress?.authored_items) $('offline').innerHTML+='<p>本次上帝视角批次：已产出 '+e(o.oracle_progress.authored_items)+'，独立核验 '+e(o.oracle_progress.independently_checked_items)+'，公开盲答 '+e(o.oracle_progress.public_blind_checked_items)+'；机器争议 '+e(o.oracle_progress.machine_concern_ids?.length||0)+' 题。</p><p><a href="/offline-annotation">进入人类盲答与 GT 审核</a></p>';
  $('scoreNote').textContent=d.score_note;
  $('t4').innerHTML=d.t4_runs.map((r,i)=>i===0?renderRun(r):'<details><summary>'+e(r.title)+'</summary>'+renderRun(r)+'</details>').join('');
  $('historyNote').textContent=d.historical_gate2.note+' 正式状态：'+d.historical_gate2.status;
  $('history').innerHTML=table(['历史实验','记录值'],Object.entries(d.historical_gate2.checks).map(([k,v])=>[e(k),e(JSON.stringify(v))]));
  $('sources').textContent=d.sources.map(s=>s.path+'\n'+s.sha256).join('\n\n');
  $('error').textContent=d.read_errors.length?'部分运行文件正在写入或不可读，下次刷新将重试；请以对应运行记录为准。':'';
 }catch(err){$('error').textContent=err.message;}finally{busy=false;}
}
$('refresh').onclick=refresh;
$('download').onclick=()=>{if(!snapshot)return;const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(snapshot,null,2)],{type:'application/json'}));a.download='socialflux-experiment-status.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
refresh();setInterval(refresh,30000);
