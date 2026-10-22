/* Uses the local current-batch review data; never calls model providers. */
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
(async () => {
  const browser = await chromium.launch({headless: true, args: ['--no-sandbox']});
  const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    const base = process.env.REVIEW_TEST_URL || 'http://127.0.0.1:8000';
    await page.goto(base + '/gpt50-live#GPT50_005');
    await page.waitForSelector('#scenarioGateStatus [data-gate3="reject"]');
    assert.match(await page.locator('#qualitySection').innerText(), /低于要求/);
    assert.ok((await page.locator('#qualitySection [lang="en"]').innerText()).length > 100);
    await page.locator('#showGateReasons').click();
    assert.equal(new URL(page.url()).hash, '#GPT50_005', 'in-page navigation must retain scenario ID');
    await page.selectOption('#gateFilter', 'rejected');
    assert.equal(await page.locator('#scenarios .scenario-button').count(), 9);
    assert.equal(await page.locator('#scenarios [data-gate3="reject"]').count(), 9);
    await page.selectOption('#gateFilter', 'errors');
    assert.equal(await page.locator('#scenarios .scenario-button').count(), 2);
    await page.locator('#scenarios [data-id="GPT50_015"]').click();
    await page.waitForSelector('#scenarioGateStatus [data-gate2="error"]');
    assert.match(await page.locator('#qualitySection').innerText(), /top_p/);
    assert.equal(await page.locator('#scenarioGateStatus [data-gate3="reject"]').count(), 0);
    await page.selectOption('#gateFilter', 'all');
    await page.locator('#scenarios [data-id="GPT50_035"]').click();
    await page.waitForFunction(() => document.querySelector('#scenarioGateStatus')?.textContent.includes('轨迹不完整'));
    await page.locator('#scenarios [data-id="GPT50_002"]').click();
    await page.waitForFunction(() => document.querySelector('#version')?.querySelector('option[value="invalid_horizon"]'));
    await page.selectOption('#version', 'invalid_horizon');
    assert.match(await page.locator('#qualitySection').innerText(), /历史记录没有本批 Gate3/);
    assert.equal(await page.locator('#scenarioGateStatus [data-gate3]').count(), 0);
    await page.setViewportSize({width: 390, height: 844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    assert.deepEqual(errors, []);
    console.log('Gate badges, rejection filters, reasons, partial/history boundaries and mobile layout passed.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
