const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1400,height:1000}});
  const errors=[],refs=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(new URL(r.url()).pathname.endsWith('/reference'))refs.push(r.url());});
  const base=process.env.REVIEW_TEST_URL||'http://127.0.0.1:8000';
  try{
    await page.goto(base+'/offline-demo');await page.waitForSelector('#revealReference');
    assert.equal(await page.locator('#bankSelect').inputValue(),'scenarios-v2');
    assert.equal(await page.locator('#itemNav button').count(),300);
    assert.equal(await page.locator('#sceneFilter option').count(),51);
    assert.match(await page.locator('#bankMeta').innerText(),/270 题有配对视频 · 30 题缺少视频/);
    assert.equal(refs.length,0);
    await page.locator('#advancedFilters summary').click();
    await page.selectOption('#statusFilter','machine_concerns');
    assert.equal(await page.locator('#itemNav button').count(),138);
    await page.selectOption('#statusFilter','');
    await page.locator('#advancedFilters summary').click();
    await page.selectOption('#sceneFilter','GPT50_050');
    assert.equal(await page.locator('#itemNav button').count(),6);
    assert.match(await page.locator('#sceneCoverage').innerText(),/T1 2 题 \/ T2 2 题 \/ T3 2 题/);
    for(const task of ['T1','T2','T3']){
      await page.selectOption('#taskFilter',task);assert.equal(await page.locator('#itemNav button').count(),2);
    }
    await page.locator('#itemNav button').first().click();await page.waitForSelector('.candidate');
    assert.deepEqual(await page.locator('.candidate strong').allTextContents(),['行动 1','行动 2']);
    await page.locator('input[name=answer][value=B]').check();assert.equal(await page.locator('#modelAnswer').innerText(),'{"answer":"B"}');
    assert.equal(await page.locator('#humanReviewFields').getAttribute('open'),null);
    await page.click('#revealReference');await page.waitForSelector('#referenceBody table');
    assert.match(await page.locator('#referenceBody').innerText(),/API 盲试答/);
    await page.selectOption('#sceneFilter','GPT50_001');await page.selectOption('#taskFilter','T2');
    await page.locator('#itemNav button').first().click();await page.waitForSelector('#sharedEnding');
    assert.equal(await page.locator('[data-history]').count(),2);assert.equal(await page.locator('#sharedEnding').count(),1);
    assert.equal(await page.locator('#referenceBody').innerText(),'');
    await page.selectOption('#modality','text+video');await page.waitForFunction(()=>document.querySelector('video')?.readyState>=1);
    assert.match(await page.locator('#mediaClips').innerText(),/A\/B 共用同一段未改写前史视频/);
    assert.match(await page.locator('#mediaClips').innerText(),/尚无对应视频：共同结尾/);
    assert.match(await page.locator('#mediaClips').innerText(),/不朗读题中台词/);
    await page.selectOption('#sceneFilter','GPT50_005');
    await page.locator('#itemNav button').first().click();await page.waitForSelector('#sharedEnding');
    await page.selectOption('#modality','text+video');
    assert.equal(await page.locator('video').count(),0);
    assert.match(await page.locator('#mediaClips').innerText(),/没有与当前题目版本匹配的配对视频/);
    await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
    await page.goto(base+'/gpt50-live#GPT50_050');await page.waitForSelector('#showOfflineTasks');
    assert.equal(await page.locator('#showOfflineTasks').getAttribute('href'),'/offline-demo?scene=GPT50_050');
    await page.click('#showOfflineTasks');await page.waitForSelector('#itemNav button');
    assert.equal(await page.locator('#sceneFilter').inputValue(),'GPT50_050');
    assert.equal(await page.locator('#itemNav button').count(),6);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,items:300,scenes:50,checks:['default bank','scene filters','two per task','minimal answer','shared T2 expression','reference isolation','retained media','mobile layout']}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
