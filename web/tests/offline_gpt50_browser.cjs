/* New-bank routing and draft continuity while the cohort grows; no model calls. */
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const base = process.env.REVIEW_TEST_URL || 'http://127.0.0.1:8000';
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  const context = await browser.newContext();
  const page = await context.newPage(), errors=[];
  page.on('pageerror', error => errors.push(error.message));
  try {
    const catalog = await (await context.request.get(base+'/api/offline-review?bank=gpt50-t1-t3')).json();
    assert(catalog.items.length>0);
    assert(catalog.items.every(item => ['T1','T3'].includes(item.task)));
    const id=catalog.items[0].instance_id;
    const detail=await (await context.request.get(base+'/api/offline-review/'+id+'?bank=gpt50-t1-t3')).json();
    // Pin one coherent read-only view so active generation cannot race the test.
    detail.bank_sha256=catalog.bank_sha256;
    catalog.items.find(item=>item.instance_id===id).item_sha256=detail.metadata.item_sha256;
    let revision=0, changed=false;
    await page.route(/\/api\/offline-review(?:\/|\?|$)/,async route=>{
      const url=new URL(route.request().url());
      if(url.searchParams.get('bank')!=='gpt50-t1-t3')return route.continue();
      const payload=structuredClone(url.pathname==='/api/offline-review'?catalog:detail);
      payload.bank_sha256='test-growing-bank-'+revision;
      if(changed){
        if(payload.items)payload.items.find(item=>item.instance_id===id).item_sha256='changed-question';
        else payload.metadata.item_sha256='changed-question';
      }
      await route.fulfill({json:payload});
    });
    await page.goto(base+'/offline-review#'+id);
    await page.waitForSelector('input[name=answer]');
    assert.equal(await page.locator('#bankSelect').inputValue(),'gpt50-t1-t3');
    await page.locator('input[name=answer][value=B]').check();
    revision++;
    await page.reload();
    await page.waitForSelector('input[name=answer]');
    assert(await page.locator('input[name=answer][value=B]').isChecked(),'bank append must preserve unchanged item draft');
    changed=true;revision++;
    await page.reload();
    await page.waitForSelector('input[name=answer]');
    assert.equal(await page.locator('input[name=answer]:checked').count(),0);
    assert.match(await page.locator('#message').innerText(),/旧版草稿已保留/);
    await page.fill('#reviewer','browser-test');
    const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('socialflux-offline-choice-review:offline_gpt50_t1_t3')));
    assert.equal(Object.values(saved.stale_annotations)[0].answer,'B');
    await page.selectOption('#bankSelect','dev60');
    await page.waitForSelector('#itemNav button');
    assert.equal(await page.locator('#itemNav button').count(),60);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,checks:['GPT50 default and bank selection','unchanged draft survives append','changed draft archived','old60 retained']}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
