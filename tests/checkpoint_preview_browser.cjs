/* Existing local Chromium only; no server, install, network, or GPU required. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL, fileURLToPath} = require('node:url');
const {createHash} = require('node:crypto');
const {execFileSync} = require('node:child_process');

const root = path.resolve(__dirname, '..');
const entry = path.resolve(process.env.CHECKPOINT_PREVIEW || path.join(root, 'build/offline-checkpoint-preview/index.html'));
const output = path.resolve(process.env.CHECKPOINT_BROWSER_OUTPUT || path.join(root, 'build/offline-video-revision-audit/browser-check.json'));
const report = {entry, testedAt: new Date().toISOString(), protocol: 'file:', checks: [], videos: [],
  pageErrors: [], consoleErrors: [], failedRequests: [], externalRequests: [], passed: false};
let browser;
function sha(file) { return createHash('sha256').update(fs.readFileSync(file)).digest('hex'); }
function discover() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, 'playwright', path.join(root, 'web/participant_demo/node_modules/playwright')];
  for (const name of fs.readdirSync('/tmp').filter(x => x.startsWith('emotree-browser-')).sort()) {
    candidates.push(path.join('/tmp', name, 'node_modules/playwright'));
  }
  for (const modulePath of candidates.filter(Boolean)) {
    try {
      const module = require(modulePath);
      const found = require.resolve(modulePath);
      const directory = path.resolve(path.dirname(found), '../..');
      const executables = [process.env.CHROMIUM_EXECUTABLE, module.chromium.executablePath()];
      const browsers = path.join(directory, 'browsers');
      if (fs.existsSync(browsers)) {
        for (const name of fs.readdirSync(browsers).filter(x => x.startsWith('chromium-'))) {
          executables.push(path.join(browsers, name, 'chrome-linux64/chrome'));
        }
      }
      const executablePath = executables.find(x => x && fs.existsSync(x));
      if (executablePath) return {chromium: module.chromium, executablePath, modulePath: found};
    } catch {}
  }
  throw new Error('Existing Playwright/Chromium dependency missing; no download attempted.');
}
async function check(name, action) {
  try { const detail = await action(); report.checks.push({name, passed: true, detail}); }
  catch (error) { report.checks.push({name, passed: false, error: String(error.stack || error)}); }
}

(async () => {
  fs.mkdirSync(path.dirname(output), {recursive: true});
  report.entrySha256 = sha(entry);
  const runtime = discover();
  report.runtime = {modulePath: runtime.modulePath, executablePath: runtime.executablePath, gpuDisabled: true};
  browser = await runtime.chromium.launch({headless: true, executablePath: runtime.executablePath,
    args: ['--no-sandbox', '--disable-gpu', '--disable-background-networking', '--autoplay-policy=no-user-gesture-required']});
  report.browserVersion = browser.version();
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  page.on('pageerror', error => report.pageErrors.push(error.message));
  page.on('console', msg => { if (msg.type() === 'error') report.consoleErrors.push(msg.text()); });
  page.on('requestfailed', req => report.failedRequests.push({url: req.url(), error: req.failure()}));
  page.on('request', req => { if (/^https?:/.test(req.url())) report.externalRequests.push(req.url()); });
  await page.goto(pathToFileURL(entry).href, {waitUntil: 'load'});
  const data = await page.locator('#preview-data').evaluate(el => JSON.parse(el.textContent));
  report.snapshot = {createdAt: data.created_at, nodes: data.node_count, videos: data.video_count,
    statusCounts: data.status_counts, manifestSha256: data.source_manifest_sha256};
  await check('all cards and candidate warning', async () => {
    assert.equal(await page.locator('article.card').count(), data.nodes.length);
    assert.equal(await page.locator('video').count(), data.nodes.filter(x => x.video).length);
    assert.match(await page.locator('main > .notice').innerText(), /未发布.*待观感复核/);
    assert.equal(data.published, false);
    assert.equal(data.release_eligible, false);
    return {cards: data.nodes.length};
  });
  for (const node of data.nodes.filter(x => x.video)) {
    await check(`video metadata, playback and audio: ${node.node_id}`, async () => {
      const card = page.locator('article.card').filter({has: page.locator('.meta', {hasText: node.node_id})});
      const video = card.locator('video');
      await video.evaluate(async element => {
        if (element.readyState >= 1) return;
        await new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(new Error('Metadata timeout')), 15000);
          element.addEventListener('loadedmetadata', () => {clearTimeout(timer); resolve();}, {once: true});
          element.addEventListener('error', () => {clearTimeout(timer); reject(new Error('Media error ' + element.error?.code));}, {once: true});
        });
      });
      const before = await video.evaluate(element => ({duration: element.duration, width: element.videoWidth,
        height: element.videoHeight, currentTime: element.currentTime, currentSrc: element.currentSrc,
        error: element.error?.code || null}));
      assert.ok(before.duration >= 4 && before.duration <= 5, JSON.stringify(before));
      assert.ok(before.width > 0 && before.height > 0);
      assert.equal(before.error, null);
      assert.ok(before.currentSrc.startsWith('file:'));
      await video.evaluate(async element => {element.currentTime = 0; element.muted = false; element.volume = 1; await element.play();});
      await page.waitForFunction(id => {
        const card = [...document.querySelectorAll('article.card')].find(x => x.querySelector('.meta')?.textContent === id);
        return card?.querySelector('video')?.currentTime >= .65;
      }, node.node_id, {timeout: 10000});
      const after = await video.evaluate(element => {
        element.pause();
        return {currentTime: element.currentTime, paused: element.paused, muted: element.muted,
          readyState: element.readyState, error: element.error?.code || null,
          decodedAudioBytes: element.webkitAudioDecodedByteCount ?? null,
          audioTrackCount: element.audioTracks?.length ?? null,
          decodedVideoFrames: element.getVideoPlaybackQuality?.().totalVideoFrames ?? null};
      });
      const file = fileURLToPath(before.currentSrc);
      const metadata = JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-show_streams', '-of', 'json', file], {encoding: 'utf8'}));
      const audio = metadata.streams.filter(x => x.codec_type === 'audio');
      assert.equal(audio.length, 1, 'An actual audio stream must be present');
      assert.equal(after.error, null);
      assert.equal(after.muted, false);
      assert.ok(after.currentTime >= .65);
      assert.ok(after.decodedAudioBytes > 0 || after.audioTrackCount > 0,
        'Browser must report an audio track or actual decoded audio bytes: ' + JSON.stringify(after));
      assert.equal(sha(file), node.hashes['video.mp4']);
      const result = {nodeId: node.node_id, mediaStatus: node.status, before, after,
        audio: audio.map(x => ({codec: x.codec_name, channels: x.channels, sampleRate: x.sample_rate, duration: x.duration}))};
      report.videos.push(result);
      if (report.videos.length % 10 === 0) console.log(JSON.stringify({playbackChecked: report.videos.length, totalVideos: data.video_count}));
      return result;
    });
  }
  await check('scene and status filters', async () => {
    const results = [];
    for (const scene of ['', ...new Set(data.nodes.map(x => x.scene))]) {
      await page.locator('#scene').selectOption(scene);
      const statuses = await page.locator('#status option').evaluateAll(options => options.map(x => x.value));
      for (const status of statuses) {
        await page.locator('#status').selectOption(status);
        const expected = data.nodes.filter(n => (!scene || n.scene === scene) &&
          (!status || (status === 'visual' ? n.frame_review?.priority === 'priority_visual_rewatch'
            : status === 'issues' ? n.status !== 'passed' : status === 'failed' ? ['failed', 'invalid'].includes(n.status)
            : status === 'pending' ? ['missing', 'pending'].includes(n.status) : n.status === 'passed')));
        assert.equal(await page.locator('article.card').count(), expected.length, `${scene}/${status}`);
        if (status === 'visual') assert.deepEqual(await page.locator('article.card > div.meta').allTextContents(), expected.map(x => x.node_id));
        if (!expected.length) assert.match(await page.locator('#cards').innerText(), /没有符合筛选条件/);
        results.push({scene, status, count: expected.length});
      }
    }
    await page.locator('#scene').selectOption(''); await page.locator('#status').selectOption('');
    return results;
  });
  const detailsByTitle = (card, title) => card.locator('details').filter({has: page.locator('summary').filter({hasText: new RegExp('^' + title + '$')})});
  await check('frame review details, exact video SHA binding and visual priority filter', async () => {
    const reviewed = data.nodes.filter(x => x.frame_review);
    const visualOption = await page.locator('#status option[value="visual"]').count();
    if (!visualOption && !reviewed.length) return {supported: false, reviewed: 0};
    const visualPath = path.resolve(process.env.CHECKPOINT_VISUAL_REVIEW || path.join(root, 'build/offline-video-revision-audit/visual-combined-review.json'));
    const original = JSON.parse(fs.readFileSync(visualPath, 'utf8'));
    const samples = new Map(original.samples.map(x => [x.node_id, x]));
    const priority = reviewed.filter(x => x.frame_review.priority === 'priority_visual_rewatch');
    for (const node of data.nodes) {
      const card = page.locator('article.card').filter({has: page.locator('div.meta', {hasText: node.node_id})});
      const panel = detailsByTitle(card, '帧级抽查，非完整观感验收');
      const sample = samples.get(node.node_id);
      const exact = sample && node.video && sample.video_sha256 === node.hashes['video.mp4'];
      if (exact) {
        assert.equal(node.frame_review_status, 'frame_sample_reviewed');
        assert.ok(node.frame_review);
        assert.equal(node.frame_review.priority, sample.findings.follow_up_priority);
        assert.equal(sha(path.resolve(path.dirname(entry), node.video)), sample.video_sha256);
        assert.equal(await panel.count(), 1);
        await panel.locator('summary').click();
        assert.equal(await panel.evaluate(el => el.open), true);
        const content = JSON.parse(await panel.locator('pre').innerText());
        assert.deepEqual(content, node.frame_review.findings);
        for (const [key, value] of Object.entries(content)) {
          assert.ok(sample.findings[key]);
          for (const [field, text] of Object.entries(value)) assert.deepEqual(text, sample.findings[key][field]);
        }
        assert.equal(node.human_review, 'pending');
      } else {
        assert.equal(await panel.count(), 0, 'Unbound review must not be shown for ' + node.node_id);
        assert.ok(!node.frame_review);
      }
    }
    await page.locator('#status').selectOption('visual');
    assert.deepEqual(await page.locator('article.card > div.meta').allTextContents(), priority.map(x => x.node_id));
    assert.equal(await page.locator('article.card').count(), priority.length);
    for (const node of priority) assert.equal(samples.get(node.node_id).video_sha256, node.hashes['video.mp4']);
    await page.locator('#status').selectOption('');
    return {supported: true, reviewed: reviewed.length, priority: priority.length,
      priorityNodeIds: priority.map(x => x.node_id), sourceReportSha256: sha(visualPath)};
  });
  await check('details expand and preserve full public content', async () => {
    for (let index = 0; index < data.nodes.length; index++) {
      const card = page.locator('article.card').nth(index);
      for (const title of ['完整原回复', '公开表情与动作线索', '本条 SHA 绑定']) {
        const item = detailsByTitle(card, title);
        assert.equal(await item.evaluate(el => el.open), false);
        await item.locator('summary').click();
        assert.equal(await item.evaluate(el => el.open), true);
        await item.locator('pre').waitFor({state: 'visible'});
      }
      assert.equal(await detailsByTitle(card, '完整原回复').locator('pre').innerText(), data.nodes[index].full_response || '请求尚未通过校验。');
      assert.deepEqual(JSON.parse(await detailsByTitle(card, '公开表情与动作线索').locator('pre').innerText()), data.nodes[index].expression);
      assert.deepEqual(JSON.parse(await detailsByTitle(card, '本条 SHA 绑定').locator('pre').innerText()),
        {spec_sha256: data.nodes[index].spec_sha256, ...data.nodes[index].hashes});
    }
    return {expanded: data.nodes.length * 3};
  });
  for (const width of [390, 320]) {
    await check(`mobile layout ${width}px with expanded details`, async () => {
      await page.setViewportSize({width, height: 844});
      const geometry = await page.evaluate(() => {
        const result = {viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        offenders: [...document.querySelectorAll('body *')].filter(el => {
          const box = el.getBoundingClientRect(); return box.width &&
            (box.right > innerWidth + 1 || box.left < -1 || el.scrollWidth > el.clientWidth + 1);
        }).slice(0, 10).map(el => ({tag: el.tagName, id: el.id, class: el.className, width: el.getBoundingClientRect().width,
          scrollWidth: el.scrollWidth, text: el.textContent.slice(0, 100)}))};
        const footer = document.querySelector('footer');
        const previous = footer.style.overflowWrap;
        footer.style.overflowWrap = 'anywhere';
        result.scrollWidthWithFooterWrapping = document.documentElement.scrollWidth;
        footer.style.overflowWrap = previous;
        return result;
      });
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({path: path.join(path.dirname(output), `checkpoint-preview-mobile-${width}.png`), fullPage: false});
      assert.ok(geometry.scrollWidth <= width + 1, JSON.stringify(geometry));
      return geometry;
    });
  }
  await check('no page errors or network dependencies', async () => {
    assert.deepEqual(report.pageErrors, []); assert.deepEqual(report.consoleErrors, []);
    // Chromium aborts metadata/range requests when filters remove video nodes.
    // Only allow cancellations for local files whose playback succeeded above.
    const played = new Set(report.videos.map(x => x.before.currentSrc));
    report.expectedMediaCancellations = report.failedRequests.filter(x =>
      x.error?.errorText === 'net::ERR_ABORTED' && played.has(x.url));
    const unexpected = report.failedRequests.filter(x => !report.expectedMediaCancellations.includes(x));
    assert.deepEqual(unexpected, []); assert.deepEqual(report.externalRequests, []);
  });
  report.passed = report.checks.every(x => x.passed);
})().catch(error => {report.fatalError = String(error.stack || error);}).finally(async () => {
  if (browser) await browser.close();
  fs.mkdirSync(path.dirname(output), {recursive: true});
  fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({passed: report.passed, checks: report.checks.length, failed: report.checks.filter(x => !x.passed).map(x => x.name),
    videos: report.videos.length, output, fatalError: report.fatalError}));
  if (!report.passed) process.exitCode = 1;
});
