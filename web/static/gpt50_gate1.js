(function(){
"use strict";
var STORAGE_KEY="socialflux.gpt50.gate1.drafts.v1";
var data=null,index=0,detail=null;
var attestations=[
 ["variables_relevant","状态变量确实与本场景相关"],
 ["values_justified","Initial state 数值有充分情境依据"],
 ["no_policy_effect_baked_in","初始状态没有预写某种策略的效果"],
 ["initial_triggers_inactive","三个 trigger 在初始配置下均未激活"],
 ["multiple_future_paths_possible","存在多种合理走向，没有唯一脚本"],
 ["shared_across_models_and_seeds","冻结配置可供不同模型公平比较"]
];
var dimensions=[
 ["social_plausibility","社会情境可信度"],
 ["character_coherence","人物与动机一致性"],
 ["tradeoff_quality","真实取舍质量"],
 ["history_necessity","历史信息必要性"],
 ["interaction_richness","互动与策略空间"],
 ["t1_t4_suitability","T1–T4 任务适用性"]
];
var rolloutDimensions=[
 ["effective_dialogue","对话是否有效推进"],
 ["persona_coherence","角色与 persona 一致"],
 ["progression","情节与关系有真实进展"],
 ["naturalness","表达自然、非模板化"]
];
function esc(v){return String(v==null?"":v).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function store(){try{return JSON.parse(localStorage.getItem(STORAGE_KEY)||'{"reviewer":"","records":{}}');}catch(e){return{reviewer:"",records:{}};}}
function persist(v){localStorage.setItem(STORAGE_KEY,JSON.stringify(v));}
async function get(url){var r=await fetch(url);if(!r.ok)throw new Error(await r.text());return r.json();}
function current(){return data.candidates[index];}
function key(id){return"gpt50_gate1:"+id;}
function record(){var c=current(),s=store();return s.records[key(c.scenario_id)]||{};}
function reviewed(r,c){return r.decision&&r.decision!=="pending"&&r.scenario_sha256===c.scenario_sha256;}
function drawQueue(){
 if(!data)return;
 var query=document.getElementById("search").value.trim().toLowerCase(),s=store();
 var visible=data.candidates.map(function(c,i){return{c:c,i:i};}).filter(function(v){return !query||[v.c.scenario_id,v.c.title,v.c.mechanism,v.c.relationship_structure].join(" ").toLowerCase().indexOf(query)>=0;});
 document.getElementById("queue").innerHTML=visible.map(function(v){
  var r=s.records[key(v.c.scenario_id)]||{},state=r.scenario_sha256&&r.scenario_sha256!==v.c.scenario_sha256?"stale":reviewed(r,v.c)?"done":"";
  var rollout=v.c.rollout||{status:"pending"},gate2=v.c.gate2||{status:"not_sampled"};
  return'<button class="item '+(v.i===index?'active':'')+'" data-i="'+v.i+'"><span class="dot '+state+'"></span><strong>'+esc(v.c.scenario_id)+' · '+esc(v.c.title)+'</strong><small>'+esc(v.c.schema_status)+' · '+esc(r.decision||"pending")+' · rollout '+esc(rollout.status)+(rollout.turn_count!=null?' ('+esc(rollout.turn_count)+' turns)':'')+' · Gate2 '+esc(gate2.status)+'</small></button>';
 }).join("");
 document.querySelectorAll("[data-i]").forEach(function(x){x.onclick=function(){index=Number(this.dataset.i);loadCurrent();};});
 var done=data.candidates.filter(function(c){return reviewed(s.records[key(c.scenario_id)]||{},c);}).length;
 document.getElementById("progress").textContent=done+" / "+data.scenario_count+" 已人工判定";
}
function rows(value,prefix){
 var out=[];
 function walk(v,p){
  if(v&&typeof v==="object"&&!Array.isArray(v)){Object.keys(v).forEach(function(k){walk(v[k],p?p+"."+k:k);});}
  else out.push("<tr><td>"+esc(p)+"</td><td>"+esc(Array.isArray(v)?v.join("；"):v)+"</td></tr>");
 }
 walk(value,prefix||"");return out.join("");
}
function list(items){return'<ul class="list">'+(items||[]).map(function(x){return"<li>"+esc(x)+"</li>";}).join("")+"</ul>";}
function personaHtml(title,p,goal,hidden,extraClass){
 p=p||{};
 var traits=(p.temperament||[]).join("、")||"未说明";
 var values=(p.core_values||[]).join("、")||"未说明";
 var boundaries=(p.boundaries||[]).map(function(x){return"<li>"+esc(x)+"</li>";}).join("");
 return'<article class="persona-card '+esc(extraClass||"")+'"><h4>'+esc(title)+'：'+esc(p.name||"未命名")+'</h4><p><b>'+esc(p.name||"该角色")+'</b>的身份是“'+esc(p.role||"未说明")+'”。当前明确目标是：'+esc(goal||"未说明")+'</p><p>这个人看重'+esc(values)+'，性格倾向为'+esc(traits)+'。沟通时通常'+esc(p.communication_style||"未说明")+'；做决定时'+esc(p.decision_style||"未说明")+'；面对冲突时'+esc(p.conflict_style||"未说明")+'。</p>'+(boundaries?'<p class="label">不会越过的边界</p><ul class="list">'+boundaries+'</ul>':'')+(hidden?'<div class="private-note"><b>作者侧隐藏意图（被测模型不可见）</b><p>'+esc(hidden)+'</p></div>':'')+'</article>';
}
function rolloutHtml(rollout,evaluatedName,environmentName){
 rollout=rollout||{};
 var turns=rollout.turns||[],attempts=rollout.attempts||[],recent=attempts.length?attempts[attempts.length-1]:null;
 if(!turns.length){
  return'<section class="panel"><h3>GPT rollout · 暂无对话</h3><p class="warning">'+esc(rollout.quality_warning||"当前场景还没有形成可展示的 rollout。")+'</p>'+(recent?'<p>最近一次尝试为 <b>'+esc(recent.status)+'</b>。'+esc(recent.error||"")+'</p>':'')+'<details><summary>技术尝试记录</summary><div class="raw">'+esc(JSON.stringify(attempts,null,2))+'</div></details></section>';
 }
 var accepted=rollout.gate3_candidate===true;
 var review=rollout.machine_review||{};
 var diagnosis=(review.hard_reject_reasons||[]).concat(review.false_checks||[]);
 var label=accepted?"机器预检通过":rollout.status==="machine_rejected"?"机器拒绝但保留供审查":rollout.status==="short_trajectory"?"短轨迹":"需要人工诊断";
 var warning=rollout.quality_warning?'<p class="warning">'+esc(rollout.quality_warning)+'</p>':'';
 var dialogue=turns.map(function(t){
  return'<article class="dialogue-turn"><div class="utterance policy-bubble"><span class="speaker">'+esc(evaluatedName||"被测 Agent")+' · '+esc(t.turn_id)+'</span><p>'+esc(t.policy_action)+'</p></div><div class="utterance environment-bubble"><span class="speaker">'+esc(environmentName||"Environment Agent")+'</span><p>'+esc(t.environment_response)+'</p></div><details><summary>本轮结构化 appraisal 与状态变化</summary><div class="raw">'+esc(JSON.stringify({social_act:t.social_act,speaker_intent:t.speaker_intent,state_delta:t.state_delta,dynamics_delta:t.dynamics_delta,trigger_events:t.trigger_events},null,2))+'</div></details></article>';
 }).join("");
 return'<section class="panel"><h3>GPT rollout · '+esc(turns.length)+' 轮 · '+esc(label)+'</h3><p class="long">下面是 '+esc(evaluatedName||"被测 Agent")+' 与 '+esc(environmentName||"Environment Agent")+' 的完整对话。请按人物是否站得住、对话是否有效推进、情节是否自然发展来审，不要把机器预检结论直接当成人工结论。</p>'+warning+(diagnosis.length?'<div class="machine-diagnosis"><b>机器标出的风险</b>'+list(diagnosis)+'</div>':'')+'<div class="dialogue">'+dialogue+'</div><details><summary>技术来源与结束信息</summary><div class="meta"><div><span>Trajectory</span>'+esc(rollout.trajectory_id||"—")+'</div><div><span>Policy</span>'+esc(rollout.policy_id||"—")+'</div><div><span>Prompt</span>'+esc(rollout.policy_prompt_id||"—")+'</div><div><span>结束原因</span>'+esc((rollout.ending||{}).reason||"—")+'</div><div><span>产物类型</span>'+esc(rollout.artifact_kind||"—")+'</div><div><span>机器预检</span>'+esc(accepted?"通过":"未通过")+'</div></div><p class="help">产物：'+esc(rollout.artifact_path||"—")+'</p></details></section>';
}
function gate2StatusLabel(status){
 return({machine_pass:"机器通过",machine_fail:"机器标记不通过",machine_error:"机器实验异常",pending_human:"待人工",machine_flagged:"存在机器不通过",pending_human_review:"待人工复核",machine_screen_passed:"机器检查通过",not_sampled:"未抽中"})[status]||status||"未知";
}
function gate2ItemHtml(experiment,item){
 var id=experiment.experiment_id,status=item.gate2_screen_status||"pending_human",body="";
 if(id==="E1"){
  var dirs=item.machine_directions_after_vote||{};
  body='<p><b>最新行动：</b>'+esc(item.latest_action||"—")+'</p><p><b>机器方向：</b>'+esc(Object.keys(dirs).map(function(k){return k+" → "+dirs[k];}).join("；")||"—")+'</p>';
 }else if(id==="E2"){
  body='<p>完整轨迹 '+esc(item.trajectory_id||"—")+'，共 '+esc((item.turns||[]).length)+' 轮。请结合上方对话判断 persona、history、state continuity 与 response-state consistency。</p>';
 }else if(id==="E9"){
  body='<p><b>'+esc(item.state_id||"状态变量")+'</b> · 先验时间尺度 '+esc(item.expected_timescale_prior||"—")+'；变化轮数 '+esc(item.changed_turn_count)+'/'+esc(item.turn_count)+'，最大单轮变化 '+esc(item.maximum_single_turn_change)+'，反转 '+esc(item.reversal_count)+' 次。</p>';
 }else{
  var comparison=item.comparison||{};
  body='<p>checkpoint '+esc(item.checkpoint_turn_id||"—")+' · trajectory '+esc(item.source_trajectory_id||"—")+'</p><p>change score '+esc(comparison.change_score==null?"—":comparison.change_score)+' · direction agreement '+esc(comparison.exact_direction_agreement==null?(item.direction_consistency==null?"—":item.direction_consistency):comparison.exact_direction_agreement)+' · sign reversal '+esc(comparison.true_sign_reversal_rate==null?"—":comparison.true_sign_reversal_rate)+'</p>';
 }
 return'<article class="gate2-item"><div class="gate2-item-head"><b>'+esc(id)+' · '+esc(gate2StatusLabel(status))+'</b><span>'+esc(item.turn_id||item.checkpoint_turn_id||"")+'</span></div>'+body+'<details><summary>查看完整 Gate 2 证据</summary><div class="raw">'+esc(JSON.stringify(item,null,2))+'</div></details></article>';
}
function gate2Html(gate2){
 gate2=gate2||{};var overview=gate2.scenario_overview||{},experiments=gate2.experiments||[];
 var covered=experiments.filter(function(x){return(x.items||[]).length;});
 var cards=covered.map(function(exp){
  return'<section class="gate2-experiment"><h4>'+esc(exp.experiment_id)+' · '+esc(exp.label)+' <span class="badge">'+esc((exp.items||[]).length)+' 项</span></h4>'+(exp.items||[]).map(function(item){return gate2ItemHtml(exp,item);}).join("")+'</section>';
 }).join("");
 return'<section class="panel gate2-panel"><h3>Gate 2 · Environment Validity</h3><p>'+esc(gate2.warning||"")+'</p><div class="meta"><div><span>本场景状态</span><b>'+esc(gate2StatusLabel(overview.status))+'</b></div><div><span>证据项</span>'+esc(overview.evidence_item_count||0)+'</div><div><span>覆盖实验</span>'+esc((overview.experiment_ids||[]).join("、")||"未抽中")+'</div><div><span>处置</span>只标注，不删除</div></div>'+(cards||'<p class="warning">本场景未被 Gate 2 稳定抽样选中；这不等于不通过。</p>')+'</section>';
}
function drawContent(){
 var s=detail.scenario,d=s.narrative_design||{},env=s.environment_agent||{},persona=env.persona||{},role=s.evaluated_agent_role||{},rolePersona=role.persona||{},source=s.source||{};
 var schema=detail.schema_status==="valid"?'<span class="good">schema valid</span>':'<span class="error">schema invalid：'+esc(detail.schema_error)+'</span>';
 document.getElementById("content").innerHTML=
 '<section class="panel"><p class="help">这里展示原审核批次。<a href="/gpt50-live#'+encodeURIComponent(s.scenario_id)+'">查看此场景当前批次的 rollout 和 state →</a></p><h2>'+esc(s.title)+'</h2><div class="meta"><div><span>Scenario</span>'+esc(s.scenario_id)+'</div><div><span>核心机制</span>'+esc(s.mechanism)+'</div><div><span>来源</span>'+esc(source.type)+' · '+esc(source.provenance_id)+'</div><div><span>机器结构检查</span>'+schema+'</div></div><h3 class="section-title">故事背景</h3><p class="long narrative">'+esc(s.background)+'</p><div class="help">SHA-256 '+esc(detail.scenario_sha256)+'</div></section>'+
 '<section class="panel"><h3>两个人为什么会陷入这场冲突</h3><p><b>关系：</b>'+esc(d.relationship_structure)+'</p><p><b>谁掌握什么：</b>'+esc(d.power_structure)+'</p><p><b>眼下的分歧：</b>'+esc(d.goal_conflict)+'</p><p><b>彼此不知道的部分：</b>'+esc(d.information_asymmetry)+'</p></section>'+
 '<section class="panel"><h3>对话双方的人物设定</h3><div class="persona-grid">'+personaHtml("被测模型扮演",rolePersona,role.explicit_goal,"","") + personaHtml("环境扮演",persona,env.explicit_goal,env.hidden_intention,"hidden-author")+'</div></section>'+
 '<section class="panel"><h3>走到今天之前发生了什么</h3>'+list(d.relevant_history)+'<h3>对话中真正可选的路径</h3>'+list(d.meaningful_choice_space)+'</section>'+
 '<section class="panel"><h3>起始人物状态</h3><p class="help">这是互动开始时冻结的状态，不是预写的结局。</p><table class="state">'+rows(s.initial_state)+'</table><details><summary>查看 runtime dynamics seed 与初始化依据</summary><table class="state">'+rows(s.initial_dynamics)+'</table><div class="raw">'+esc(JSON.stringify((s.initialization_notes||{}).rationale||{},null,2))+'</div></details></section>'+
 rolloutHtml(detail.rollout,role.name||rolePersona.name,persona.name)+
 gate2Html(detail.gate2);
}
function approvedCheck(r,c){
 var values=dimensions.map(function(x){return Number((r.quality_scores||{})[x[0]]);});
 var missing=values.some(function(v){return !Number.isFinite(v)||v<1||v>5;});
 var thresholds=!missing&&values[0]>=4&&values[2]>=4&&values[3]>=4&&values.every(function(v){return v>=3;})&&values.reduce(function(a,b){return a+b;},0)/values.length>=4;
 var checks=attestations.every(function(x){return(r.attestations||{})[x[0]]===true;});
 return{ok:c.schema_status==="valid"&&Boolean(r.reviewer)&&r.human_attestation===true&&checks&&thresholds,mean:missing?null:values.reduce(function(a,b){return a+b;},0)/values.length,checks:checks,thresholds:thresholds};
}
function drawReview(){
 var c=current(),r=record(),check=approvedCheck(r,c),stale=r.scenario_sha256&&r.scenario_sha256!==c.scenario_sha256,rr=r.rollout_review||{},g2r=r.gate2_review||{},rollout=detail.rollout||{},gate2=detail.gate2||{},trajectoryStale=rr.trajectory_id&&rr.trajectory_id!==(rollout.trajectory_id||null);
 document.getElementById("review").innerHTML='<h2>场景人工 Gate 1</h2>'+
 (stale?'<p class="error">场景 SHA 已变化：旧审核作废，请重新检查。</p>':'')+
 '<label>结论<select id="decision"><option value="pending">未判断</option><option value="approved">通过并冻结</option><option value="needs_revision">需要修改</option><option value="rejected">拒绝</option></select></label>'+
 '<h3>六项冻结确认</h3>'+attestations.map(function(x){return'<label class="check"><input type="checkbox" data-att="'+x[0]+'" '+((r.attestations||{})[x[0]]?'checked':'')+'> <span>'+esc(x[1])+'</span></label>';}).join("")+
 '<h3>质量评分（1–5）</h3><div class="scores">'+dimensions.map(function(x){var v=(r.quality_scores||{})[x[0]];return'<label>'+esc(x[1])+'</label><select data-score="'+x[0]+'"><option value="">—</option>'+[1,2,3,4,5].map(function(n){return'<option value="'+n+'" '+(Number(v)===n?'selected':'')+'>'+n+'</option>';}).join("")+'</select>';}).join("")+'</div>'+
 '<div id="threshold" class="threshold '+(check.thresholds?'good':'warning')+'">通过阈值：可信度/取舍/历史 ≥4；其他 ≥3；均分 ≥4.0。当前均分：'+(check.mean==null?'—':check.mean.toFixed(2))+'</div>'+
 '<label>审核备注<textarea id="notes" placeholder="需要修改或拒绝时请写具体问题">'+esc(r.notes||"")+'</textarea></label>'+
 '<label class="check"><input id="human" type="checkbox" '+(r.human_attestation?'checked':'')+'> <span><b>真人确认</b>：我已亲自审阅以上场景、initial state 和 triggers；runtime dynamics seed 仅由机器合同校验。本记录不是模型自动批准。</span></label>'+
 '<hr><h2>Rollout 人工审查</h2>'+(trajectoryStale?'<p class="error">rollout 已变化：旧的对话审核作废，请重新检查。</p>':'')+(rollout.turns&&rollout.turns.length?'<label>对话结论<select id="rolloutDecision"><option value="pending">未判断</option><option value="usable">可用</option><option value="borderline">边界案例，保留讨论</option><option value="reject">拒绝</option></select></label><h3>对话评分（1–5）</h3><div class="scores">'+rolloutDimensions.map(function(x){var v=(rr.scores||{})[x[0]];return'<label>'+esc(x[1])+'</label><select data-rollout-score="'+x[0]+'"><option value="">—</option>'+[1,2,3,4,5].map(function(n){return'<option value="'+n+'" '+(Number(v)===n?'selected':'')+'>'+n+'</option>';}).join("")+'</select>';}).join("")+'</div><label>对话审查备注<textarea id="rolloutNotes" placeholder="请记录过短、模板化、跳步或值得保留的原因">'+esc(rr.notes||"")+'</textarea></label>':'<p class="warning">当前没有对话正文，暂时无法做 rollout 人工判定。</p>')+
 '<hr><h2>Gate 2 筛选复核</h2><p class="help">评价机器筛选是否合理，不会删除场景，也不会替代 batch-level Gate 2 人工签字。</p><label>对机器标签的判断<select id="gate2Decision"><option value="pending">未判断</option><option value="reasonable">标签合理</option><option value="questionable">标签可疑</option><option value="needs_more_evidence">证据不足</option></select></label><label>Gate 2 备注<textarea id="gate2Notes" placeholder="记录误杀、漏检、指标不合理或未抽中问题">'+esc(g2r.notes||"")+'</textarea></label>'+
 '<button id="save" class="primary save">保存场景、rollout 与 Gate 2 审核</button><p class="help">三类结论分开保存。浏览器只保存草稿；导出 JSON 后再进入正式冻结流程。</p>';
 document.getElementById("decision").value=r.decision||"pending";
 if(document.getElementById("rolloutDecision"))document.getElementById("rolloutDecision").value=rr.decision||"pending";
 document.getElementById("gate2Decision").value=g2r.decision||"pending";
 document.getElementById("save").onclick=saveReview;
 document.querySelectorAll("[data-score]").forEach(function(x){x.onchange=updateThreshold;});
}
function updateThreshold(){
 var q={};document.querySelectorAll("[data-score]").forEach(function(x){q[x.dataset.score]=x.value?Number(x.value):null;});
 var check=approvedCheck({quality_scores:q},current()),el=document.getElementById("threshold");
 el.className="threshold "+(check.thresholds?"good":"warning");
 el.textContent="通过阈值：可信度/取舍/历史 ≥4；其他 ≥3；均分 ≥4.0。当前均分："+(check.mean==null?"—":check.mean.toFixed(2));
}
function saveReview(){
 var c=current(),s=store(),decision=document.getElementById("decision").value,a={},q={};
 document.querySelectorAll("[data-att]").forEach(function(x){a[x.dataset.att]=x.checked;});
 document.querySelectorAll("[data-score]").forEach(function(x){q[x.dataset.score]=x.value?Number(x.value):null;});
 var rolloutDecision=document.getElementById("rolloutDecision"),rolloutScores={};
 document.querySelectorAll("[data-rollout-score]").forEach(function(x){rolloutScores[x.dataset.rolloutScore]=x.value?Number(x.value):null;});
 var rolloutReview=rolloutDecision?{trajectory_id:(detail.rollout||{}).trajectory_id||null,decision:rolloutDecision.value,scores:rolloutScores,notes:document.getElementById("rolloutNotes").value.trim(),reviewed_at_utc:new Date().toISOString()}:null;
 var gate2Review={decision:document.getElementById("gate2Decision").value,notes:document.getElementById("gate2Notes").value.trim(),scenario_gate2_status:((detail.gate2||{}).scenario_overview||{}).status||"not_sampled",experiment_ids:((detail.gate2||{}).scenario_overview||{}).experiment_ids||[],reviewed_at_utc:new Date().toISOString()};
 var r={record_type:"gpt50_gate1",scenario_id:c.scenario_id,reviewer:document.getElementById("reviewer").value.trim(),reviewed_at_utc:new Date().toISOString(),scenario_sha256:c.scenario_sha256,decision:decision,human_attestation:document.getElementById("human").checked,attestations:a,quality_scores:q,notes:document.getElementById("notes").value.trim(),rollout_review:rolloutReview,gate2_review:gate2Review};
 if(decision==="approved"&&!approvedCheck(r,c).ok){alert("不能批准：请确认 schema 有效、填写审核人、完成六项确认和评分阈值，并勾选真人确认。");return;}
 if((decision!=="pending"||(rolloutReview&&rolloutReview.decision!=="pending")||gate2Review.decision!=="pending")&&!r.reviewer){alert("请填写审核人姓名或 ID。");return;}
 s.reviewer=r.reviewer;s.records[key(c.scenario_id)]=r;persist(s);drawQueue();drawReview();alert("已保存 "+c.scenario_id+" · "+decision);
}
async function loadCurrent(){
 if(!data||!data.candidates.length)return;
 drawQueue();detail=await get("/api/gpt50-scenario/"+encodeURIComponent(current().scenario_id));drawContent();drawReview();
}
function drawBatchStatus(){
 var expected=data.expected_scenario_count||50,complete=data.review_ready===true,rollout=data.rollout||{},gate2=data.gate2||{},gate2Manifest=gate2.manifest||{},gate2Progress=gate2.machine_progress||{};
 document.getElementById("count").textContent=data.scenario_count+" / "+expected+" 已生成 · "+data.schema_valid_count+" schema valid";
 document.getElementById("root").textContent="作者模型："+data.authoring_model+" · 正式批次："+data.active_scenario_root;
 document.getElementById("status").innerHTML='<b>正式 GPT50：'+data.scenario_count+' / '+expected+'</b> · '+(complete?'<span class="good">可开始完整 Gate 1</span>':'<span class="error">'+esc(data.review_blocker||'批次未完成')+'</span>')+(data.load_errors.length?' · <span class="error">加载错误 '+data.load_errors.length+'</span>':'')+'<p class="help">'+esc(data.human_review_warning)+'</p>';
 var counts=rollout.attempt_status_counts||{},done=rollout.completed_count||0,retained=rollout.retained_count||0,short=rollout.short_trajectory_count||0,total=rollout.expected_count||expected;
 document.getElementById("rolloutStatus").innerHTML='<h3>GPT rollout 与 Gate 2 实时进度</h3><div class="meta"><div><span>机器接收</span><b>'+esc(done)+' / '+esc(total)+'</b></div><div><span>机器拒绝</span>'+esc(counts.machine_rejected||0)+'</div><div><span>无可读对话</span>'+esc(rollout.without_readable_rollout_count==null?total:rollout.without_readable_rollout_count)+'</div><div><span>Gate 2 模式</span>'+esc(gate2Manifest.mode||"not_started")+'</div><div><span>E1 / E2 / E9</span>'+esc((gate2Manifest.e1_review_items||0)+" / "+(gate2Manifest.e2_review_items||0)+" / "+(gate2Manifest.e9_review_items||0))+'</div><div><span>Gate 2 机器实验</span>'+esc((gate2Progress.completed_scenario_count||0)+" / "+(gate2Progress.target_scenario_count||50))+'</div></div><p class="help">机器拒绝的完整对话仍会展示。Gate 2 未抽中不等于失败，所有机器结论仍需人工复核。更新时间：'+esc(rollout.updated_at_utc||"—")+'。</p>';
}
async function refresh(){
 data=await get("/api/gpt50-review");
 drawBatchStatus();
 if(index>=data.candidates.length)index=0;drawQueue();
 if(data.candidates.length)await loadCurrent();else document.getElementById("content").innerHTML='<section class="panel warning">'+esc(data.review_blocker||'正式批次没有可审核场景。')+'</section>';
}
async function refreshProgress(){
 var next=await get("/api/gpt50-review");
 data=next;drawBatchStatus();drawQueue();
 if(data.candidates.length)await loadCurrent();
}
document.getElementById("reviewer").value=store().reviewer||"";
document.getElementById("reviewer").oninput=function(){var s=store();s.reviewer=this.value.trim();persist(s);};
document.getElementById("search").oninput=drawQueue;
document.getElementById("prev").onclick=function(){if(index>0){index--;loadCurrent();}};
document.getElementById("next").onclick=function(){if(data&&index+1<data.candidates.length){index++;loadCurrent();}};
document.getElementById("refresh").onclick=function(){refresh().catch(showError);};
document.getElementById("export").onclick=function(){
 var s=store(),records=Object.keys(s.records).filter(function(k){return k.indexOf("gpt50_gate1:")===0;}).map(function(k){return s.records[k];});
 var payload={format:"socialflux_gpt50_gate1_browser_export_v1",batch:data&&data.batch,active_scenario_root:data&&data.active_scenario_root,exported_at_utc:new Date().toISOString(),reviewer:s.reviewer,record_count:records.length,records:records};
 var a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:"application/json"}));a.download="gpt50-gate1-review.json";a.click();URL.revokeObjectURL(a.href);
};
document.getElementById("importBtn").onclick=function(){document.getElementById("importFile").click();};
document.getElementById("importFile").onchange=async function(){
 try{
  var v=JSON.parse(await this.files[0].text());if(v.format!=="socialflux_gpt50_gate1_browser_export_v1"||!Array.isArray(v.records))throw new Error("文件格式不正确");
  var s=store();v.records.forEach(function(r){if(r.record_type==="gpt50_gate1"&&r.scenario_id)s.records[key(r.scenario_id)]=r;});if(v.reviewer)s.reviewer=v.reviewer;persist(s);document.getElementById("reviewer").value=s.reviewer;drawQueue();drawReview();alert("已导入 "+v.records.length+" 条记录");
 }catch(e){alert("导入失败："+e.message);}finally{this.value="";}
};
function showError(e){document.getElementById("status").innerHTML='<span class="error">加载失败：'+esc(e.message)+'</span>';}
refresh().catch(showError);
setInterval(function(){refreshProgress().catch(showError);},30000);
})();
