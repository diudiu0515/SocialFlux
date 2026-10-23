/* Local candidate QA only. --prepare-legacy-fixture writes SQL, never executes it. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createHash, randomBytes, randomUUID} = require('node:crypto');
const {gunzipSync} = require('node:zlib');
const {execFileSync} = require('node:child_process');

const root = path.resolve(__dirname, '../../..');
const candidate = path.resolve(process.env.CHECKPOINT_SITE || path.join(root, 'build/annotation-checkpoint-integration-20261023/site'));
const output = path.resolve(process.env.CHECKPOINT_INTEGRATION_OUTPUT || path.join(root, 'build/annotation-checkpoint-integration-20261023/browser'));
const url = process.env.CHECKPOINT_QA_URL || 'http://127.0.0.1:8133';
assert.match(url, /^http:\/\/127\.0\.0\.1:\d+$/, 'Only an explicitly isolated local server may be used');
const invite = 'qa-human-gt-invite-20261022-abcdefghijklm';
const oldHash = '338a2502b00b4146525b96c864debee2d2da35cf9da6c06151169d900b18d9bc';
const json = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const unpack = file => JSON.parse(gunzipSync(Buffer.from(json(file).gzip_base64, 'base64')));
const sha = value => createHash('sha256').update(value).digest('hex');
const normalize = text => text.replace(/\s+/g, ' ').trim();
const data = unpack(path.join(candidate, 'data/research-server.json'));
const registry = unpack(path.join(candidate, 'data/gate2-review-server.json'));
const tasksFor = bundle => bundle.tasks || bundle.task_refs.map(ref => {
  const task = registry.task_pool[ref]; assert.ok(task && task.sha256 === ref, 'Exact-bound task reference required'); return task;
});
const selectedTasks = (bundle, assignment) => tasksFor(bundle).filter(task => assignment.scene_ids.includes(task.scene_id) &&
  (task.tracks ? task.tracks.includes(assignment.track) : !task.kind.startsWith('T4-') && (task.kind !== 'media-quality' || assignment.track === 'offline_video')));
const syntheticAnswer = task => ({values: Object.fromEntries(task.questions.map(q => [q.id,
  q.id === 'playback' && Object.hasOwn(q.choices, 'partial') ? 'partial' :
    ['uncertain', 'unverifiable', 'unavailable', 'not_applicable'].find(key => Object.hasOwn(q.choices, key)) || Object.keys(q.choices)[0]])),
  rationale: 'Isolated automated QA only. No human semantic or media-quality approval is being recorded.'});
fs.mkdirSync(output, {recursive: true});
const fixtureFile = path.join(output, 'legacy-v15-fixture.json');

function prepareLegacyFixture() {
  const snapshot = json(path.join(candidate, 'data/research-media-history.json')).find(x => x.dataset_sha256 === oldHash);
  assert.ok(snapshot, 'Published v15 media snapshot must be retained');
  const assignment = snapshot.assignments.find(x => x.id === 'offline_video-01');
  const rows = snapshot.items.filter(x => assignment.item_ids.includes(x.id));
  const bundle = registry.versions.filter(x => x.dataset_sha256 === oldHash).at(-1);
  assert.ok(bundle, 'Old Gate2 bundle must remain available');
  const tasks = selectedTasks(bundle, assignment);
  const blind = Object.fromEntries(assignment.item_ids.map(id => [id, {answer: 'A', confidence: 'medium', rationale: 'Synthetic local v15 recovery fixture.', issue: 'none'}]));
  const independent = Object.fromEntries(tasks.filter(x => x.stage === 'independent').map(x => [x.id, syntheticAnswer(x)]));
  const now = new Date().toISOString();
  const code = 'SF-' + randomBytes(32).toString('base64url');
  const record = {id: randomUUID(), user_id: sha(code), dataset_sha256: oldHash, release: snapshot.release,
    reviewer_alias: 'qa-local-v15-' + randomBytes(6).toString('hex'), prior_exposure: 0,
    draft_json: JSON.stringify(blind), item_hashes_json: JSON.stringify(Object.fromEntries(rows.map(x => [x.id, x.item_sha256]))),
    media_reviews_json: '{}', media_hashes_json: JSON.stringify(Object.fromEntries(rows.map(x => [x.id, x.media]))),
    assignment_json: JSON.stringify(assignment), workflow_json: JSON.stringify({phase: 'gt', blind, blindLockedAt: now,
      baselineEligible: true, exclusions: [], gate2: {packet_sha256: bundle.sha256, answers: independent, independentLockedAt: now}}),
    revision: 3, status: 'in_progress', created_at: now, updated_at: now, submitted_at: null};
  const sqlValue = value => value === null ? 'NULL' : typeof value === 'number' ? String(value) : "'" + value.replace(/'/g, "''") + "'";
  fs.writeFileSync(path.join(output, 'legacy-v15-fixture.sql'), '-- Synthetic isolated local D1 fixture. Execute with --local only.\nINSERT INTO demo_sessions (' +
    Object.keys(record).join(',') + ') VALUES (' + Object.values(record).map(sqlValue).join(',') + ');\n');
  fs.writeFileSync(fixtureFile, JSON.stringify({localOnly: true, alias: record.reviewer_alias, recoveryCode: code, datasetSha256: oldHash,
    assignment, blind, gate2Sha256: bundle.sha256, taskHashes: Object.fromEntries(tasks.map(x => [x.id, x.sha256])),
    itemHashes: JSON.parse(record.item_hashes_json), mediaHashes: JSON.parse(record.media_hashes_json)}, null, 2));
  console.log(JSON.stringify({prepared: true, localOnly: true, sqlFile: path.join(output, 'legacy-v15-fixture.sql'), fixtureFile,
    datasetSha256: oldHash, gate2Sha256: bundle.sha256, questions: rows.length, tasks: tasks.length}));
}

function discover() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, 'playwright', path.join(root, 'web/participant_demo/node_modules/playwright')];
  for (const name of fs.readdirSync('/tmp').filter(x => x.startsWith('emotree-browser-')).sort()) candidates.push(path.join('/tmp', name, 'node_modules/playwright'));
  for (const modulePath of candidates.filter(Boolean)) {
    try {
      const module = require(modulePath), found = require.resolve(modulePath), directory = path.resolve(path.dirname(found), '../..');
      const executables = [process.env.CHROMIUM_EXECUTABLE, module.chromium.executablePath()];
      const browsers = path.join(directory, 'browsers');
      if (fs.existsSync(browsers)) for (const name of fs.readdirSync(browsers).filter(x => x.startsWith('chromium-'))) executables.push(path.join(browsers, name, 'chrome-linux64/chrome'));
      const executablePath = executables.find(x => x && fs.existsSync(x));
      if (executablePath) return {chromium: module.chromium, executablePath};
    } catch {}
  }
  throw new Error('Existing Playwright/Chromium missing; no download attempted.');
}
async function post(context, action, body) {
  const response = await context.request.post(url + '/api/demo/' + action, {data: body});
  return {status: response.status(), data: await response.json()};
}
async function status(context) {
  const response = await context.request.get(url + '/api/demo/status'); assert.equal(response.status(), 200); return response.json();
}
async function start(context, assignmentId) {
  assert.equal((await post(context, 'access', {invite})).status, 200);
  const code = 'SF-' + randomBytes(32).toString('base64url');
  const response = await post(context, 'start', {alias: 'qa-checkpoint-' + randomBytes(8).toString('hex'), priorExposure: false, consent: true, assignmentId, recoveryCode: code});
  assert.equal(response.status, 200, JSON.stringify(response.data)); return {state: response.data, code};
}
function assertPublicOnly(value) {
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    assert.ok(!['private', 'private_character', 'omniscient_evidence', 'oracle_reference', 'api_screening', 'machine', 'state_before', 'state_after'].includes(key), 'Private key leaked: ' + key);
    assertPublicOnly(child);
  }
}
const report = {testedAt: new Date().toISOString(), url, candidate, localOnly: true, passed: false, checks: [], videos: [], pageErrors: [], externalRequests: [], onlineTested: false};
let browser;
async function checked(name, action) {
  const detail = await action(); report.checks.push({name, passed: true, detail}); console.log(JSON.stringify({check: name, passed: true})); return detail;
}
async function newPage(context) {
  const page = await context.newPage();
  page.on('pageerror', error => report.pageErrors.push(error.message));
  page.on('request', request => {if (/^https?:/.test(request.url()) && !request.url().startsWith(url + '/')) report.externalRequests.push(request.url().split('?')[0]);});
  await page.goto(url, {waitUntil: 'networkidle'}); return page;
}
async function goItem(page, state, item) {
  const sceneItems = state.research.assignment.item_ids.filter(id => state.research.items.find(x => x.id === id).scene_id === item.scene_id);
  await page.locator('[data-scene="' + item.scene_id + '"]').click();
  await page.getByRole('navigation', {name: '场景内任务', exact: true}).getByRole('button').nth(sceneItems.indexOf(item.id)).click();
  await page.waitForFunction(id => document.querySelector('.answer-panel .section-kicker')?.textContent.includes(id), item.id);
}
async function playVideo(page, locator, expectedDuration, full = true) {
  const result = await locator.evaluate(async (video, options) => {
    video.pause(); video.currentTime = 0; video.muted = false; video.volume = 1;
    const before = video.currentTime;
    await video.play();
    await new Promise((resolve, reject) => {
      const deadline = setTimeout(() => {clearInterval(timer); reject(new Error('Playback timeout'));}, 12000);
      const timer = setInterval(() => {
        if (video.error) {clearTimeout(deadline); clearInterval(timer); reject(new Error('Media error ' + video.error.code));}
        else if (options.full ? video.ended : video.currentTime >= .65) {clearTimeout(deadline); clearInterval(timer); resolve();}
      }, 50);
    });
    video.pause();
    return {duration: video.duration, width: video.videoWidth, height: video.videoHeight, before, currentTime: video.currentTime,
      ended: video.ended, muted: video.muted, src: video.currentSrc, decodedAudioBytes: video.webkitAudioDecodedByteCount || 0,
      audioTracks: video.audioTracks?.length || 0, frames: video.getVideoPlaybackQuality?.().totalVideoFrames || 0, error: video.error?.code || null};
  }, {full});
  assert.ok(Math.abs(result.duration - expectedDuration) < .08, JSON.stringify(result));
  assert.ok(result.width > 0 && result.height > 0 && result.frames > 0);
  assert.ok(result.currentTime > result.before && result.currentTime >= .65);
  if (full) assert.equal(result.ended, true);
  assert.equal(result.muted, false); assert.equal(result.error, null);
  assert.ok(result.decodedAudioBytes > 0 || result.audioTracks > 0, 'Browser must decode actual audio');
  return result;
}

async function run() {
  assert.ok(fs.existsSync(fixtureFile), 'Prepare and inject the synthetic v15 fixture into candidate local D1 first');
  const runtime = discover();
  browser = await runtime.chromium.launch({headless: true, executablePath: runtime.executablePath,
    args: ['--no-sandbox', '--disable-gpu', '--disable-background-networking', '--autoplay-policy=no-user-gesture-required']});
  const initialContext = await browser.newContext({viewport: {width: 1440, height: 1000}});
  let {state, code} = await start(initialContext, 'offline_video-01');
  const initial = structuredClone(state), items = initial.research.items;
  const assets = new Map(items.flatMap(item => item.media).map(media => [media.sha256, media]));
  await checked('new release, public-only blind material and 40 questions / 15 unique clips', async () => {
    assert.equal(state.dataset.sha256, data.dataset_sha256); assert.notEqual(state.dataset.sha256, oldHash);
    assert.equal(state.dataset.release, 'annotation400-checkpoint-20261023-v2');
    assert.equal(state.session.workflow.gate2.packet_sha256, registry.current);
    assert.equal(state.session.workflow.phase, 'blind'); assert.equal(items.length, 40); assert.equal(assets.size, 15);
    assert.equal(state.research.assignment.scene_ids.length, 5); assert.deepEqual(state.research.gate2Tasks, []);
    assertPublicOnly(items); assertPublicOnly(state.questions);
    assert.equal((await post(initialContext, 'evidence', {instanceId: items[0].id})).status, 400);
    for (const asset of assets.values()) {
      assert.equal(asset.spoken_scope, 'checkpoint_sentence'); assert.equal(asset.duration_seconds, 4.6);
      assert.equal(asset.audio_required, true); assert.equal(asset.human_review, 'pending'); assert.equal(asset.speech_verified, false);
      assert.ok(asset.spoken_text && asset.full_public_response && asset.full_public_response.length > asset.spoken_text.length);
      assert.match(asset.url, /^\/media\/[a-f0-9]{64}\.mp4$/); assert.equal(path.basename(asset.url, '.mp4'), asset.sha256);
    }
    return {datasetSha256: state.dataset.sha256, gate2Sha256: registry.current, questions: items.length, uniqueMedia: assets.size};
  });
  let page = await newPage(initialContext);
  await checked('all 40 complete public prompts, short captions and 15 actual full audio/video plays', async () => {
    const played = new Set();
    for (const itemId of state.research.assignment.item_ids) {
      const item = items.find(x => x.id === itemId); await goItem(page, state, item);
      assert.equal(normalize(await page.locator('.answer-panel h2').innerText()), normalize(item.public.question));
      assert.deepEqual((await page.locator('.checkpoint-caption p[lang="en"]').allTextContents()).map(normalize), item.media.map(x => normalize(x.spoken_text)));
      const material = normalize(await page.locator('.material').innerText());
      for (const asset of item.media) {
        assert.ok(material.includes(normalize(asset.full_public_response)), 'Full public response missing from ' + item.id + '/' + asset.node_id);
        if (played.has(asset.sha256)) continue;
        const video = page.locator('.video-panel video[src="' + asset.url + '"]');
        const playback = await playVideo(page, video, 4.6);
        const response = await initialContext.request.get(url + asset.url); assert.equal(response.status(), 200);
        assert.equal(sha(await response.body()), asset.sha256);
        const localFile = path.join(candidate, 'public', asset.url);
        assert.equal(sha(fs.readFileSync(localFile)), asset.sha256);
        const streams = JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-show_streams', '-of', 'json', localFile], {encoding: 'utf8'})).streams;
        assert.equal(streams.filter(x => x.codec_type === 'audio').length, 1);
        report.videos.push({nodeId: asset.node_id, sha256: asset.sha256, spokenText: asset.spoken_text, playback}); played.add(asset.sha256);
        console.log(JSON.stringify({fullVideoPlayback: played.size, total: assets.size}));
      }
      assert.equal(await page.locator('.private-panel').count(), 0);
      assert.equal(await page.locator('[data-review-task]').count(), 0);
    }
    assert.equal(played.size, 15); return {prompts: items.length, captions: 'all assigned item media', fullyPlayedWithDecodedAudio: played.size};
  });
  await checked('T2 histories share the same exact ending clip', async () => {
    for (const scene of state.research.assignment.scene_ids) {
      const rows = items.filter(x => x.scene_id === scene && x.task === 'T2'); assert.equal(rows.length, 2);
      const endings = rows.map(item => item.media.filter(x => x.evidence_ids.some(id => /ending/.test(id))));
      assert.ok(endings.every(list => list.length === 1));
      assert.equal(endings[0][0].sha256, endings[1][0].sha256);
      assert.equal(normalize(endings[0][0].full_public_response), normalize(rows[0].public.input.shared_ending.environment_character || rows[0].public.input.shared_ending.current_response));
    }
    return {scenes: 5, exactSharedEnding: true};
  });
  const first = items.find(x => x.id === state.research.assignment.item_ids[0]); await goItem(page, state, first);
  await page.locator('label.option').filter({has: page.locator('input[name="research-answer"][value="B"]')}).click();
  assert.equal(await page.locator('input[name="research-answer"][value="B"]').isChecked(), true);
  await page.getByLabel('把握程度', {exact: true}).selectOption('high');
  await page.locator('.answer-panel textarea').fill('Local checkpoint QA: actual UI autosave and recovery.');
  await page.waitForFunction(() => document.querySelector('.save-status')?.textContent.includes('进度已保存'), null, {timeout: 15000});
  state = await status(initialContext); assert.equal(state.session.answers[first.id]?.answer, 'B');
  await page.close();
  const context = await browser.newContext({viewport: {width: 390, height: 844}});
  await checked('cross-context restore, actual UI autosave and mobile layout', async () => {
    const recovered = await post(context, 'recover', {alias: state.session.alias, recoveryCode: code}); assert.equal(recovered.status, 200); state = recovered.data;
    assert.equal(state.session.answers[first.id].rationale, 'Local checkpoint QA: actual UI autosave and recovery.');
    assert.equal(state.dataset.sha256, initial.dataset.sha256); assert.deepEqual(state.research.items, initial.research.items);
    page = await newPage(context); assert.equal(await page.locator('input[name="research-answer"][value="B"]').isChecked(), true);
    const widths = [];
    for (const width of [390, 320]) {
      await page.setViewportSize({width, height: 844});
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth); assert.ok(scrollWidth <= width + 1, String(scrollWidth));
      await page.screenshot({path: path.join(output, 'checkpoint-blind-' + width + '.png'), fullPage: false}); widths.push({width, scrollWidth});
    }
    await page.setViewportSize({width: 1440, height: 1000}); return {restored: true, widths};
  });
  const blind = Object.fromEntries(items.map(item => [item.id, state.session.answers[item.id] || {answer: 'A', confidence: 'medium', rationale: 'Isolated synthetic QA.', issue: 'none'}]));
  let response = await post(context, 'draft', {revision: state.session.revision, answers: blind}); assert.equal(response.status, 200); state = response.data;
  assert.equal((await post(context, 'draft', {revision: state.session.revision - 1, answers: blind})).status, 409);
  await page.reload({waitUntil: 'networkidle'});
  await page.getByRole('button', {name: '检查与提交', exact: true}).click(); await page.locator('#research-submit').click();
  await page.getByRole('heading', {name: '先留下独立的环境判断。', exact: true}).waitFor(); state = await status(context);
  await checked('blind lock and independent review retain private-evidence gate', async () => {
    assert.equal(state.session.workflow.phase, 'gate2'); assert.deepEqual(state.session.workflow.blind, blind);
    assert.ok(state.research.gate2Tasks.length > 0 && state.research.gate2Tasks.every(x => x.stage === 'independent'));
    assert.equal((await post(context, 'evidence', {instanceId: first.id})).status, 400);
    assert.equal(await page.locator('.private-panel').count(), 0);
    return {independentTasks: state.research.gate2Tasks.length, blindLockedAt: state.session.workflow.blindLockedAt};
  });
  const independentAnswers = Object.fromEntries(state.research.gate2Tasks.map(task => [task.id, syntheticAnswer(task)]));
  response = await post(context, 'draft', {revision: state.session.revision, gate2Answers: independentAnswers}); assert.equal(response.status, 200); state = response.data;
  await page.reload({waitUntil: 'networkidle'}); await page.locator('#gate2-lock').click();
  await page.getByRole('heading', {name: '核对私有证据，确认 GT。', exact: true}).waitFor(); state = await status(context);
  await checked('15 media-quality tasks bind the short spoken text and full public response', async () => {
    assert.equal(state.session.workflow.phase, 'gt'); assert.equal((await post(context, 'evidence', {instanceId: first.id})).status, 200);
    const mediaTasks = state.research.gate2Tasks.filter(x => x.kind === 'media-quality'); assert.equal(mediaTasks.length, 15);
    assert.deepEqual(new Set(mediaTasks.map(x => x.video.sha256)), new Set(assets.keys()));
    for (const task of mediaTasks) {
      const asset = assets.get(task.video.sha256); assert.equal(task.video.url, asset.url);
      assert.equal(task.evidence.spoken_text, asset.spoken_text); assert.equal(task.evidence.full_public_response, asset.full_public_response);
      assert.equal(task.evidence.spoken_scope, 'checkpoint_sentence'); assert.equal(task.evidence.duration_seconds, 4.6);
      for (const ref of task.evidence.identity_reference_clips || []) {
        assert.ok(assets.has(ref.sha256), 'Reference clip must be assigned');
        assert.ok(items.some(item => item.scene_id === task.scene_id && item.media.some(media => media.sha256 === ref.sha256)), 'Reference clip must be from the same scene');
      }
    }
    await page.getByRole('button', {name: /场景与 rollout 核对/}).click();
    const task = mediaTasks.find(x => x.scene_id === first.scene_id);
    const panel = page.locator('[data-review-task="' + task.id + '"]'); await panel.evaluate(element => {element.open = true;});
    assert.ok(normalize(await panel.innerText()).includes(normalize(task.evidence.spoken_text)));
    assert.ok(normalize(await panel.innerText()).includes(normalize(task.evidence.full_public_response)));
    assert.equal(await panel.locator('video[src="' + task.video.url + '"]').count(), 1);
    await page.screenshot({path: path.join(output, 'checkpoint-media-quality.png'), fullPage: false});
    return {mediaTasks: mediaTasks.length, exactShortAndFullText: true};
  });
  await page.close();
  const gt = Object.fromEntries(items.map(item => [item.id, {answer: null, acceptable_answers: [], decision: 'reject', rationale: 'Synthetic local QA record only, not a human GT judgment.'}]));
  const allAnswers = Object.fromEntries(state.research.gate2Tasks.map(task => [task.id, independentAnswers[task.id] || syntheticAnswer(task)]));
  await checked('final submission and export freeze new dataset and all media hashes', async () => {
    const missing = {...allAnswers}; delete missing[state.research.gate2Tasks.find(x => x.kind === 'media-quality').id];
    assert.equal((await post(context, 'submit', {revision: state.session.revision, gt, gate2Answers: missing, attestation: true})).status, 400);
    const tampered = structuredClone(blind); tampered[first.id].answer = 'D';
    response = await post(context, 'draft', {revision: state.session.revision, answers: tampered, gt, gate2Answers: allAnswers});
    assert.equal(response.status, 200); state = response.data; assert.deepEqual(state.session.workflow.blind, blind);
    response = await post(context, 'submit', {revision: state.session.revision, gt, gate2Answers: allAnswers, attestation: true});
    assert.equal(response.status, 200); state = response.data; assert.equal(state.session.workflow.phase, 'complete');
    const exported = await (await context.request.get(url + '/api/demo/export')).json();
    assert.equal(exported.dataset_sha256, data.dataset_sha256); assert.equal(exported.release, data.release);
    assert.equal(exported.gate2_human_review.packet_sha256, registry.current); assert.equal(exported.formal_ground_truth, false);
    assert.deepEqual(exported.blind_responses, blind); assert.deepEqual(exported.media_hashes, Object.fromEntries(items.map(x => [x.id, x.media])));
    assert.deepEqual(exported.item_hashes, Object.fromEntries(data.items.filter(x => state.research.assignment.item_ids.includes(x.id)).map(x => [x.id, x.item_sha256])));
    assert.deepEqual(exported.gate2_human_review.task_hashes, Object.fromEntries(state.research.gate2Tasks.map(x => [x.id, x.sha256])));
    assert.equal((await post(context, 'draft', {revision: state.session.revision, gt, gate2Answers: allAnswers})).status, 409);
    fs.writeFileSync(path.join(output, 'new-release-export.json'), JSON.stringify(exported, null, 2));
    return {datasetSha256: exported.dataset_sha256, gate2Sha256: exported.gate2_human_review.packet_sha256, uniqueMedia: assets.size, finalStatus: exported.status};
  });
  await checked('old v15 session restores original long media, Gate2 bundle and hashes', async () => {
    const fixture = json(fixtureFile), oldContext = await browser.newContext({viewport: {width: 1440, height: 1000}});
    const recovered = await post(oldContext, 'recover', {alias: fixture.alias, recoveryCode: fixture.recoveryCode}); assert.equal(recovered.status, 200);
    const old = recovered.data; assert.equal(old.dataset.sha256, fixture.datasetSha256); assert.equal(old.releaseInfo.isCurrent, false);
    assert.equal(old.session.workflow.phase, 'gt'); assert.equal(old.session.workflow.gate2.packet_sha256, fixture.gate2Sha256);
    assert.deepEqual(old.session.workflow.blind, fixture.blind);
    assert.deepEqual(Object.fromEntries(old.research.items.map(x => [x.id, x.media])), fixture.mediaHashes);
    assert.deepEqual(Object.fromEntries(old.research.gate2Tasks.map(x => [x.id, x.sha256])), fixture.taskHashes);
    const oldAssets = new Map(old.research.items.flatMap(x => x.media).map(x => [x.sha256, x])); assert.equal(oldAssets.size, 15);
    assert.ok([...oldAssets.keys()].every(hash => !assets.has(hash))); assert.ok([...oldAssets.values()].every(x => x.spoken_scope !== 'checkpoint_sentence'));
    const oldPage = await newPage(oldContext); assert.equal(await oldPage.locator('.checkpoint-caption').count(), 0);
    const oldItem = old.research.items.find(x => x.id === old.research.assignment.item_ids[0]), sample = oldItem.media[0];
    assert.ok(sample.duration_seconds > 5);
    const playback = await playVideo(oldPage, oldPage.locator('.video-panel video').first(), sample.duration_seconds, false);
    const mediaResponse = await oldContext.request.get(url + sample.url); assert.equal(mediaResponse.status(), 200); assert.equal(sha(await mediaResponse.body()), sample.sha256);
    const exported = await (await oldContext.request.get(url + '/api/demo/export')).json();
    assert.equal(exported.dataset_sha256, oldHash); assert.deepEqual(exported.media_hashes, fixture.mediaHashes);
    assert.deepEqual(exported.item_hashes, fixture.itemHashes); assert.equal(exported.gate2_human_review.packet_sha256, fixture.gate2Sha256);
    fs.writeFileSync(path.join(output, 'legacy-v15-export.json'), JSON.stringify(exported, null, 2)); await oldContext.close();
    return {datasetSha256: oldHash, gate2Sha256: fixture.gate2Sha256, retainedOldMedia: oldAssets.size, sampleSha256: sample.sha256, samplePlayback: playback};
  });
  const textContext = await browser.newContext(); const textState = (await start(textContext, 'offline_text-01')).state;
  await checked('offline text remains 40 text-only questions; no online workflow tested', async () => {
    assert.equal(textState.dataset.sha256, data.dataset_sha256); assert.equal(textState.research.items.length, 40);
    assert.ok(textState.research.items.every(x => x.media.length === 0)); assert.deepEqual(textState.research.gate2Tasks, []);
    assert.deepEqual(report.pageErrors, []); assert.deepEqual(report.externalRequests, []); return {questions: 40, media: 0, onlineTested: false};
  });
  report.passed = true;
}

if (process.argv.includes('--prepare-legacy-fixture')) prepareLegacyFixture();
else run().catch(error => {report.error = String(error.stack || error); process.exitCode = 1; console.error(report.error);})
  .finally(async () => {
    if (browser) await browser.close(); report.completedAt = new Date().toISOString();
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify({passed: report.passed, checks: report.checks.length, videos: report.videos.length, report: path.join(output, 'result.json')}));
  });
