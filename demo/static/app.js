const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>Array.from(r.querySelectorAll(s));
const esc=x=>String(x==null?"":x).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const DEBUG_TOKEN=new URLSearchParams(location.search).get("token")||sessionStorage.getItem("emotree_debug_token")||"";if(DEBUG_TOKEN)sessionStorage.setItem("emotree_debug_token",DEBUG_TOKEN);const withToken=url=>url+(url.includes("?")?"&":"?")+"token="+encodeURIComponent(DEBUG_TOKEN);
const api=async(url,opt={})=>{const r=await fetch(url,opt),d=await r.json();if(!r.ok)throw new Error(d.error||"request failed");return d};
function nav(){let page=document.body.dataset.page;$("#nav").innerHTML=[["participant","index.html","Participant"],["debug","researcher.html","Researcher"],["replay","replay.html","Replay"]].map(x=>{let href=x[0]!=="participant"&&DEBUG_TOKEN?x[1]+"?token="+encodeURIComponent(DEBUG_TOKEN):x[1];return '<a class="'+(page===x[0]?"active":"")+'" href="'+href+'">'+x[2]+"</a>"}).join("")}
function post(url,data){return api(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)})}
function turns(conversation){return conversation.map(x=>'<div class="turn '+x.role+'">'+(x.cue?'<div class="turn-cue">['+esc(x.cue)+']</div>':"")+'<div class="role">'+(x.role==="advisor"?"高启明":"你")+'</div><div class="bubble">'+esc(x.text)+'</div></div>').join("")}
let participantSession=null;
const EXTERNAL_ZH={facial_expression:"表情",gaze:"视线",head_motion:"头部动作",speech_rate:"语速",pitch:"音调",pause_before_speech_ms:"开口前停顿",emotion_intensity:"外显强度"};
function renderStateObservation(o){
 if(!o)return;
 $("#stateCueText").textContent=o.cue||"本轮没有新的外显线索";
 let external=o.external||{};
 $("#externalSignals").innerHTML=Object.keys(external).length
  ?Object.entries(external).map(([k,v])=>'<div class="external-signal"><span>'+esc(EXTERNAL_ZH[k]||k)+'</span><b>'+esc(k==="pause_before_speech_ms"?v+" ms":v)+'</b></div>').join("")
  :'<div class="muted">当前仅提供文字线索</div>';
}
async function newSession(){participantSession=await post("/api/sessions",{mode:"participant"});localStorage.setItem("emotree_session",participantSession.session_id);renderParticipant()}
async function loadParticipant(){
 let id=localStorage.getItem("emotree_session");
 if(id){try{participantSession=await api("/api/sessions/"+id)}catch(e){}}
 if(!participantSession||participantSession.status!=="active")await newSession();else renderParticipant()
}
function renderParticipant(){
 let s=participantSession,last=s.current_advisor_message;
 $("#turnCount").textContent=s.turn_id+" / "+s.max_turns;
 $("#turnBar").style.width=(s.turn_id/s.max_turns*100)+"%";
 $("#advisorCue").textContent=last.cue?"["+last.cue+"]":"";
 $("#advisorCue").style.display=last.cue?"block":"none";
 $("#advisorSpeech").textContent="“"+last.text+"”";
 renderStateObservation(s.state_observation);
 $("#history").innerHTML=turns(s.conversation);
 $("#history").scrollTop=$("#history").scrollHeight;
 $("#studentText").disabled=s.status!=="active";$("#send").disabled=s.status!=="active";
 if(s.status!=="active")$("#error").textContent="会话已结束。可以开始一个新会话。"
}
async function sendTurn(){
 let text=$("#studentText").value.trim();if(!text)return;
 $("#send").disabled=true;$("#send").textContent="处理中…";$("#error").textContent="";
 try{let r=await post("/api/sessions/"+participantSession.session_id+"/turn",{student_text:text});participantSession=r.participant;$("#studentText").value="";renderParticipant()}
 catch(e){$("#error").textContent=e.message}
 finally{$("#send").disabled=false;$("#send").textContent="发送"}
}
async function participant(){
 let scenario=await api("/api/scenario");
 $("#scenarioTitle").textContent=scenario.title;$("#advisorName").textContent=scenario.advisor.identity.name;
 $("#facts").innerHTML=scenario.world_facts.map(x=>"<li>"+esc(x)+"</li>").join("");
 $("#send").onclick=sendTurn;$("#newSession").onclick=newSession;
 $("#studentText").onkeydown=e=>{if(e.key==="Enter"&&(e.ctrlKey||e.metaKey))sendTurn()};
 $$(".suggestions button").forEach(b=>b.onclick=()=>{$("#studentText").value=b.dataset.text;$("#studentText").focus()});
 await loadParticipant()
}
let sessions=[],debugSession=null,debugTimer=null;
async function sessionList(){
 sessions=await api(withToken("/api/sessions"));
 $("#sessions").innerHTML=sessions.length?sessions.map(x=>'<button class="session '+(debugSession&&debugSession.session_id===x.session_id?"active":"")+'" data-id="'+x.session_id+'"><b>'+x.session_id+'</b><small>Turn '+x.turn_id+' · '+x.discrete_state+' · '+x.status+'</small></button>').join(""):'<div class="empty">暂无会话</div>';
 $$(".session").forEach(b=>b.onclick=()=>loadDebug(b.dataset.id))
}
function deltaCell(v){let cls=v>0?"up":v<0?"down":"";return '<span class="delta '+cls+'">'+(v>0?"↑":"")+v+"</span>"}
function chart(series){
 let keys=["anger","anxiety","trust_student","hostility_student","willingness_to_negotiate","department_escalation_risk"],colors=["#b74e3d","#d89a35","#235f48","#6f3442","#426f8c","#755a9d"],w=760,h=220,p=28,maxTurn=Math.max(1,series[series.length-1].turn_id);
 let grid=[0,25,50,75,100].map(v=>'<line x1="'+p+'" y1="'+(h-p-v*(h-2*p)/100)+'" x2="'+(w-p)+'" y2="'+(h-p-v*(h-2*p)/100)+'" stroke="#ddd8ce"/><text x="3" y="'+(h-p-v*(h-2*p)/100+3)+'">'+v+"</text>").join("");
 let lines=keys.map((k,i)=>{let points=series.map(x=>(p+x.turn_id*(w-2*p)/maxTurn)+","+(h-p-x[k]*(h-2*p)/100)).join(" ");return '<polyline class="chart-line" stroke="'+colors[i]+'" points="'+points+'"/>'}).join("");
 let legend=keys.map((k,i)=>'<span class="tag" style="color:'+colors[i]+'">'+k+"</span>").join("");
 return '<svg class="chart" viewBox="0 0 '+w+" "+h+'">'+grid+lines+"</svg><div>"+legend+"</div>"
}
function renderDebug(){
 let s=debugSession,last=s.trajectory[s.trajectory.length-1],before=last?last.state_before:s.latent_state,deltas=last?last.applied_deltas:{};
 $("#debugEmpty").style.display="none";$("#debugContent").style.display="block";
 $("#currentState").textContent=s.discrete_state;$("#previousState").textContent=s.previous_state||"—";
 $("#stateTransition").textContent=last&&last.state_transition?last.state_transition:"No transition this turn";
 $("#latent").innerHTML=Object.entries(s.latent_state).map(([k,v])=>'<div class="latent-row"><span>'+k+'</span><div class="bar"><i style="width:'+v+'%"></i></div><b>'+v+"</b>"+deltaCell(deltas[k]||0)+"</div>").join("");
 $("#action").innerHTML=last?'<h3>'+esc(last.interpreted_action.primary_strategy)+'</h3>'+last.interpreted_action.strategy_labels.map(x=>'<span class="tag">'+x+"</span>").join("")+'<div class="log">'+esc(JSON.stringify(last.interpreted_action.dimensions,null,2))+"</div>":'<div class="muted">等待学生输入</div>';
 $("#rules").innerHTML=last?last.triggered_conditions.map(x=>'<div class="tag">'+esc(x)+"</div>").join(""):'—';
 $("#cueDebug").textContent=last&&last.observable_cue?last.observable_cue.text:"本轮没有显著 State Transition";
 $("#internal").textContent=last?JSON.stringify({proposed_state_effects:last.proposed_state_effects,trait_modifiers:last.trait_modifiers,internal_research_log:last.internal_research_log,memory:last.memory_after},null,2):"等待第一轮";
 $("#trajectoryChart").innerHTML=chart(s.trajectory_series);
 $("#debugConversation").innerHTML=turns(s.conversation);
}
async function loadDebug(id){debugSession=await api(withToken("/api/sessions/"+id+"?view=researcher"));renderDebug();await sessionList()}
async function debug(){
 await sessionList();if(sessions[0])await loadDebug(sessions[0].session_id);
 debugTimer=setInterval(async()=>{await sessionList();if(debugSession)await loadDebug(debugSession.session_id)},2500)
}
let replaySession=null;
async function replay(){
 let list=await api(withToken("/api/sessions"));$("#replaySession").innerHTML='<option value="">选择 trajectory</option>'+list.map(x=>'<option value="'+x.session_id+'">'+x.session_id+" · "+x.turn_id+" turns · "+x.discrete_state+"</option>").join("");
 $("#replaySession").onchange=async()=>{if(!$("#replaySession").value)return;replaySession=await api(withToken("/api/sessions/"+$("#replaySession").value+"?view=researcher"));$("#step").max=replaySession.turn_id;$("#step").value=replaySession.turn_id;renderReplay()};
 $("#step").oninput=renderReplay;$("#fork").onclick=async()=>{if(!replaySession)return;let x=await post(withToken("/api/sessions/"+replaySession.session_id+"/fork"),{through_turn:Number($("#step").value)});location.href="researcher.html?token="+encodeURIComponent(DEBUG_TOKEN)+"&session="+x.session_id}
}
function renderReplay(){
 let n=Number($("#step").value),logs=replaySession.trajectory.slice(0,n),log=logs[logs.length-1],series=replaySession.trajectory_series.slice(0,n+1),conversation=replaySession.conversation.filter(x=>x.turn_id<=n);
 $("#stepLabel").textContent="Turn "+n+" / "+replaySession.turn_id;
 $("#replayState").textContent=n===0?replaySession.trajectory_series[0].discrete_state:log.discrete_state_after;
 $("#replayTransition").textContent=log?(log.state_transition||"No transition"):"Initial state";
 $("#replayConversation").innerHTML=turns(conversation);
 $("#replayLog").textContent=log?JSON.stringify(log,null,2):JSON.stringify(replaySession.trajectory_series[0],null,2);
 $("#replayChart").innerHTML=chart(series)
}
document.addEventListener("DOMContentLoaded",async()=>{nav();try{let p=document.body.dataset.page;if(p==="participant")await participant();if(p==="debug")await debug();if(p==="replay")await replay()}catch(e){$(".wrap").insertAdjacentHTML("afterbegin",'<div class="notice">'+esc(e.message)+"</div>")}});