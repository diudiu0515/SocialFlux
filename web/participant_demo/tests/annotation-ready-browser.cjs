const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {randomBytes,createHash}=require('node:crypto');
const url=process.env.RESEARCH_QA_URL||'http://127.0.0.1:8022';
assert.match(url,/^http:\/\/127\.0\.0\.1:/,'Only isolated local databases may be used');
const out=process.env.ANNOTATION_QA_OUTPUT||'/tmp/socialflux-annotation-ready';fs.mkdirSync(out,{recursive:true});
const invite='qa-human-gt-invite-20261022-abcdefghijklm';
const dimensions=['goal_achievement','state_adaptation','risk_management','recovery','relationship_outcome'];
async function post(c,action,data){const r=await c.request.post(url+'/api/demo/'+action,{data});return {status:r.status(),data:await r.json()};}
async function status(c){return (await c.request.get(url+'/api/demo/status')).json();}
function answer(task){return {values:Object.fromEntries(task.questions.map(q=>[q.id,Object.hasOwn(q.choices,'uncertain')?'uncertain':Object.hasOwn(q.choices,'unverifiable')?'unverifiable':Object.keys(q.choices)[0]])),rationale:'Isolated QA: uncertainty is preserved, not a quality pass.'};}
async function start(c,assignment){await post(c,'access',{invite});const code='SF-'+randomBytes(32).toString('base64url');
 const r=await post(c,'start',{alias:'qa-ready-'+randomBytes(8).toString('hex'),priorExposure:false,consent:true,assignmentId:assignment,recoveryCode:code});assert.equal(r.status,200,JSON.stringify(r.data));return {s:r.data,code};}
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const errors=[];const checks={};
 try{
  const tc=await browser.newContext({viewport:{width:1440,height:1000}});await post(tc,'access',{invite});
  const entry=await status(tc), catalog=entry.catalog, t4Assignment=catalog.assignments.find(a=>a.id==='t4-10')||catalog.assignments.find(a=>a.track==='t4');
  let r;
  if(t4Assignment){
  let {s:t,code}=await start(tc,t4Assignment.id);
  const originalRatings=Object.fromEntries(t.research.trajectories.map(x=>[x.id,Object.fromEntries(dimensions.map(d=>[d,{score:6,evidence_turn_ids:[x.packet.observable_trajectory[0].turn_id],rationale:'QA independent public-text score.',insufficient_evidence:false}]))]));
  assert.deepEqual(t.research.gate2Tasks,[]);assert.ok(t.research.trajectories.every(x=>!Object.hasOwn(x,'machine')));
  assert.equal((await post(tc,'submit',{revision:t.session.revision,ratings:{},attestation:true})).status,400);
  r=await post(tc,'draft',{revision:t.session.revision,ratings:originalRatings});assert.equal(r.status,200);t=r.data;
  const page=await tc.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto(url);
  await page.getByRole('navigation',{name:'轨迹导航',exact:true}).waitFor();
  assert.equal(await page.locator('[data-review-task]').count(),0);
  await page.getByRole('button',{name:'检查与提交',exact:true}).click();await page.locator('#research-attestation').check();
  await page.locator('#research-submit').click();await page.getByRole('heading',{name:'核对触发记录与实际视频。',exact:true}).waitFor();
  t=await status(tc);assert.equal(t.session.workflow.phase,'t4_review');assert.ok(t.session.workflow.ratingsLockedAt);
  assert.ok(t.research.gate2Tasks.length>=5);assert.ok(t.research.gate2Tasks.every(x=>x.kind.startsWith('T4-')));
  assert.ok(t.research.trajectories.every(x=>!Object.hasOwn(x,'machine')));
  assert.equal(await page.getByLabel('目标达成分数',{exact:true}).count(),0);
  const first=t.research.gate2Tasks[0], panel=page.locator('[data-review-task]').filter({has:page.locator('summary').filter({hasText:first.scene_id})}).first();
  await panel.locator('summary').first().click(); // details starts open; use attribute for a deterministic visible form.
  await panel.evaluate(el=>{el.open=true;});
  const firstInput=panel.locator('select').first();const selected=await firstInput.locator('option').nth(1).getAttribute('value');await firstInput.selectOption(selected);
  await panel.locator('textarea').fill('QA actual UI autosave after rating lock.');
  await page.waitForTimeout(1900);t=await status(tc);assert.ok(Object.keys(t.session.workflow.gate2.answers).length);
  const restored=await browser.newContext({viewport:{width:390,height:844}});
  r=await post(restored,'recover',{alias:t.session.alias,recoveryCode:code});assert.equal(r.status,200);t=r.data;
  assert.equal(t.session.workflow.phase,'t4_review');assert.deepEqual(t.session.workflow.ratings,originalRatings);
  assert.ok(Object.values(t.session.workflow.gate2.answers).some(x=>x.rationale.includes('actual UI')));
  const rp=await restored.newPage();rp.on('pageerror',e=>errors.push(e.message));await rp.goto(url);
  await rp.locator('[data-review-task]').first().waitFor();
  assert.ok(await rp.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await rp.screenshot({path:out+'/t4-review-mobile.png',fullPage:true});
  assert.equal((await post(restored,'submit',{revision:t.session.revision,ratings:originalRatings,gate2Answers:{},attestation:true})).status,400);
  const gate2Answers=Object.fromEntries(t.research.gate2Tasks.map(x=>[x.id,answer(x)]));
  const tampered=structuredClone(originalRatings);tampered[Object.keys(tampered)[0]].goal_achievement.score=0;
  const rev=t.session.revision;r=await post(restored,'draft',{revision:rev,ratings:tampered,gate2Answers});assert.equal(r.status,200);t=r.data;
  assert.deepEqual(t.session.workflow.ratings,originalRatings);
  assert.equal((await post(restored,'draft',{revision:rev,gate2Answers})).status,409);
  const videos=t.research.gate2Tasks.filter(x=>x.video);assert.ok(videos.length,'Fixed GPT T4 sample must expose exact-bound videos');
  for(const task of videos){const v=await restored.request.get(url+task.video.url);assert.equal(v.status(),200);assert.equal(createHash('sha256').update(await v.body()).digest('hex'),task.video.sha256);}
  r=await post(restored,'submit',{revision:t.session.revision,gate2Answers,attestation:true});assert.equal(r.status,200);t=r.data;
  assert.equal(t.session.workflow.phase,'complete');assert.ok(t.research.trajectories.every(x=>Object.hasOwn(x,'machine')));
  assert.equal((await post(restored,'draft',{revision:t.session.revision,ratings:{}})).status,409);
  assert.equal((await post(restored,'submit',{})).status,200);
  const t4export=await (await restored.request.get(url+'/api/demo/export')).json();fs.writeFileSync(out+'/t4-export.json',JSON.stringify(t4export));
  assert.deepEqual(t4export.independent_t4_ratings,originalRatings);assert.equal(Object.keys(t4export.gate2_human_review.answers).length,Object.keys(gate2Answers).length);
  checks.t4={trajectories:t.research.trajectories.length,tasks:Object.keys(gate2Answers).length,verifiedVideos:videos.length,lockedRatings:true,recovery:true,finalExport:true};
  checks.online={enabled:true,t4WorkflowTested:true};await restored.close();
  }else{
    assert.equal(catalog.scope,'offline');assert.equal(catalog.textScenes,50);assert.equal(catalog.textCount,400);assert.equal(catalog.mediaCount,150);
    assert.ok(catalog.assignments.every(a=>['offline_text','offline_video'].includes(a.track)&&a.item_ids.length===40));
    r=await post(tc,'start',{alias:'qa-online-disabled-'+randomBytes(8).toString('hex'),priorExposure:false,consent:true,assignmentId:'t4-10',recoveryCode:'SF-'+randomBytes(32).toString('base64url')});assert.equal(r.status,400);
    assert.equal((await status(tc)).session,null);
    const entryPage=await tc.newPage();entryPage.on('pageerror',e=>errors.push(e.message));await entryPage.goto(url);await entryPage.locator('#research-track').waitFor();
    assert.deepEqual(await entryPage.locator('#research-track option').evaluateAll(options=>options.map(x=>x.value)),['offline_video','offline_text']);
    assert.deepEqual(await entryPage.locator('.facts strong').allTextContents(),['50','400','150']);
    assert.doesNotMatch(await entryPage.locator('.intro').innerText(),/T4|Claude|五维评分/);
    checks.scope={scope:'offline',scenes:catalog.textScenes,questions:catalog.textCount,uniqueMedia:catalog.mediaCount};
    checks.online={enabled:false,newT4Rejected:true,t4WorkflowTested:false};
  }
  await tc.close();

  const oc=await browser.newContext({viewport:{width:1440,height:1000}});let {s:o}=await start(oc,'offline_video-01');
  const blind=Object.fromEntries(o.research.items.map(x=>[x.id,{answer:'A',confidence:'medium',rationale:'QA',issue:'none'}]));
  r=await post(oc,'lock',{revision:o.session.revision,answers:blind});assert.equal(r.status,200);o=r.data;
  assert.equal(o.session.workflow.phase,'gate2');assert.ok(o.research.gate2Tasks.every(x=>x.stage==='independent'));
  assert.equal((await post(oc,'evidence',{instanceId:o.research.items[0].id})).status,400);
  r=await post(oc,'gate2-lock',{revision:o.session.revision,gate2Answers:Object.fromEntries(o.research.gate2Tasks.map(x=>[x.id,answer(x)]))});assert.equal(r.status,200);o=r.data;
  const media=o.research.gate2Tasks.filter(x=>x.kind==='media-quality');assert.equal(media.length,15);assert.equal(new Set(media.map(x=>x.video.sha256)).size,15);
  assert.ok(o.research.gate2Tasks.every(x=>!x.kind.startsWith('T4-')));
  const op=await oc.newPage();op.on('pageerror',e=>errors.push(e.message));await op.goto(url);
  await op.getByRole('button',{name:/场景与 rollout 核对/}).click();
  const mp=op.locator('[data-review-task]').filter({has:op.locator('summary').filter({hasText:'音视频质量'})}).first();await mp.evaluate(el=>{el.open=true;});
  const video=mp.locator('video');await video.evaluate(v=>v.play());await op.waitForFunction(()=>[...document.querySelectorAll('.gate2-task video')].some(v=>v.currentTime>.2));await video.evaluate(v=>v.pause());
  await op.screenshot({path:out+'/offline-media-review-desktop.png',fullPage:true});
  const gt=Object.fromEntries(o.research.items.map(x=>[x.id,{answer:'A',acceptable_answers:['A'],decision:'usable',rationale:'QA machine-assisted review.'}]));
  const allReviews=Object.fromEntries(o.research.gate2Tasks.map(x=>[x.id,o.session.workflow.gate2.answers[x.id]||answer(x)]));
  const missingMedia={...allReviews};delete missingMedia[media[0].id];
  assert.equal((await post(oc,'submit',{revision:o.session.revision,gt,gate2Answers:missingMedia,attestation:true})).status,400);
  r=await post(oc,'submit',{revision:o.session.revision,gt,gate2Answers:allReviews,attestation:true});assert.equal(r.status,200);o=r.data;
  assert.deepEqual(o.session.workflow.blind,blind);
  fs.writeFileSync(out+'/offline-export.json',JSON.stringify(await (await oc.request.get(url+'/api/demo/export')).json()));
  checks.offline={questions:o.research.items.length,uniqueMediaReviews:media.length,requiresAllMedia:true,videoPlayed:true};
  const textc=await browser.newContext();const {s:tx}=await start(textc,'offline_text-01');
  assert.ok(tx.research.items.every(x=>x.media.length===0));assert.deepEqual(tx.research.gate2Tasks,[]);
  assert.deepEqual(errors,[]);fs.writeFileSync(out+'/result.json',JSON.stringify({ok:true,checks,errors},null,2));console.log(JSON.stringify({ok:true,checks,output:out}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
