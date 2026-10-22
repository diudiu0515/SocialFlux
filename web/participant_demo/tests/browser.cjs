const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('playwright');
(async()=>{
 const {url,invite,output}=JSON.parse(fs.readFileSync(0,'utf8'));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const one=await browser.newContext({viewport:{width:1440,height:1000}});const page=await one.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const call=(p,action,body)=>p.evaluate(async({action,body})=>{const r=await fetch('/api/demo/'+action,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return {status:r.status,body:await r.json()};},{action,body});
 try {
  await page.goto(url);await page.getByText('准备好你的独立判断').waitFor();assert.equal((await call(page,'status')).body.questions,undefined);
  assert.equal((await call(page,'export')).status,401);assert.equal((await call(page,'access',{invite:'bad'})).status,403);
  await page.goto(url+'/#invite='+invite);await page.reload();await page.locator('button.primary').waitFor();await page.waitForFunction(()=>!document.querySelector('button.primary')?.disabled);
  await page.screenshot({path:output+'/welcome-desktop.png',fullPage:true});
  const alias='qa-'+Date.now();await page.locator('#alias').fill(alias);await page.locator('#exposure').selectOption('no');await page.locator('#consent').check();await page.getByRole('button',{name:'进入标注空间'}).click();
  await page.locator('#issued-recovery').waitFor();const recovery=await page.locator('#issued-recovery').inputValue();assert.match(recovery,/^SF-/);
  await page.getByRole('button',{name:'我已保存，开始第 1 题'}).click();await page.locator('#save-next').waitFor();
  const initial=(await call(page,'status')).body;assert.equal(initial.questions.length,6);assert.equal(JSON.stringify(initial).includes('target_spec'),false);assert.equal(JSON.stringify(initial).includes('recoveryCode'),false);
  await page.locator('label:has(input[name="answer"][value="A"])').click();await page.locator('label:has(input[name="confidence"][value="medium"])').click();await page.locator('#save-next').click();await page.waitForFunction(()=>document.querySelector('.question-pill')?.textContent?.includes('02'));
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:output+'/question-mobile.png',fullPage:true});
  const two=await browser.newContext({viewport:{width:1440,height:1000}});const resume=await two.newPage();resume.on('pageerror',e=>errors.push(e.message));await resume.goto(url);
  await resume.getByRole('button',{name:'恢复进度',exact:true}).click();await resume.locator('#alias').fill(alias);await resume.locator('#recovery-code').fill(recovery);await resume.getByRole('button',{name:'恢复我的标注'}).click();await resume.locator('#save-next').waitFor();
  const restored=(await call(resume,'status')).body;assert.equal(restored.session.id,initial.session.id);assert.equal(restored.session.answers[initial.questions[0].instance_id].answer,'A');
  assert.equal((await call(resume,'recover',{alias:'wrong',recoveryCode:recovery})).status,401);
  assert.equal((await call(resume,'draft',{revision:restored.session.revision,answers:{[initial.questions[0].instance_id]:{answer:'Z'}}})).status,400);
  assert.equal((await call(resume,'submit',{revision:restored.session.revision,answers:restored.session.answers,attestation:true})).status,400);
  await resume.locator('label:has(input[name="answer"][value="B"])').click();await resume.locator('label:has(input[name="confidence"][value="low"])').click();await resume.locator('#save-next').click();await resume.waitForFunction(()=>document.querySelector('.question-pill')?.textContent?.includes('03'));
  assert.equal((await call(page,'draft',{revision:restored.session.revision,answers:{}})).status,409);
  await resume.screenshot({path:output+'/comparison-desktop.png',fullPage:true});
  for(let i=2;i<6;i++) {await resume.locator('label:has(input[name="answer"][value="A"])').click();await resume.locator('label:has(input[name="confidence"][value="high"])').click();await resume.locator('#save-next').click();if(i<5)await resume.waitForFunction(n=>document.querySelector('.question-pill')?.textContent?.includes(n),String(i+2).padStart(2,'0'));else await resume.locator('#submit-all').waitFor();}
  await resume.getByRole('button',{name:/01 证据判断/}).click();await resume.locator('#save-next').waitFor();assert.equal(await resume.locator('input[name="answer"][value="A"]').isChecked(),true);await resume.getByRole('button',{name:/检查提交/}).click();
  await resume.locator('#attestation').check();await resume.locator('#submit-all').click();await resume.getByText('你的判断，已妥善保存。').waitFor();
  const submitted=(await call(resume,'status')).body;assert.equal(submitted.session.status,'submitted');assert.equal((await call(resume,'draft',{answers:submitted.session.answers,revision:submitted.session.revision})).status,409);
  const repeat=await call(resume,'submit',{answers:submitted.session.answers,revision:submitted.session.revision,attestation:true});assert.equal(repeat.body.session.id,submitted.session.id);assert.equal(repeat.body.session.submittedAt,submitted.session.submittedAt);
  const exported=await call(resume,'export');assert.equal(exported.body.receipt_id,submitted.session.id);assert.equal(exported.body.formal_ground_truth,false);assert.equal(exported.body.user_id,undefined);assert.equal(exported.body.recovery_code,undefined);assert.equal(Object.keys(exported.body.answers).length,6);
  await resume.reload();await resume.getByText('你的判断，已妥善保存。').waitFor();await resume.setViewportSize({width:360,height:780});assert.equal(await resume.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await resume.screenshot({path:output+'/receipt-mobile.png',fullPage:true});
  assert.equal((await resume.request.get(url+'/api/lab/records')).status(),404);
  assert.deepEqual(errors,[]);fs.writeFileSync(output+'/browser.json',JSON.stringify({passed:true,checks:['anonymous invitation','public-only projection','cross-device resume','invalid recovery','invalid choice','incomplete submission','revision conflict','all six questions','review navigation','durable submission','idempotent retry','submission lock','own-record export','private routes absent','mobile overflow','no browser exceptions']},null,2));
  console.log('Browser checks passed: 16 flows; desktop 1440px and mobile 390px/360px.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
