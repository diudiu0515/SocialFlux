/* Read-only media view. A material preview is never evidence of a rollout event. */
(function (root) {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const families = {activated_tension:'紧张激活',easing_tension:'压力减退',open_engagement:'开放投入',guarded_withdrawal:'防御退缩',firm_boundary:'坚定边界',cautious_relief:'谨慎缓和',risk_concern:'风险担忧'};
  const sessions = new WeakMap();
  let cached = null;
  const turnKey = value => String(value ?? '').replace(/^t0*(\d+)$/, 't$1');
  function eventsFor(version) {
    return (version?.turns || []).flatMap(turn => (turn.trigger_events || []).map(event => ({...event, turn_id:turn.turn_id})));
  }
  function binding(asset, scenarioId, version) {
    if (asset.scenario_id !== scenarioId) return [];
    if (asset.asset_type === 'talking_head') {
      if (!version?.trajectory_id || asset.trajectory_id !== version.trajectory_id) return [];
      return (version.turns || []).filter(t => turnKey(t.turn_id) === turnKey(asset.turn_id)
        && [asset.source_public_response, asset.expected_audio].filter(Boolean).includes(t.environment_response));
    }
    // Matching only an event family or a threshold is not sufficient.
    return eventsFor(version).filter(e => asset.media_asset_id && e.media_asset_id === asset.media_asset_id);
  }
  function safeMediaUrl(url) {
    return typeof url === 'string' && /^\/(?:online-video|talking-video)\/gpt\/[a-zA-Z0-9_.-]+\.mp4(?:\?v=[a-f0-9]+)?$/.test(url) ? url : '';
  }
  async function packet(force = false) {
    if (force || !cached || Date.now() - cached.time > 60000) {
      const promise = fetch('/api/online-multimodal-review/gpt', {cache:'no-store'}).then(async response => {
        if (!response.ok) throw Error('素材接口返回 ' + response.status);
        const data = await response.json();
        if (!Array.isArray(data.scenarios)) throw Error('素材清单格式不完整');
        return data;
      });
      cached = {time:Date.now(), promise};
      promise.catch(() => { if (cached?.promise === promise) cached = null; });
    }
    return cached.promise;
  }
  const name = asset => asset.event_family_label || families[asset.event_family] || asset.event_family || '视频素材';
  function renderEvidence(session) {
    const {host, version, assets, scenarioId} = session;
    const events = eventsFor(version);
    const turns = version?.turns || [];
    const missing = turns.filter(t => !Array.isArray(t.trigger_events)).length;
    host.querySelector('[data-mm-evidence]').innerHTML = `
      <summary>当前所选轨迹的触发记录 <span class="mm-count">${events.length} 条</span></summary>
      <p class="subtle">来源：${escape(version?.label || '尚无轨迹')}。只读取该轨迹保存的 trigger_events，不根据视频是否存在或状态数值重新推断。</p>
      ${missing ? '<p class="mm-warning">部分轮次未提供触发日志，不能据此断言未触发。</p>' : ''}
      ${events.length ? `<div class="mm-event-list">${events.map(event => {
        const asset = assets.find(a => a.scenario_id === scenarioId && a.asset_type === 'online_nonverbal' && a.media_asset_id && a.media_asset_id === event.media_asset_id);
        return `<article class="mm-event"><div><b>${escape(event.turn_id)} · ${escape(families[event.event_family] || event.event_family || event.trigger_id)}</b><span class="badge">${asset ? '同 ID 素材可预览' : '已记录触发 · 视频待补'}</span></div>
          <p>${escape(Object.entries(event.trigger_variables || {}).map(([key,value]) => key + ' = ' + value).join('；') || '未记录触发数值')}</p>
          <small>触发器：${escape(event.trigger_id)} · 规则：${escape(event.trigger_policy_profile || event.trigger_mode || '未记录')}</small>
          <small>素材 ID：${escape(event.media_asset_id || '未指定')}</small></article>`;
      }).join('')}</div>` : `<p class="subtle">${!turns.length ? '尚无对话轮次。' : missing ? '现有数据中没有可展示的触发记录。' : '当前已完成轮次没有记录多模态触发。'}素材可独立预览，不代表本轨迹已使用。</p>`}
      <p class="subtle">“同 ID 素材可预览”不代表生成这条 rollout 时 policy 实际看过视频，也不代表人工审核通过。</p>`;
  }
  function renderList(session) {
    const {host, assets, lane, selected, scenarioId, version} = session;
    const visible = assets.filter(a => lane === 'all' || a.asset_type === lane);
    host.querySelector('[data-mm-list]').innerHTML = visible.length ? visible.map(a => {
      const matches = binding(a, scenarioId, version);
      return `<button class="mm-choice ${a.request_id === selected ? 'active' : ''}" data-mm-asset="${escape(a.request_id)}" aria-pressed="${a.request_id === selected}">
        <span>${a.asset_type === 'talking_head' ? '语音 · 响应口型' : '状态 · 非语言表达'}</span><strong>${escape(name(a))}</strong>
        <small>${matches.length ? '关联 ' + matches.map(e => e.turn_id).join('、') : '素材预览 · 未绑定当前轨迹'}</small></button>`;
    }).join('') : '<p class="subtle">本场景暂无此类素材，切换其他类型查看。</p>';
    host.querySelectorAll('[data-mm-lane]').forEach(button => {
      button.classList.toggle('active', button.dataset.mmLane === lane);
      button.setAttribute('aria-pressed', String(button.dataset.mmLane === lane));
    });
  }
  function renderBinding(session) {
    const asset = session.assets.find(a => a.request_id === session.selected);
    if (!asset) return;
    const matches = binding(asset, session.scenarioId, session.version);
    session.host.querySelector('[data-mm-binding]').textContent = matches.length
      ? (asset.asset_type === 'talking_head' ? '绑定所选轨迹回复：' : '所选轨迹记录了同素材 ID 的触发：') + matches.map(e => e.turn_id).join('、')
      : '独立素材预览 · 不代表当前轨迹已触发或使用';
  }
  function renderPlayer(session) {
    const {host, assets, selected} = session;
    const asset = assets.find(a => a.request_id === selected);
    const player = host.querySelector('[data-mm-player]');
    player.querySelector('video')?.pause();
    if (!asset) {
      player.innerHTML = '<div class="empty">暂无可播放素材。<br>场景、对话和 state 仍可正常查看。</div>';
      return;
    }
    const url = safeMediaUrl(asset.url);
    const metadata = asset.structural_metadata || {};
    const audio = Number(metadata.audio_stream_count) > 0;
    const talking = asset.asset_type === 'talking_head';
    player.innerHTML = `<div class="mm-video-shell">${url ? `<video controls playsinline preload="metadata" src="${escape(url)}" aria-label="${escape(name(asset))}"></video>` : '<div class="empty">素材地址无效，暂时无法播放。</div>'}</div>
      <div class="mm-player-title"><h4>${escape(name(asset))}</h4><span class="badge">${audio ? (talking ? '含语音音轨' : '含非语言音轨') : '未确认音轨'}</span></div>
      <p data-mm-binding class="mm-binding"></p>
      <div class="mm-controls">${url ? '<button data-mm-play type="button">有声播放</button>' : ''}<span class="subtle">${talking ? '带台词的口型视频；台词在下方展开查看。' : '此类视频没有台词；声音主要是呼吸、叹气等非语言声。'}</span></div>
      <p data-mm-playback role="status" class="subtle">点击播放后开启声音；可用播放器调节音量。</p>
      <details><summary>查看素材内容与来源</summary>
        <p class="mm-copy">${escape(asset.expected_cue || '暂无动作说明')}</p>
        ${asset.expected_audio ? `<p class="mm-copy"><b>${talking ? '素材台词' : '声音设计'}：</b>${escape(asset.expected_audio)}</p>` : ''}
        <p class="subtle">${talking ? '源轨迹：' + escape(asset.trajectory_id || '未记录') + ' · ' + escape(asset.turn_id || '') + '<br>' : ''}素材 ID：${escape(asset.media_asset_id)}<br>人工审核：${escape(({passed:'通过',rejected:'退回',pending:'待审'})[asset.human_status] || '未确认')} · 本页只读预览，不修改审核结果。</p>
      </details>`;
    renderBinding(session);
    const video = player.querySelector('video');
    if (!video) return;
    video.muted = false;
    video.volume = 1;
    const status = player.querySelector('[data-mm-playback]');
    const playButton = player.querySelector('[data-mm-play]');
    playButton.onclick = async () => {
      video.muted = false;
      video.volume = 1;
      try { await video.play(); }
      catch (_) { status.textContent = '播放未能启动，请点击播放器播放键，或重新加载素材。'; }
    };
    video.addEventListener('play', () => {
      document.querySelectorAll('video').forEach(other => { if (other !== video) other.pause(); });
      status.textContent = video.muted ? '当前静音，可在播放器中开启声音。' : '正在播放 · 非语言素材的声音可能较轻。';
    });
    video.addEventListener('volumechange', () => {
      status.textContent = video.muted || video.volume === 0 ? '当前静音，可在播放器中开启声音。' : '音量 ' + Math.round(video.volume * 100) + '%';
    });
    video.addEventListener('error', () => {
      status.textContent = '视频加载失败或格式不受支持；请点击“重新加载素材”重试。';
      status.classList.add('mm-warning');
    });
  }
  function render(session) {
    const {host, assets} = session;
    host.innerHTML = `<div class="heading-row"><div><div class="mm-eyebrow">MULTIMODAL · 多模态</div><h3>看看这位角色如何表达</h3></div><a class="mm-review-link" href="/multimodal?batch=gpt&scenario=${encodeURIComponent(session.scenarioId)}">完整素材审核 ↗</a></div>
      <p class="subtle">保留对话与状态，补充可播放的表情、动作和声音。素材与当前轨迹的关联单独核对。</p>
      <div class="mm-toolbar"><div class="tabs" aria-label="多模态素材类型"><button data-mm-lane="all">全部 ${assets.length}</button><button data-mm-lane="online_nonverbal">状态表达</button><button data-mm-lane="talking_head">语音口型</button></div><button data-mm-retry type="button">重新加载素材</button></div>
      <div class="mm-layout"><div data-mm-player></div><nav data-mm-list class="mm-list" aria-label="选择多模态素材"></nav></div>
      <details data-mm-evidence class="mm-evidence"></details>`;
    host.querySelector('[data-mm-retry]').onclick = () => load(session, true);
    host.querySelectorAll('[data-mm-lane]').forEach(button => { button.onclick = () => {
      session.lane = button.dataset.mmLane;
      const visible = assets.filter(a => session.lane === 'all' || a.asset_type === session.lane);
      if (!visible.some(a => a.request_id === session.selected)) {
        session.selected = visible[0]?.request_id;
        renderPlayer(session);
      }
      renderList(session);
    }; });
    host.querySelector('[data-mm-list]').onclick = event => {
      const button = event.target.closest('[data-mm-asset]');
      if (!button) return;
      session.selected = button.dataset.mmAsset;
      renderPlayer(session);
      renderList(session);
    };
    renderPlayer(session);
    renderList(session);
    renderEvidence(session);
  }
  async function load(session, force = false) {
    const ticket = ++session.ticket;
    session.host.querySelector('video')?.pause();
    session.host.innerHTML = '<h3>多模态 · 表情、动作与声音</h3><p role="status" class="subtle">正在读取本场景素材…</p>';
    try {
      const data = await packet(force);
      if (sessions.get(session.host) !== session || ticket !== session.ticket || !session.host.isConnected) return;
      session.assets = data.scenarios.find(s => s.scenario_id === session.scenarioId)?.assets || [];
      const visible = session.assets.filter(a => session.lane === 'all' || a.asset_type === session.lane);
      if (!visible.some(a => a.request_id === session.selected)) session.selected = visible[0]?.request_id;
      render(session);
    } catch (error) {
      if (sessions.get(session.host) !== session || ticket !== session.ticket || !session.host.isConnected) return;
      session.host.innerHTML = `<h3>多模态素材暂时无法加载</h3><p class="mm-warning" role="alert">${escape(error.message)}</p><p class="subtle">不影响场景、对话及 state 查看。</p><button data-mm-retry>重试</button>`;
      session.host.querySelector('[data-mm-retry]').onclick = () => load(session, true);
    }
  }
  function mount(host, context) {
    const previous = sessions.get(host);
    const key = [context.scenarioId, context.version?.key, context.version?.trajectory_id].join('|');
    if (previous?.key === key) {
      previous.version = context.version;
      if (host.querySelector('[data-mm-evidence]')) {
        renderEvidence(previous);
        renderList(previous);
        renderBinding(previous);
      }
      if (previous.resumePlayback) {
        previous.resumePlayback = false;
        host.querySelector('video')?.play().catch(() => {});
      }
      return;
    }
    const session = {host, key, ...context, assets:[], lane:'all', selected:null, ticket:0};
    sessions.set(host, session);
    load(session);
  }
  function remember(host) {
    const session = host && sessions.get(host);
    const video = host?.querySelector('video');
    if (session) session.resumePlayback = Boolean(video && !video.paused && !video.ended);
  }
  const api = {mount, remember, binding, eventsFor, safeMediaUrl};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.LiveMultimodal = api;
})(globalThis);
