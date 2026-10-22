const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const fs=require('node:fs');
const url=process.env.RESEARCH_QA_URL||'http://127.0.0.1:8017';
assert.match(url,/^http:\/\/127\.0\.0\.1:/);
const out='/tmp/socialflux-av-browser';fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(url+'/#invite=qa-human-gt-invite-20261022-abcdefghijklm');
  await page.locator('#alias').fill('qa-av-'+Date.now());
  await page.locator('#research-track').selectOption('offline_video');
  await page.locator('#exposure').selectOption('no');await page.locator('#consent').check();
  await page.getByRole('button',{name:'进入标注空间',exact:true}).click();
  await page.locator('#issued-recovery').waitFor();await page.getByRole('button',{name:/我已保存/}).click();
  await page.locator('video').first().waitFor();
  const state=await (await context.request.get(url+'/api/demo/status')).json();
  assert.equal(state.research.assignment.track,'offline_video');
  assert.equal(state.questions.length,8*state.research.assignment.scene_ids.length);
  const media=new Map(state.research.items.flatMap(x=>x.media).map(x=>[x.sha256,x]));
  for(const [sha,asset] of media){
   const response=await context.request.get(url+asset.url);assert.equal(response.status(),200);
   assert.equal(createHash('sha256').update(await response.body()).digest('hex'),sha);
   assert.equal(asset.audio_required,true);assert.equal(asset.speech_language,'en');
  }
  const clip=page.locator('video').first();
  await clip.evaluate(v=>v.play());
  await page.waitForFunction(()=>document.querySelector('video')?.currentTime>.3);
  const playback=await clip.evaluate(v=>({muted:v.muted,volume:v.volume,error:v.error?.code,
    ready:v.readyState,width:v.videoWidth,audioBytes:v.webkitAudioDecodedByteCount}));
  assert.equal(playback.muted,false);assert.ok(playback.volume>0);assert.ok(playback.width>0);
  assert.equal(playback.error,undefined);assert.ok(playback.ready>=2);
  if(playback.audioBytes!==undefined)assert.ok(playback.audioBytes>0);
  await clip.evaluate(v=>v.pause());
  const evidence=await context.request.post(url+'/api/demo/evidence',{data:{instanceId:state.research.items[0].id}});
  assert.equal(evidence.status(),400);
  assert.equal(await page.getByRole('navigation',{name:'场景内任务',exact:true}).getByRole('button').count(),8);
  await page.screenshot({path:out+'/desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:out+'/mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({ok:true,sceneCount:state.research.assignment.scene_ids.length,
    questionCount:state.questions.length,verifiedMedia:media.size,playback,output:out}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
