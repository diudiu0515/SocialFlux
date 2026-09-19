(function(){
"use strict";
var STORAGE_KEY="socialflux.gpt50.gate1.drafts.v1";
var data=null,index=0,detail=null;
var attestations=[
 ["variables_relevant","状态变量确实与本场景相关"],
 ["values_justified","S0/D0 数值有充分情境依据"],
 ["no_policy_effect_baked_in","初始状态没有预写某种策略的效果"],
 ["initial_triggers_inactive","三个 trigger 在 S0/D0 均未激活"],
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
  return'<button class="item '+(v.i===index?'active':'')+'" data-i="'+v.i+'"><span class="dot '+state+'"></span><strong>'+esc(v.c.scenario_id)+' · '+esc(v.c.title)+'</strong><small>'+esc(v.c.schema_status)+' · '+esc(r.decision||"pending")+'</small></button>';
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
function drawContent(){
 var s=detail.scenario,d=s.narrative_design||{},env=s.environment_agent||{},persona=env.persona||{},role=s.evaluated_agent_role||{},source=s.source||{};
 var schema=detail.schema_status==="valid"?'<span class="good">schema valid</span>':'<span class="error">schema invalid：'+esc(detail.schema_error)+'</span>';
 document.getElementById("content").innerHTML=
 '<section class="panel"><h2>'+esc(s.title)+'</h2><div class="meta"><div><span>Scenario</span>'+esc(s.scenario_id)+'</div><div><span>机制</span>'+esc(s.mechanism)+'</div><div><span>来源</span>'+esc(source.type)+' · '+esc(source.provenance_id)+'</div><div><span>机器结构检查</span>'+schema+'</div></div><p class="long">'+esc(s.background)+'</p><div class="help">SHA-256 '+esc(detail.scenario_sha256)+'</div></section>'+
 '<section class="panel"><h3>关系、权力与冲突</h3><div class="kv"><span class="label">关系结构</span>'+esc(d.relationship_structure)+'</div><div class="kv"><span class="label">权力结构</span>'+esc(d.power_structure)+'</div><div class="kv"><span class="label">目标冲突</span>'+esc(d.goal_conflict)+'</div><div class="kv"><span class="label">信息不对称</span>'+esc(d.information_asymmetry)+'</div></section>'+
 '<section class="panel"><h3>双方角色</h3><div class="columns"><div class="kv"><span class="label">被评估 Agent</span><b>'+esc(role.name)+'</b> · '+esc(role.role)+'<p>'+esc(role.explicit_goal)+'</p></div><div class="kv hidden-author"><span class="label">Environment Agent · 作者侧</span><b>'+esc(persona.name)+'</b> · '+esc(persona.role)+'<p>'+esc(env.explicit_goal)+'</p><span class="label">隐藏意图（不会给 Policy）</span>'+esc(env.hidden_intention)+'</div></div></section>'+
 '<section class="panel"><h3>相关历史</h3>'+list(d.relevant_history)+'<h3>有意义的选择空间</h3>'+list(d.meaningful_choice_space)+'</section>'+
 '<section class="panel"><h3>S0 · 初始状态</h3><table class="state">'+rows(s.initial_state)+'</table><h3 style="margin-top:16px">D0 · 初始互动动力</h3><table class="state">'+rows(s.initial_dynamics)+'</table><h3 style="margin-top:16px">初始化依据</h3><div class="raw">'+esc(JSON.stringify((s.initialization_notes||{}).rationale||{},null,2))+'</div></section>'+
 '<section class="panel"><h3>Talking-head trigger 可达性</h3>'+(s.video_triggers||[]).map(function(t){return'<div class="kv"><b>'+esc(t.trigger_id)+'</b> · '+esc(t.trigger_mode)+'<div class="help">'+esc(t.cue_template)+'</div><pre class="raw">'+esc(JSON.stringify({conditions:t.conditions,change_conditions:t.change_conditions},null,2))+'</pre></div>';}).join("")+'</section>'+
 '<section class="panel"><h3>机器质量检查（仅供参考，不是人工结论）</h3><table class="state">'+rows(s.quality_gate)+'</table></section>';
}
function approvedCheck(r,c){
 var values=dimensions.map(function(x){return Number((r.quality_scores||{})[x[0]]);});
 var missing=values.some(function(v){return !Number.isFinite(v)||v<1||v>5;});
 var thresholds=!missing&&values[0]>=4&&values[2]>=4&&values[3]>=4&&values.every(function(v){return v>=3;})&&values.reduce(function(a,b){return a+b;},0)/values.length>=4;
 var checks=attestations.every(function(x){return(r.attestations||{})[x[0]]===true;});
 return{ok:c.schema_status==="valid"&&Boolean(r.reviewer)&&r.human_attestation===true&&checks&&thresholds,mean:missing?null:values.reduce(function(a,b){return a+b;},0)/values.length,checks:checks,thresholds:thresholds};
}
function drawReview(){
 var c=current(),r=record(),check=approvedCheck(r,c),stale=r.scenario_sha256&&r.scenario_sha256!==c.scenario_sha256;
 document.getElementById("review").innerHTML='<h2>人工 Gate 1</h2>'+
 (stale?'<p class="error">场景 SHA 已变化：旧审核作废，请重新检查。</p>':'')+
 '<label>结论<select id="decision"><option value="pending">未判断</option><option value="approved">通过并冻结</option><option value="needs_revision">需要修改</option><option value="rejected">拒绝</option></select></label>'+
 '<h3>六项冻结确认</h3>'+attestations.map(function(x){return'<label class="check"><input type="checkbox" data-att="'+x[0]+'" '+((r.attestations||{})[x[0]]?'checked':'')+'> <span>'+esc(x[1])+'</span></label>';}).join("")+
 '<h3>质量评分（1–5）</h3><div class="scores">'+dimensions.map(function(x){var v=(r.quality_scores||{})[x[0]];return'<label>'+esc(x[1])+'</label><select data-score="'+x[0]+'"><option value="">—</option>'+[1,2,3,4,5].map(function(n){return'<option value="'+n+'" '+(Number(v)===n?'selected':'')+'>'+n+'</option>';}).join("")+'</select>';}).join("")+'</div>'+
 '<div id="threshold" class="threshold '+(check.thresholds?'good':'warning')+'">通过阈值：可信度/取舍/历史 ≥4；其他 ≥3；均分 ≥4.0。当前均分：'+(check.mean==null?'—':check.mean.toFixed(2))+'</div>'+
 '<label>审核备注<textarea id="notes" placeholder="需要修改或拒绝时请写具体问题">'+esc(r.notes||"")+'</textarea></label>'+
 '<label class="check"><input id="human" type="checkbox" '+(r.human_attestation?'checked':'')+'> <span><b>真人确认</b>：我已亲自审阅以上场景、S0、D0 和 triggers，本记录不是模型自动批准。</span></label>'+
 '<button id="save" class="primary save">保存本条审核</button><p class="help">浏览器只保存草稿。完成后请导出 JSON，再由应用脚本冻结 scenario 并生成最终 hash-bound registry。</p>';
 document.getElementById("decision").value=r.decision||"pending";
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
 var r={record_type:"gpt50_gate1",scenario_id:c.scenario_id,reviewer:document.getElementById("reviewer").value.trim(),reviewed_at_utc:new Date().toISOString(),scenario_sha256:c.scenario_sha256,decision:decision,human_attestation:document.getElementById("human").checked,attestations:a,quality_scores:q,notes:document.getElementById("notes").value.trim()};
 if(decision==="approved"&&!approvedCheck(r,c).ok){alert("不能批准：请确认 schema 有效、填写审核人、完成六项确认和评分阈值，并勾选真人确认。");return;}
 if(decision!=="pending"&&!r.reviewer){alert("请填写审核人姓名或 ID。");return;}
 s.reviewer=r.reviewer;s.records[key(c.scenario_id)]=r;persist(s);drawQueue();drawReview();alert("已保存 "+c.scenario_id+" · "+decision);
}
async function loadCurrent(){
 if(!data||!data.candidates.length)return;
 drawQueue();detail=await get("/api/gpt50-scenario/"+encodeURIComponent(current().scenario_id));drawContent();drawReview();
}
async function refresh(){
 data=await get("/api/gpt50-review");
 var expected=data.expected_scenario_count||50,complete=data.review_ready===true;
 document.getElementById("count").textContent=data.scenario_count+" / "+expected+" 已生成 · "+data.schema_valid_count+" schema valid";
 document.getElementById("root").textContent="作者模型："+data.authoring_model+" · 正式批次："+data.active_scenario_root;
 document.getElementById("status").innerHTML='<b>正式 GPT50：'+data.scenario_count+' / '+expected+'</b> · '+(complete?'<span class="good">可开始完整 Gate 1</span>':'<span class="error">'+esc(data.review_blocker||'批次未完成')+'</span>')+(data.load_errors.length?' · <span class="error">加载错误 '+data.load_errors.length+'</span>':'')+'<p class="help">'+esc(data.human_review_warning)+'</p>';
 if(index>=data.candidates.length)index=0;drawQueue();
 if(data.candidates.length)await loadCurrent();else document.getElementById("content").innerHTML='<section class="panel warning">'+esc(data.review_blocker||'正式批次没有可审核场景。')+'</section>';
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
})();
