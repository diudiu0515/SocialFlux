const {request,chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {randomBytes}=require('node:crypto');
const url=process.env.RESEARCH_QA_URL||'http://127.0.0.1:8017';
assert.match(url,/^http:\/\/127\.0\.0\.1:/);
const checkpoint=process.env.MEDIA_RECOVERY_CHECKPOINT||('/tmp/socialflux-av-browser/frozen-session-'+new URL(url).port+'.json');
async function post(context,action,data){const response=await context.post(url+'/api/demo/'+action,{data});const value=await response.json();assert.equal(response.status(),200,JSON.stringify(value));return value;}
(async()=>{
 if(process.argv[2]==='prepare'){
  const context=await request.newContext();
  try{
   await post(context,'access',{invite:'qa-human-gt-invite-20261022-abcdefghijklm'});
   const alias='qa-frozen-media-'+Date.now(),recoveryCode='SF-'+randomBytes(32).toString('base64url');
   let state=await post(context,'start',{alias,recoveryCode,assignmentId:'offline_video-01',priorExposure:false,consent:true});
   const first=state.questions[0].instance_id;
   state=await post(context,'draft',{revision:state.session.revision,answers:{[first]:{answer:'A',confidence:'medium',rationale:'QA frozen draft',issue:'none'}}});
   const receipt=await (await context.get(url+'/api/demo/export')).json();
   fs.mkdirSync('/tmp/socialflux-av-browser',{recursive:true});
   fs.writeFileSync(checkpoint,JSON.stringify({alias,recoveryCode,state,receipt}),{mode:0o600});
   console.log(JSON.stringify({prepared:true,dataset:state.dataset.sha256,questions:state.questions.length}));
  }finally{await context.dispose();}
 }else{
  assert.equal(process.argv[2],'verify');
  const frozen=JSON.parse(fs.readFileSync(checkpoint)),browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  try{
   const context=await browser.newContext(),page=await context.newPage();
   const state=await post(context.request,'recover',{alias:frozen.alias,recoveryCode:frozen.recoveryCode});
   assert.equal(state.dataset.sha256,frozen.state.dataset.sha256);
   assert.deepEqual(state.questions,frozen.state.questions);
   assert.deepEqual(state.research.assignment,frozen.state.research.assignment);
   assert.deepEqual(state.research.items,frozen.state.research.items);
   assert.deepEqual(state.session.answers,frozen.state.session.answers);
   const receipt=await (await context.request.get(url+'/api/demo/export')).json();
   assert.deepEqual(receipt.media_hashes,frozen.receipt.media_hashes);
   assert.equal(state.releaseInfo.isCurrent,false);
   await page.goto(url);await page.locator('#switch-latest-release').waitFor();
   assert.match(await page.getByRole('region',{name:'题库版本'}).innerText(),/旧版标注/);
   console.log(JSON.stringify({recovered:true,originalQuestions:state.questions.length,
     originalMediaRetained:true,draftRetained:true,latestVideoTotal:state.releaseInfo.latestVideoTotal}));
  }finally{await browser.close();}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
