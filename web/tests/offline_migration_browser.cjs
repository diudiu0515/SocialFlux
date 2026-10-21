const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1300,height:1000}});
  const errors=[],refs=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(new URL(r.url()).pathname.endsWith('/reference'))refs.push(r.url());});
  const base=process.env.REVIEW_TEST_URL||'http://127.0.0.1:8000';
  try{
    await page.goto(base+'/offline-review?bank=dev60#SFO-002');
    await page.waitForSelector('#revealReference');
    assert.equal(refs.length,0);
    assert.match(await page.locator('#bankMeta').innerText(),/新版适配已机器复核/);
    const response=await page.request.get(base+'/api/offline-review/SFO-002?bank=dev60');
    const publicData=await response.json();
    assert.equal(publicData.metadata.migration_level,'metadata_only');
    for(const key of ['blind_answer','best_answer','migration_review'])assert.ok(!JSON.stringify(publicData).includes('"'+key+'"'));
    await page.locator('#advancedFilters summary').click();
    await page.selectOption('#migrationFilter','metadata_only');
    assert.ok(await page.locator('#itemNav button').count()>0);
    assert.equal(await page.locator('#itemNav [data-id="SFO-001"]').count(),0);
    await page.click('#revealReference');
    await page.waitForSelector('#referenceBody table');
    assert.match(await page.locator('#referenceBody').innerText(),/新版任务适配 · API 机器复核/);
    assert.match(await page.locator('#referenceBody').innerText(),/不替代人工核验/);
    await page.selectOption('#migrationFilter','substantive');
    await page.locator('[data-id="SFO-001"]').click();
    await page.waitForSelector('#revealReference');
    assert.equal(await page.locator('#referenceBody').innerText(),'');
    const catalog=await (await page.request.get(base+'/api/offline-review?bank=dev60')).json();
    const pending=catalog.items.filter(i=>i.migration_status==='pending');
    assert.equal(catalog.summary.migration_pending,pending.length);
    await page.selectOption('#migrationFilter','pending');
    assert.equal(await page.locator('#itemNav button').count(),pending.length);
    if(pending.length){
      await page.locator(`[data-id="${pending[0].instance_id}"]`).click();
      await page.waitForSelector('#revealReference');
      await page.click('#revealReference');
      await page.waitForSelector('#referenceBody table');
      assert.match(await page.locator('#referenceBody').innerText(),/接口失败或超时不代表题目不合格/);
    }
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,checks:['migration filter','pending is not rejection','review version binding','no default answer exposure','review opt-in','existing question preserved']}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
