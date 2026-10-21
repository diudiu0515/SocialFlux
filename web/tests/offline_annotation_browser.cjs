const assert = require("node:assert/strict");
const {chromium} = require("playwright");

(async () => {
  const browser = await chromium.launch({headless: true, args: ["--no-sandbox"]});
  const page = await browser.newPage({viewport: {width: 1360, height: 900}});
  const base = process.env.ANNOTATION_TEST_URL || "http://127.0.0.1:8001";
  const errors = []; page.on("pageerror", error => errors.push(error.message));
  await page.goto(base + "/offline-annotation");
  await page.locator("#participant").fill("browser-test-" + Date.now());
  await page.locator("#assignmentScene").selectOption("GPT50_001");
  await page.locator("#priorExposure").selectOption("no");
  await page.locator("#startForm button").click();
  await page.locator("#submitJudgment").waitFor();
  assert.match(await page.locator("#phaseTitle").innerText(), /独立盲答/);
  assert.equal(await page.locator("#openPrivateEvidence").count(), 0);
  const token = await page.evaluate(() => JSON.parse(localStorage.getItem("socialflux-human-sessions"))[0].token);
  const api = async (action, extra = {}) => page.evaluate(async ({action, token, extra}) => {
    const response = await fetch("/api/offline-annotation/" + action, {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({token, ...extra})});
    return {status: response.status, body: await response.json()};
  }, {action, token, extra});
  const status = (await api("status")).body;
  assert.equal(status.counts.total, 6);
  const identity = status.items[0].instance_id;
  assert.equal((await api("evidence", {instance_id: identity})).status, 400);
  const publicRow = (await api("item", {instance_id: identity})).body;
  assert.equal(JSON.stringify(publicRow).includes("target_spec"), false);
  for (let i = 0; i < 6; i++) {
    await page.locator('input[name="answer"][value="A"]').check();
    await page.locator("#submitJudgment").click();
    await page.waitForFunction(expected => document.getElementById("sessionProgress").textContent.includes(`盲答 ${expected}`), i + 1);
  }
  assert.match(await page.locator("#phaseTitle").innerText(), /独立 GT 初判/);
  assert.equal((await api("blind", {instance_id: identity, answer: "B"})).status, 400);
  assert.equal((await api("machine", {instance_id: identity})).status, 400);
  await page.reload();
  await page.locator(".resume-button").first().click();
  await page.locator("#openPrivateEvidence").waitFor();
  for (let i = 0; i < 6; i++) {
    await page.locator("#openPrivateEvidence").click();
    await page.locator("#submitJudgment").waitFor();
    await page.locator('input[name="answer"][value="B"]').check();
    await page.locator("#judgmentRationale").fill("浏览器自动化测试记录，不是真实人工标注。");
    await page.locator("#submitJudgment").click();
    await page.waitForFunction(expected => document.getElementById("sessionProgress").textContent.includes(`独立初判 ${expected}`), i + 1);
  }
  assert.match(await page.locator("#phaseTitle").innerText(), /最终人工审核/);
  await page.locator("#openMachineSuggestion").click();
  await page.getByText("机器候选：", {exact: false}).waitFor();
  await page.locator('input[name="answer"][value="C"]').check();
  await page.locator("#humanAttestation").check();
  await page.locator("#submitJudgment").click();
  await page.waitForFunction(() => document.getElementById("sessionProgress").textContent.includes("最终审核 1"));
  const output = (await api("export")).body;
  assert.equal(output.blind_responses[identity].answer, "A");
  assert.equal(output.independent_private_judgments[identity].answer, "B");
  assert.equal(output.machine_assisted_final_judgments[identity].answer, "C");
  assert.equal(output.formal_ground_truth, false);
  await page.setViewportSize({width: 390, height: 844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS: six-question lock, private/machine stages, immutable answers, refresh resume, export, mobile");
})().catch(error => { console.error(error); process.exit(1); });
