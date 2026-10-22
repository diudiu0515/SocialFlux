const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const url=process.env.RESEARCH_QA_URL||'http://127.0.0.1:8014';
assert.match(url,/^http:\/\/127\.0\.0\.1:/,'Only isolated local D1 is allowed');
const invite='qa-human-gt-invite-20261022-abcdefghijklm';
const out='/tmp/socialflux-release-browser';fs.mkdirSync(out,{recursive:true});
async function post(c,action,data){const r=await c.request.post(url+'/api/demo/'+action,{data});assert.equal(r.status(),200,await r.text());return r.json();}
async function status(c){return (await c.request.get(url+'/api/demo/status')).json();}
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const c=await browser.newContext({viewport:{width:390,height:844}}),page=await c.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await post(c,'access',{invite});
  let old=await post(c,'recover',{alias:'qa-research-v3',recoveryCode:'SF-'+'R'.repeat(43)});
  assert.equal(old.questions.length,30);assert.equal(old.releaseInfo.currentTotal,300);
  assert.equal(old.releaseInfo.latestTotal,400);assert.equal(old.releaseInfo.latestQuestionsPerScene,8);
  assert.equal(old.releaseInfo.isCurrent,false);
  await page.goto(url);await page.locator('#switch-latest-release').waitFor();
  assert.match(await page.getByRole('region',{name:'题库版本'}).innerText(),/旧版标注.*300/s);
  assert.match(await page.getByRole('region',{name:'题库版本'}).innerText(),/最新题库已更新为 400 题/);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:out+'/old-release-mobile.png',fullPage:true});
  // Enter a fresh answer and switch immediately, before the autosave timer fires.
  await page.locator('label.option').filter({has:page.locator('input[value=A]')}).click();
  await page.getByLabel('把握程度',{exact:true}).selectOption('medium');
  await page.locator('#switch-latest-release').click();
  await page.locator('#research-track').waitFor();assert.equal(await page.locator('#alias').inputValue(),'qa-research-v3');
  await page.locator('#research-track').selectOption('offline_text');
  assert.match(await page.locator('#research-assignment option:checked').innerText(),/40 项/);
  const check=await browser.newContext();
  const preserved=await post(check,'recover',{alias:'qa-research-v3',recoveryCode:'SF-'+'R'.repeat(43)});
  assert.equal(preserved.dataset.sha256,old.dataset.sha256);assert.equal(preserved.questions.length,30);
  assert.equal(preserved.session.answers[old.questions[0].instance_id].answer,'A');await check.close();
  await page.locator('#exposure').selectOption('no');await page.locator('#consent').check();
  await page.getByRole('button',{name:'进入标注空间',exact:true}).click();await page.locator('#issued-recovery').waitFor();
  const newRecovery=await page.locator('#issued-recovery').inputValue();assert.notEqual(newRecovery,'SF-'+'R'.repeat(43));
  await page.getByRole('button',{name:/我已保存/}).click();await page.locator('label.option').first().waitFor();
  const latest=await status(c);assert.equal(latest.releaseInfo.currentTotal,400);assert.equal(latest.releaseInfo.assignedCount,40);
  assert.equal(latest.releaseInfo.isCurrent,true);assert.equal(latest.questions.length,40);
  assert.deepEqual(latest.session.answers,{});assert.equal(latest.session.workflow.baselineEligible,false);
  assert.equal(await page.locator('#switch-latest-release').count(),0);
  assert.equal(await page.getByRole('navigation',{name:'场景内任务',exact:true}).getByRole('button').count(),8);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:out+'/latest-release-mobile.png',fullPage:true});
  for(const [alias,char,total] of [['qa-legacy','L',6],['qa-media','M',270]]){
   const legacy=await browser.newContext();await post(legacy,'recover',{alias,recoveryCode:'SF-'+char.repeat(43)});
   const lp=await legacy.newPage();await lp.goto(url);await lp.locator('#switch-latest-release').waitFor();
   assert.equal((await status(legacy)).releaseInfo.currentTotal,total);await legacy.close();
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({ok:true,checks:['old/new totals','save before switch','old recovery preserved','new 40-question assignment','8 questions per scene','no answer transfer','exposure exclusion','legacy entry points','mobile layout'],output:out}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
