const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {randomBytes}=require('node:crypto');
const fs=require('node:fs');
const url=process.env.RESEARCH_QA_URL||'http://127.0.0.1:8033';
assert.match(url,/^http:\/\/127\.0\.0\.1:/,'Use isolated local D1 only');
const invite='qa-human-gt-invite-20261022-abcdefghijklm';
const out='/tmp/socialflux-scene-sequence-qa';fs.mkdirSync(out,{recursive:true});
async function post(c,action,data){const r=await c.request.post(url+'/api/demo/'+action,{data});return {status:r.status(),data:await r.json()};}
async function status(c){return (await c.request.get(url+'/api/demo/status')).json();}
function body(s,more={}){return {sceneId:s.session.workflow.sceneSequence.scenes[s.session.workflow.sceneSequence.index]?.id,revision:s.session.revision,...more};}
function votes(tasks,old={}) {return Object.fromEntries(tasks.map(t=>[t.id,old[t.id]||{values:Object.fromEntries(t.questions.map(q=>[q.id,Object.hasOwn(q.choices,'uncertain')?'uncertain':Object.hasOwn(q.choices,'unavailable')?'unavailable':Object.keys(q.choices)[0]])),rationale:'Isolated automated QA; not a participant judgment.'}]));}
async function unlock(c,s){
 const answers=Object.fromEntries(s.research.items.map(x=>[x.id,{answer:'A',confidence:'medium',rationale:'QA public answer',issue:'none'}]));
 let r=await post(c,'lock',body(s,{answers}));assert.equal(r.status,200,JSON.stringify(r.data));s=r.data;
 if(s.session.workflow.phase==='gate2'){r=await post(c,'gate2-lock',body(s,{gate2Answers:votes(s.research.gate2Tasks)}));assert.equal(r.status,200,JSON.stringify(r.data));s=r.data;}
 assert.equal(s.session.workflow.phase,'gt');return s;
}
async function finish(c,s){
 const gt=Object.fromEntries(s.research.items.map(x=>[x.id,{answer:'B',acceptable_answers:['B'],decision:'usable',rationale:'QA checked scene evidence'}]));
 const r=await post(c,'submit',body(s,{gt,gate2Answers:votes(s.research.gate2Tasks,s.session.workflow.gate2.answers),attestation:true}));assert.equal(r.status,200,JSON.stringify(r.data));return r.data;
}
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const c=await browser.newContext({viewport:{width:1440,height:1000}}),p=await c.newPage(),errors=[];
 p.on('pageerror',e=>errors.push(e.message));
 try{
 await p.goto(url+'/#invite='+invite);await p.locator('#alias').fill('qa-scene-'+Date.now());await p.locator('#research-track').selectOption('offline_text');await p.locator('#exposure').selectOption('no');await p.locator('#consent').check();await p.getByRole('button',{name:'进入标注空间',exact:true}).click();await p.locator('#issued-recovery').waitFor();const code=await p.locator('#issued-recovery').inputValue();await p.getByRole('button',{name:/我已保存/}).click();await p.locator('input[name=research-answer]').first().waitFor();
 let s=await status(c);assert.equal(s.research.items.length,8);assert.equal(s.questions.length,8);assert.deepEqual(s.research.referenceAnswers,[]);assert.equal(s.session.workflow.sceneSequence.scenes.length,5);assert.equal(await p.locator('.scene-sequence .locked').count(),4);
 const first=s.research.items[0].id,future=s.session.workflow.sceneSequence.scenes[1].itemIds[0],sceneId=s.session.workflow.sceneSequence.scenes[0].id;
 assert.equal((await post(c,'evidence',{instanceId:first})).status,400);assert.equal((await post(c,'evidence',{instanceId:future})).status,400);
 assert.equal((await post(c,'draft',body(s,{answers:{[future]:{answer:'A',confidence:'high',rationale:'',issue:'none'}}}))).status,400);
 assert.equal((await post(c,'lock',body(s,{answers:{}}))).status,400);
 assert.doesNotMatch(JSON.stringify(s.research),/"(?:initial_state|private_character|oracle_reference)"/);
 await p.locator('label.option').filter({has:p.locator('input[value=A]')}).click();await p.getByLabel('把握程度',{exact:true}).selectOption('medium');
 await p.waitForFunction(()=>document.querySelector('.save-status')?.textContent==='进度已保存');
 await p.waitForTimeout(1700);s=await status(c);assert.equal(s.session.answers[first].answer,'A');
 await p.screenshot({path:out+'/blind-desktop.png',fullPage:true});
 const stale=s.session.revision;s=await unlock(c,s);
 assert.equal((await post(c,'draft',{sceneId,revision:stale,answers:{}})).status,409);
 const evidence=await post(c,'evidence',{instanceId:first});assert.equal(evidence.status,200);assert.equal(s.research.referenceAnswers.length,8);assert.ok(s.research.referenceAnswers.every(x=>s.research.items.some(i=>i.id===x.id)));assert.ok(evidence.data.machine.answer);assert.equal((await post(c,'evidence',{instanceId:future})).status,400);
 await p.reload();await p.locator('.scene-answer-feedback strong').nth(1).waitFor();assert.match(await p.locator('.scene-answer-feedback').innerText(),/机器候选答案/);assert.match(await p.locator('.scene-answer-feedback').innerText(),/已锁定/);
 await p.screenshot({path:out+'/answers-desktop.png',fullPage:true});await p.setViewportSize({width:390,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await p.screenshot({path:out+'/answers-mobile.png',fullPage:true});
 assert.equal((await post(c,'submit',body(s,{gt:{},gate2Answers:{},attestation:true}))).status,400);
 s=await finish(c,s);assert.equal(s.session.workflow.phase,'blind');assert.equal(s.session.workflow.sceneSequence.index,1);assert.equal(s.session.answers[first].answer,'A');assert.equal(s.session.workflow.gt[first].answer,'B');assert.equal((await post(c,'evidence',{instanceId:future})).status,400);
 assert.equal((await post(c,'draft',body(s,{sceneId,answers:{}}))).status,400);
 assert.equal((await post(c,'draft',body(s,{answers:{[first]:{...s.session.answers[first],answer:'D'}}}))).status,400);
 await p.reload();await p.locator('.scene-sequence .current').waitFor();assert.match(await p.locator('.scene-sequence .current').innerText(),new RegExp(s.research.assignment.scene_ids[0]));assert.equal(await p.locator('.scene-answer-feedback').count(),0);
 const recovered=await browser.newContext();let r=await post(recovered,'recover',{alias:s.session.alias,recoveryCode:code});assert.equal(r.status,200);s=r.data;assert.equal(s.session.workflow.sceneSequence.index,1);
 while(s.session.status!=='submitted'){s=await unlock(recovered,s);s=await finish(recovered,s);}
 assert.equal(s.session.workflow.sceneSequence.index,5);assert.equal(Object.keys(s.session.workflow.blind).length,40);assert.equal(Object.keys(s.session.workflow.gt).length,40);
 const exported=await (await recovered.request.get(url+'/api/demo/export')).json();assert.equal(Object.keys(exported.blind_responses).length,40);assert.equal(Object.keys(exported.workflow.sceneSequence.completed).length,5);assert.equal(exported.blind_responses[first].answer,'A');assert.equal(exported.machine_assisted_gt[first].answer,'B');fs.writeFileSync(out+'/receipt.json',JSON.stringify(exported));
 assert.equal((await post(recovered,'submit',{})).status,200);assert.equal((await post(recovered,'draft',{})).status,409);await recovered.close();
 const vc=await browser.newContext();await post(vc,'access',{invite});const catalog=await status(vc),assignment=catalog.catalog.assignments.find(a=>a.track==='offline_video');r=await post(vc,'start',{alias:'qa-scene-video-'+Date.now(),assignmentId:assignment.id,consent:true,priorExposure:false,recoveryCode:'SF-'+randomBytes(32).toString('base64url')});assert.equal(r.status,200);assert.equal(r.data.research.items.length,8);assert.ok(r.data.research.items.every(x=>x.media.length));const media=await vc.request.get(url+r.data.research.items[0].media[0].url);assert.ok(media.ok());assert.ok((await media.body()).length>2000);await vc.close();
 assert.deepEqual(errors,[]);console.log('PASS: five sequential scenes, 40 immutable blind answers, per-scene machine feedback, future API denial, autosave, recovery, complete receipt, video materials and mobile layout');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
