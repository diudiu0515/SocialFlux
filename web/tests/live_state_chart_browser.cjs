/* Run with the existing local server and Playwright available in NODE_PATH. */
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
(async () => {
  const browser = await chromium.launch({headless: true, args: ['--no-sandbox']});
  const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  try {
    await page.goto((process.env.REVIEW_TEST_URL || 'http://127.0.0.1:8000') + '/gpt50-live#GPT50_003');
    await page.waitForSelector('#chartVariable');
    for (const group of ['emotion', 'behavioral_disposition', 'relationship', 'consequence_risk', 'dynamics']) {
      await page.locator(`[data-family="${group}"]`).click();
      const values = await page.evaluate(() => {
        const v = currentVersion(), model = chartSeries(v, detail.scenario, family);
        return {expected: model.series.length, ticks: model.ticks.length,
          lines: document.querySelectorAll('#chart [data-state-variable]').length,
          points: document.querySelectorAll('#chart circle').length,
          tableCells: document.querySelectorAll('#chart tbody td').length,
          invalid: /NaN|undefined/.test(document.querySelector('#chart svg').outerHTML)};
      });
      assert.equal(values.lines, values.expected);
      assert.equal(values.points, values.expected * values.ticks);
      assert.equal(values.tableCells, values.expected * (values.ticks + 1));
      assert.equal(values.invalid, false);
    }
    assert.match(await page.locator('#chart').innerText(), /全程重合/);
    await page.selectOption('#chartVariable', 'resource_scarcity');
    assert.equal(await page.locator('#chart [data-state-variable]').count(), 1);
    assert.equal(await page.locator('#chart circle').count(), 11);
    await page.selectOption('#chartVariable', '');
    await page.locator('#stateSection').screenshot({path: '/tmp/emotree-state-after.png'});
    await page.setViewportSize({width: 390, height: 844});
    await page.locator('#chart summary').click();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    assert.ok(await page.evaluate(() => {
      const chart = document.querySelector('#chart'); chart.scrollLeft = chart.scrollWidth;
      const last = [...chart.querySelectorAll('svg text')].find(n => n.textContent === 't10');
      return last.getBoundingClientRect().right <= chart.getBoundingClientRect().right;
    }), 'last turn remains accessible on narrow screens');
    assert.deepEqual(errors, []);
    console.log('Desktop/mobile state charts, overlap isolation and complete value tables passed.');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
