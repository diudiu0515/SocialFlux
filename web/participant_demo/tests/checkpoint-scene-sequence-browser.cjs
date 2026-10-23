/* Final scene-sequence candidate QA; local D1 only, no production requests. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {gunzipSync} = require('node:zlib');
const {createHash, randomBytes} = require('node:crypto');
const root = path.resolve(__dirname, '../../..');
const site = path.resolve(process.env.CHECKPOINT_SITE || path.join(root, 'build/annotation-checkpoint-integration-20261023/hosted-site-cached'));
const out = path.resolve(process.env.CHECKPOINT_SEQUENCE_OUTPUT || path.join(root, 'build/annotation-checkpoint-integration-20261023/browser-scene-sequence'));
const url = process.env.CHECKPOINT_QA_URL || 'http://127.0.0.1:8134';
assert.match(url, /^http:\/\/127\.0\.0\.1:\d+$/, 'Use isolated local D1 only');
const invite = 'qa-human-gt-invite-20261022-abcdefghijklm';
const read = file => JSON.parse(fs.readFileSync(file));
const unpack = file => JSON.parse(gunzipSync(Buffer.from(read(file).gzip_base64, 'base64')));
const data = unpack(path.join(site, 'data/research-server.json'));
const assignment = data.assignments.find(x => x.id === 'offline_video-01');
const assigned = data.items.filter(x => assignment.item_ids.includes(x.id));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const norm = text => text.replace(/\s+/g, ' ').trim();
const report = {url, site, localOnly: true, testedAt: new Date().toISOString(), checks: [], videos: [], pageErrors: [], passed: false};
fs.mkdirSync(out, {recursive: true});
let browser;
function runtime() {
  for (const base of [process.env.PLAYWRIGHT_MODULE, 'playwright', ...fs.readdirSync('/tmp').filter(x => x.startsWith('emotree-browser-')).map(x => '/tmp/' + x + '/node_modules/playwright')].filter(Boolean)) {
    try {
      const module = require(base), browsers = path.resolve(path.dirname(require.resolve(base)), '../../browsers');
      const executable = [process.env.CHROMIUM_EXECUTABLE, module.chromium.executablePath(), ...fs.existsSync(browsers) ? fs.readdirSync(browsers).filter(x => x.startsWith('chromium-')).map(x => path.join(browsers, x, 'chrome-linux64/chrome')) : []].find(x => x && fs.existsSync(x));
      if (executable) return {chromium: module.chromium, executable};
    } catch {}
  }
  throw new Error('Existing browser unavailable; no download attempted');
}
async function post(context, action, data) {const response = await context.request.post(url + '/api/demo/' + action, {data}); return {status: response.status(), data: await response.json()};}
async function get(context, action) {const response = await context.request.get(url + '/api/demo/' + action); assert.equal(response.status(), 200); return response.json();}
const body = (state, values = {}) => ({revision: state.session.revision, sceneId: state.session.workflow.sceneSequence.scenes[state.session.workflow.sceneSequence.index]?.id, ...values});
function votes(tasks, old = {}) {return Object.fromEntries(tasks.map(task => [task.id, old[task.id] || {values: Object.fromEntries(task.questions.map(q => [q.id,
  q.id === 'playback' && Object.hasOwn(q.choices, 'partial') ? 'partial' : ['uncertain', 'unavailable', 'unverifiable'].find(key => Object.hasOwn(q.choices, key)) || Object.keys(q.choices)[0]])), rationale: 'Synthetic local QA only; no human quality approval.'}]));}
async function checked(name, action) {const detail = await action(); report.checks.push({name, passed: true, detail}); console.log(JSON.stringify({check: name, passed: true}));}
async function pageFor(context) {const page = await context.newPage(); page.on('pageerror', e => report.pageErrors.push(e.message)); await page.goto(url, {waitUntil: 'networkidle'}); return page;}
function assertNoFuture(value, sequence, label) {
  const allowedScenes = new Set(sequence.scenes.slice(0, sequence.index + 1).map(x => x.id));
  const serialized = JSON.stringify(value);
  for (const item of assigned.filter(x => !allowedScenes.has(x.scene_id))) for (const media of item.media) {
    assert.ok(!serialized.includes(media.sha256), `${label} exposes future media SHA ${media.node_id}`);
    assert.ok(!serialized.includes(media.full_public_response), `${label} exposes future complete reply ${media.node_id}`);
  }
}
async function assertScope(context, state) {
  const sequence = state.session.workflow.sceneSequence, current = sequence.scenes[sequence.index];
  assert.equal(state.research.items.length, 8); assert.equal(state.questions.length, 8);
  assert.ok(state.research.items.every(x => x.scene_id === current.id));
  assert.deepEqual(state.research.assignment.scene_ids, [current.id]);
  assert.equal(state.research.referenceAnswers.length, state.session.workflow.phase === 'gt' ? 8 : 0);
  assert.ok(state.research.referenceAnswers.every(x => current.itemIds.includes(x.id)));
  assertNoFuture(state, sequence, 'status');
  const exported = await get(context, 'export'); assertNoFuture(exported, sequence, 'export');
  const visibleIds = sequence.scenes.slice(0, sequence.index + 1).flatMap(x => x.itemIds);
  assert.deepEqual(new Set(Object.keys(exported.media_hashes)), new Set(visibleIds));
  return {scene: current.id, index: sequence.index, phase: state.session.workflow.phase, exportedMediaRows: Object.keys(exported.media_hashes).length};
}
async function unlock(context, state) {
  const answers = Object.fromEntries(state.research.items.map(x => [x.id, state.session.answers[x.id] || {answer: 'A', confidence: 'medium', rationale: 'Synthetic local QA.', issue: 'none'}]));
  let response = await post(context, 'lock', body(state, {answers})); assert.equal(response.status, 200, JSON.stringify(response.data)); state = response.data;
  if (state.session.workflow.phase === 'gate2') {response = await post(context, 'gate2-lock', body(state, {gate2Answers: votes(state.research.gate2Tasks)})); assert.equal(response.status, 200, JSON.stringify(response.data)); state = response.data;}
  assert.equal(state.session.workflow.phase, 'gt'); return state;
}
async function finish(context, state) {
  const gt = Object.fromEntries(state.research.items.map(x => [x.id, {answer: null, acceptable_answers: [], decision: 'reject', rationale: 'Synthetic QA only, not a human GT judgment.'}]));
  const response = await post(context, 'submit', body(state, {gt, gate2Answers: votes(state.research.gate2Tasks, state.session.workflow.gate2.answers), attestation: true}));
  assert.equal(response.status, 200, JSON.stringify(response.data)); return response.data;
}
async function run() {
  const available = runtime(); browser = await available.chromium.launch({headless: true, executablePath: available.executable, args: ['--no-sandbox', '--disable-gpu', '--autoplay-policy=no-user-gesture-required']});
  let context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  assert.equal((await post(context, 'access', {invite})).status, 200);
  const code = 'SF-' + randomBytes(32).toString('base64url');
  let response = await post(context, 'start', {assignmentId: assignment.id, alias: 'qa-sequence-short-' + randomBytes(8).toString('hex'), recoveryCode: code, consent: true, priorExposure: false});
  assert.equal(response.status, 200, JSON.stringify(response.data)); let state = response.data;
  assert.equal(state.dataset.sha256, data.dataset_sha256); assert.equal(state.dataset.release, 'annotation400-seedance-state-20261023-v3');
  const initial = structuredClone(state), first = state.research.items[0], future = state.session.workflow.sceneSequence.scenes[1].itemIds[0];
  let page = await pageFor(context);
  await checked('first scene 8 questions, future materials absent from entire status and export', async () => {
    const scope = await assertScope(context, state); assert.equal(scope.exportedMediaRows, 8);
    assert.equal(state.session.workflow.sceneSequence.scenes.length, 5); assert.deepEqual(state.research.gate2Tasks, []);
    assert.equal(await page.locator('.scene-sequence .locked').count(), 4);
    assert.equal((await post(context, 'evidence', {instanceId: first.id})).status, 400);
    assert.equal((await post(context, 'evidence', {instanceId: future})).status, 400);
    assert.equal((await post(context, 'draft', body(state, {answers: {[future]: {answer: 'A', confidence: 'high', rationale: '', issue: 'none'}}}))).status, 400);
    assert.doesNotMatch(JSON.stringify(state.research), /"(?:initial_state|private_character|oracle_reference|state_before)"/);
    return scope;
  });
  await checked('current 8 full prompts, checkpoint captions, 2 complete plays and text-only T2', async () => {
    const played = new Set();
    for (const id of state.research.assignment.item_ids) {
      const item = state.research.items.find(x => x.id === id);
      await page.getByRole('navigation', {name: '场景内任务', exact: true}).getByRole('button').nth(state.research.assignment.item_ids.indexOf(id)).click();
      assert.equal(norm(await page.locator('.answer-panel h2').innerText()), norm(item.public.question));
      assert.deepEqual((await page.locator('.checkpoint-caption p[lang=en]').allTextContents()).map(norm), item.media.map(x => norm(x.spoken_text)));
      const text = norm(await page.locator('.material').innerText());
      for (const media of item.media) {
        assert.ok(text.includes(norm(media.full_public_response))); assert.equal(media.spoken_scope, 'checkpoint_sentence');
        if (played.has(media.sha256)) continue;
        const video = page.locator('.video-panel video[src="' + media.url + '"]');
        const result = await video.evaluate(async v => {v.currentTime = 0; v.muted = false; await v.play(); await new Promise((resolve, reject) => {
          const deadline = setTimeout(() => reject(new Error('Video end timeout')), 10000); v.addEventListener('ended', () => {clearTimeout(deadline); resolve();}, {once: true});
        }); return {duration: v.duration, currentTime: v.currentTime, ended: v.ended, audioBytes: v.webkitAudioDecodedByteCount || 0, audioTracks: v.audioTracks?.length || 0, frames: v.getVideoPlaybackQuality().totalVideoFrames};});
        assert.ok(result.duration >= 4.9 && result.duration <= 5.2); assert.ok(result.ended && result.frames > 0 && (result.audioBytes > 0 || result.audioTracks > 0));
        const file = await context.request.get(url + media.url); assert.equal(file.status(), 200); assert.equal(sha(await file.body()), media.sha256);
        played.add(media.sha256); report.videos.push({nodeId: media.node_id, sha256: media.sha256, ...result});
      }
    }
    assert.equal(played.size, 2);
    const t2 = state.research.items.filter(x => x.task === 'T2'); assert.equal(t2.length, 2);
    assert.ok(t2.every(x => x.media.length === 0 && x.public.modality === 'text'));
    return {prompts: 8, fullPlaysWithAudio: 2, textOnlyT2: true};
  });
  await page.getByRole('navigation', {name: '场景内任务', exact: true}).getByRole('button').first().click();
  await page.locator('label.option').filter({has: page.locator('input[value="B"]')}).click(); await page.getByLabel('把握程度', {exact: true}).selectOption('high');
  await page.locator('.answer-panel textarea').fill('Scene checkpoint UI autosave.');
  await page.waitForFunction(() => document.querySelector('.save-status')?.textContent === '进度已保存');
  state = await get(context, 'status'); assert.equal(state.session.answers[first.id].answer, 'B');
  state = await unlock(context, state); await page.reload({waitUntil: 'networkidle'});
  await checked('locked current-scene feedback, 2 media audits and mobile layout', async () => {
    const scope = await assertScope(context, state); assert.equal(scope.exportedMediaRows, 8);
    assert.equal((await post(context, 'evidence', {instanceId: future})).status, 400);
    await page.locator('.scene-answer-feedback strong').nth(1).waitFor(); assert.equal(await page.locator('.scene-answer-summary tbody tr').count(), 8);
    const mediaTasks = state.research.gate2Tasks.filter(x => x.kind === 'media-quality'); assert.equal(mediaTasks.length, 2);
    for (const task of mediaTasks) {const asset = initial.research.items.flatMap(x => x.media).find(x => x.sha256 === task.video.sha256); assert.ok(asset); assert.equal(task.evidence.spoken_text, asset.spoken_text); assert.equal(task.evidence.full_public_response, asset.full_public_response);}
    for (const width of [390, 320]) {await page.setViewportSize({width, height: 844}); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)); await page.screenshot({path: path.join(out, 'scene-gt-' + width + '.png'), fullPage: false});}
    await page.setViewportSize({width: 1440, height: 1000});
    assert.equal((await post(context, 'submit', body(state, {gt: {}, gate2Answers: {}, attestation: true}))).status, 400);
    return {referenceAnswers: 8, mediaAudits: 2, widths: [390, 320], ...scope};
  });
  state = await finish(context, state); await page.reload({waitUntil: 'networkidle'});
  await checked('next scene relocks feedback, retains immutable first scene and exports 16 visible rows', async () => {
    const scope = await assertScope(context, state); assert.equal(scope.index, 1); assert.equal(scope.phase, 'blind'); assert.equal(scope.exportedMediaRows, 16);
    assert.equal(await page.locator('.scene-answer-feedback').count(), 0); assert.equal(await page.locator('.scene-sequence .finished').count(), 1); assert.equal(await page.locator('.scene-sequence .locked').count(), 3);
    assert.equal(state.session.workflow.blind[first.id].answer, 'B');
    assert.equal((await post(context, 'draft', body(state, {answers: {[first.id]: {...state.session.workflow.blind[first.id], answer: 'D'}}}))).status, 400);
    assert.equal((await post(context, 'evidence', {instanceId: first.id})).status, 400); assert.equal((await post(context, 'evidence', {instanceId: future})).status, 400);
    await page.close(); const recovered = await browser.newContext(); response = await post(recovered, 'recover', {alias: state.session.alias, recoveryCode: code}); assert.equal(response.status, 200); await context.close(); context = recovered; state = response.data;
    assert.equal(state.session.workflow.sceneSequence.index, 1); return {...scope, recovery: true};
  });
  await checked('five scenes complete with 40 frozen answers and all 10 media only in final export', async () => {
    while (state.session.status !== 'submitted') {await assertScope(context, state); state = await unlock(context, state); await assertScope(context, state); state = await finish(context, state);}
    const exported = await get(context, 'export'); assert.equal(exported.dataset_sha256, data.dataset_sha256);
    assert.equal(state.session.workflow.sceneSequence.index, 5); assert.equal(Object.keys(exported.workflow.sceneSequence.completed).length, 5);
    assert.equal(Object.keys(exported.blind_responses).length, 40); assert.equal(Object.keys(exported.machine_assisted_gt).length, 40);
    assert.deepEqual(exported.media_hashes, Object.fromEntries(assigned.map(x => [x.id, x.media]))); assert.equal(new Set(Object.values(exported.media_hashes).flat().map(x => x.sha256)).size, 10);
    fs.writeFileSync(path.join(out, 'new-release-export.json'), JSON.stringify(exported, null, 2));
    assert.equal((await post(context, 'draft', {})).status, 409); return {datasetSha256: exported.dataset_sha256, completedScenes: 5, blindAnswers: 40, mediaRows: 40, uniqueMedia: 10};
  });
  await checked('old v15 restores all records while retired videos are explicitly marked', async () => {
    const fixture = read(path.join(out, 'legacy-v15-fixture.json')), oldContext = await browser.newContext();
    response = await post(oldContext, 'recover', {alias: fixture.alias, recoveryCode: fixture.recoveryCode}); assert.equal(response.status, 200); const old = response.data;
    assert.equal(old.dataset.sha256, fixture.datasetSha256); assert.equal(old.session.workflow.sceneSequence, undefined); assert.equal(old.research.items.length, 40);
    assert.deepEqual(Object.fromEntries(old.research.items.map(x => [x.id, x.media])), fixture.mediaHashes);
    const oldPage = await pageFor(oldContext); assert.equal(await oldPage.locator('.scene-sequence').count(), 0); assert.equal(await oldPage.locator('.checkpoint-caption').count(), 0);
    assert.equal(await oldPage.locator('.video-panel video').count(), 0);
    assert.ok((await oldPage.locator('.video-panel').innerText()).includes('旧版视频已清理'));
    assert.ok((await oldPage.locator('.release-notice').innerText()).includes('原题目和标注记录仍保留'));
    const exported = await get(oldContext, 'export'); assert.deepEqual(exported.media_hashes, fixture.mediaHashes); assert.deepEqual(exported.gate2_human_review.task_hashes, fixture.taskHashes);
    fs.writeFileSync(path.join(out, 'legacy-v15-export.json'), JSON.stringify(exported, null, 2)); await oldContext.close(); return {questions: 40, retiredMediaExplicit: true, datasetSha256: fixture.datasetSha256};
  });
  assert.deepEqual(report.pageErrors, []); report.passed = true;
}
run().catch(error => {report.error = String(error.stack || error); console.error(report.error); process.exitCode = 1;}).finally(async () => {
  if (browser) await browser.close(); report.completedAt = new Date().toISOString(); fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({passed: report.passed, checks: report.checks.length, videos: report.videos.length, report: path.join(out, 'result.json')}));
});
