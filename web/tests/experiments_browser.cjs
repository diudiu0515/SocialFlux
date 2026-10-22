const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1400,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto((process.env.REVIEW_TEST_URL||'http://127.0.0.1:8000')+'/experiments');
  await page.waitForSelector('#gates article');
  assert.equal(await page.locator('#gates article').count(),4);
  assert.equal(await page.locator('#gate2Table tbody tr').count(),9);
  assert.match(await page.locator('#offline').innerText(),/300 题/);
  assert.match(await page.locator('#offline').innerText(),/正式准入 0 题/);
  // A newly queued cohort has no outcomes yet; inspect the preceding run too.
  await page.locator('#t4 > details').first().locator('summary').first().click();
  assert.match(await page.locator('#t4').innerText(),/N\/A/);
  assert.match(await page.locator('#t4').innerText(),/移交|不支持视频|未收到视频/);
  assert.ok(await page.locator('[data-run]').count()>=3);
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
  await page.screenshot({path:'/tmp/socialflux-experiments-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,checks:['four gates','E1-E9','current bank','separate runs','N/A and denominators','failure counts','mobile layout']}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
