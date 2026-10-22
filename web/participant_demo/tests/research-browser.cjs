const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {randomBytes}=require('node:crypto');
const url=process.env.RESEARCH_QA_URL||'http://127.0.0.1:8012';
assert.match(url,/^http:\/\/127\.0\.0\.1:/,'QA must use isolated local D1');
const invite='qa-human-gt-invite-20261022-abcdefghijklm';
const dimensions=['goal_achievement','state_adaptation','risk_management','recovery','relationship_outcome'];
const out='/tmp/socialflux-research-browser';fs.mkdirSync(out,{recursive:true});
async function post(context,action,data){const r=await context.request.post(url+'/api/demo/'+action,{data});return {status:r.status(),data:await r.json()};}
async function state(context){return (await context.request.get(url+'/api/demo/status')).json();}
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
 await page.goto(url+'/#invite='+invite);await page.locator('#alias').waitFor();
 assert.match(await page.title(),/人工标注/);
 const catalog=(await state(context)).catalog, t4Assignment=catalog.assignments.find(a=>a.id==='t4-09')||catalog.assignments.find(a=>a.track==='t4'), t4Checks=[];
 await page.locator('#alias').fill('qa-browser-'+Date.now());await page.locator('#exposure').selectOption('no');await page.locator('#consent').check();
 await page.getByRole('button',{name:'进入标注空间',exact:true}).click();await page.locator('#issued-recovery').waitFor();
 const code=await page.locator('#issued-recovery').inputValue();await page.getByRole('button',{name:/我已保存/}).click();
 await page.locator('label.option').first().waitFor();let s=await state(context);const first=s.research.items[0].id;
 assert.equal(s.dataset.kind,'research');assert.equal(s.research.items.length,s.research.assignment.scene_ids.length*8);assert.ok(s.research.items.length<=40);assert.equal(s.session.workflow.phase,'blind');
 const videoCondition=s.research.assignment.track==='offline_video';
 if(videoCondition)assert.ok(s.research.items.every(x=>x.coverage.complete&&x.media.every(v=>v.audio_required&&v.speech_language==='en')));
 assert.doesNotMatch(JSON.stringify(s.research),/"(?:private_character|initial_state|authoring|ground_truth|oracle_reference)"/);
 assert.equal((await post(context,'evidence',{instanceId:first})).status,400);
 assert.equal((await post(context,'lock',{revision:s.session.revision,answers:{}})).status,400);
 if(videoCondition){
  const media=await context.request.get(url+s.research.items[0].media[0].url,{headers:{range:'bytes=0-2047'}});assert.ok([200,206].includes(media.status()));assert.ok((await media.body()).length>2000);
  const clip=page.locator('video').first();assert.equal(await clip.evaluate(v=>v.muted),false);
  await clip.evaluate(async v=>{v.muted=true;await v.play();});await page.waitForTimeout(1500);
  assert.ok(await clip.evaluate(v=>v.currentTime>0&&v.duration>0));await clip.evaluate(v=>v.pause());
 }
 await page.locator('label.option').filter({has:page.locator('input[value=A]')}).click();await page.getByLabel('把握程度',{exact:true}).selectOption('medium');await page.waitForTimeout(2000);
 s=await state(context);assert.equal(s.session.answers[first].answer,'A');
 await page.screenshot({path:out+'/offline-blind-desktop.png',fullPage:true});
 const answers=Object.fromEntries(s.research.items.map(x=>[x.id,{answer:'A',confidence:'medium',rationale:'QA public evidence',issue:'none'}]));
 const stale=s.session.revision;let saved=await post(context,'draft',{revision:stale,answers});assert.equal(saved.status,200);s=saved.data;
 assert.equal((await post(context,'draft',{revision:stale,answers:{}})).status,409);
 const locked=await post(context,'lock',{revision:s.session.revision,answers});assert.equal(locked.status,200);s=locked.data;
 if(s.session.workflow.phase==='gate2'){
  assert.equal((await post(context,'evidence',{instanceId:first})).status,400);
  const gate2Answers=Object.fromEntries(s.research.gate2Tasks.map(t=>[t.id,{values:Object.fromEntries(t.questions.map(q=>[q.id,Object.keys(q.choices)[0]])),rationale:'QA independent evidence judgment'}]));
  const checked=await post(context,'gate2-lock',{revision:s.session.revision,gate2Answers});assert.equal(checked.status,200);s=checked.data;
 }
 assert.equal(s.session.workflow.phase,'gt');const e=await post(context,'evidence',{instanceId:first});assert.equal(e.status,200);assert.ok(e.data.evidence.scenario.environment_agent);assert.ok(e.data.evidence.omniscient_evidence.initial_state);assert.ok(e.data.machine.answer);
 assert.equal((await post(context,'evidence',{instanceId:'unassigned'})).status,400);
 await page.reload();await page.getByRole('button',{name:'机器答案',exact:true}).waitFor();await page.getByRole('button',{name:'机器答案',exact:true}).click();await page.getByText('机器候选答案',{exact:true}).count();
 await page.locator('label.option').filter({has:page.locator('input[value=A]')}).click();await page.getByLabel('GT 判断依据',{exact:true}).fill('QA: 已核对状态、环境私有端及机器候选。');await page.waitForTimeout(1800);
 await page.screenshot({path:out+'/offline-gt-desktop.png',fullPage:true});
 const recovered=await browser.newContext();assert.equal((await post(recovered,'recover',{alias:s.session.alias,recoveryCode:code})).status,200);let current=await state(recovered);assert.ok(current.session.workflow.gt[first].rationale);
 const gt=Object.fromEntries(current.research.items.map(x=>[x.id,{answer:'A',acceptable_answers:['A'],decision:'usable',rationale:'QA reviewed private evidence'}]));
 const gate2Answers=Object.fromEntries((current.research.gate2Tasks||[]).map(t=>[t.id,current.session.workflow.gate2.answers[t.id]||{values:Object.fromEntries(t.questions.map(q=>[q.id,Object.keys(q.choices)[0]])),rationale:'QA reviewed frozen scene evidence'}]));
 const submitted=await post(recovered,'submit',{revision:current.session.revision,gt,gate2Answers,answers:{},attestation:true});assert.equal(submitted.status,200);assert.deepEqual(submitted.data.session.workflow.blind,answers);
 assert.equal((await post(recovered,'draft',{revision:submitted.data.session.revision,gt:{}})).status,409);
 assert.equal((await post(recovered,'submit',{})).status,200);
 fs.writeFileSync(out+'/offline-export.json',JSON.stringify(await (await recovered.request.get(url+'/api/demo/export')).json()));await recovered.close();
 for(const [alias,char,kind,count] of [['qa-legacy','L','text',6],['qa-media','M','multimodal_review',270]]){
  const old=await browser.newContext();const r=await post(old,'recover',{alias,recoveryCode:'SF-'+char.repeat(43)});assert.equal(r.status,200);assert.equal(r.data.dataset.kind,kind);assert.equal(r.data.questions.length,count);await old.close();
 }
 const prior=await browser.newContext();const restored=await post(prior,'recover',{alias:'qa-research-v3',recoveryCode:'SF-'+'R'.repeat(43)});
 assert.equal(restored.status,200);assert.equal(restored.data.dataset.kind,'research');assert.equal(restored.data.questions.length,30);
 assert.notEqual(restored.data.dataset.sha256,s.dataset.sha256);
 const priorDraft=await post(prior,'draft',{revision:restored.data.session.revision,answers:{}});assert.equal(priorDraft.status,200);
 await prior.close();
 const tc=await browser.newContext({viewport:{width:390,height:844}});await post(tc,'access',{invite});
 const tr=await post(tc,'start',{alias:'qa-t4-'+Date.now(),priorExposure:false,consent:true,assignmentId:t4Assignment?.id||'t4-09',recoveryCode:'SF-'+randomBytes(32).toString('base64url')});
 if(t4Assignment){
 assert.equal(tr.status,200);
 let t=tr.data;assert.equal(t.research.trajectories.length,5);assert.ok(t.research.trajectories.every(x=>!Object.hasOwn(x,'machine')));
 const tp=await tc.newPage();tp.on('pageerror',e=>errors.push(e.message));await tp.goto(url);await tp.getByLabel('目标达成分数',{exact:true}).waitFor();
 await tp.getByLabel('目标达成分数',{exact:true}).selectOption('6');await tp.getByLabel('目标达成证据',{exact:true}).fill('t1,t2');await tp.getByLabel('目标达成依据',{exact:true}).fill('QA observed progress');await tp.waitForTimeout(1800);
 t=await state(tc);assert.deepEqual(t.session.workflow.ratings[t.research.trajectories[0].id].goal_achievement.evidence_turn_ids,['t1','t2']);
 assert.ok(await tp.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await tp.screenshot({path:out+'/t4-mobile.png',fullPage:true});
 const ratings=Object.fromEntries(t.research.trajectories.map(x=>[x.id,Object.fromEntries(dimensions.map(d=>[d,{score:d==='recovery'?null:6,evidence_turn_ids:['t1','t2'],rationale:'QA observed evidence',insufficient_evidence:d==='recovery'}]))]));
 let final=await post(tc,'submit',{revision:t.session.revision,ratings,attestation:true});assert.equal(final.status,200);
 assert.equal(final.data.session.workflow.phase,'t4_review');assert.ok(final.data.research.trajectories.every(x=>!Object.hasOwn(x,'machine')));
 const audit=Object.fromEntries(final.data.research.gate2Tasks.map(task=>[task.id,{values:Object.fromEntries(task.questions.map(q=>[q.id,Object.hasOwn(q.choices,'uncertain')?'uncertain':Object.hasOwn(q.choices,'unverifiable')?'unverifiable':Object.keys(q.choices)[0]])),rationale:'QA reviewed available material and retained uncertainty.'}]));
 final=await post(tc,'submit',{revision:final.data.session.revision,gate2Answers:audit,attestation:true});assert.equal(final.status,200);assert.ok(final.data.research.trajectories.every(x=>Object.hasOwn(x,'machine')));
 await tp.reload();await tp.getByText('逐维差值表 · 人工 − Claude',{exact:true}).waitFor();assert.ok(await tp.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await tp.screenshot({path:out+'/t4-comparison-mobile.png',fullPage:true});
 const exported=await (await tc.request.get(url+'/api/demo/export')).json();assert.equal(exported.comparisons.length,25);assert.ok(exported.comparisons.filter(x=>x.dimension==='recovery').every(x=>x.delta_human_minus_claude===null));fs.writeFileSync(out+'/t4-export.json',JSON.stringify(exported));
 t4Checks.push('T4 evidence validation','T4 machine reveal','paired null handling','T4 mobile layout');
 }else{
 assert.equal(catalog.scope,'offline');assert.equal(tr.status,400);assert.equal((await state(tc)).session,null);
 t4Checks.push('new online assignments rejected');
 }
 await tc.close();assert.deepEqual(errors,[]);console.log(JSON.stringify({ok:true,videoPlaybackTested:videoCondition,t4WorkflowTested:!!t4Assignment,checks:['public boundary','private API gate','autosave','revision conflict','GT recovery and lock','legacy three releases',...t4Checks],output:out}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
