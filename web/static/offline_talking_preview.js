(() => {
  let data, selected, rendered;
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text) e.textContent = text; if (cls) e.className = cls; return e; };
  function render() {
    const scene = data.scenes.find(s => s.scene_id === selected);
    if (!scene) return;
    const signature = JSON.stringify(scene);
    document.querySelectorAll('#scenes button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.id === selected)));
    if (signature === rendered) return;
    if ([...document.querySelectorAll('#videos video')].some(v => !v.paused)) return;
    rendered = signature;
    const cards = scene.nodes.map(n => {
      const card = el('article', '', 'preview-card');
      const label = n.location === 'ending' ? 'T2 · 共同回应' : `前史 · ${n.location}`;
      card.append(el('h2', `${label} · ${n.speaker.name || n.speaker}`));
      if (n.review_issue) card.append(el('p', `待修正：${n.review_issue.message}`, 'notice'));
      if (n.available) {
        const video = el('video'); video.controls = true; video.preload = 'metadata'; video.src = n.url; video.playsInline = true;
        card.append(video);
      } else {
        const done = n.segment_statuses.filter(s => s === 'downloaded').length;
        const failed = n.segment_statuses.some(s => ['failed', 'expired', 'cancelled'].includes(s));
        const running = n.segment_statuses.some(s => ['running', 'queued', 'submitted'].includes(s));
        const stage = running ? '生成中' : done ? '待补齐' : '尚未生成';
        card.append(el('p', failed ? '本段生成未通过，待处理。' : `${stage} · 已完成 ${done}/${n.segment_statuses.length} 段`, 'pending-video'));
      }
      card.append(el('h3', '英文台词'), el('p', n.spoken_text, 'transcript'));
      if (n.source_text !== n.spoken_text) {
        const source = el('details'); source.append(el('summary', '来源台词（含义对照）'), el('p', n.source_text, 'transcript')); card.append(source);
      }
      const cues = el('details'); cues.append(el('summary', '公开表情提示'), el('p', JSON.stringify(n.observable_expression), 'transcript')); card.append(cues);
      if (n.speech_screen) {
        card.append(el('p', `语音自动核对：${n.speech_screen.status_label || n.speech_screen.status}。仍需听看复核。`, 'muted'));
        if (n.speech_screen.difference_note) card.append(el('p', n.speech_screen.difference_note, 'muted'));
        const details = el('details'); details.append(el('summary', '自动转写（可能有识别误差）'), el('p', n.speech_screen.transcript || '', 'transcript')); card.append(details);
      }
      return card;
    });
    document.getElementById('videos').replaceChildren(...cards);
  }
  async function refresh() {
    try {
      const response = await fetch('/api/offline-talking-preview', {cache: 'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
      document.getElementById('sceneCount').textContent = `${data.scenes.length} 个场景`;
      document.getElementById('excluded').textContent = (data.excluded_scenes || []).map(x => `${x.scene_id}：${x.reason}。`).join(' ');
      document.getElementById('progress').textContent = data.error || `${data.scenes.length} 个场景 · 已就绪 ${data.ready_nodes}/${data.node_count} 个回应`;
      if (!data.scenes.some(s => s.scene_id === selected)) {
        document.querySelectorAll('#videos video').forEach(v => v.pause());
        selected = data.scenes[0]?.scene_id;
        rendered = undefined;
      }
      document.getElementById('scenes').replaceChildren(...data.scenes.map(s => {
        const b = el('button', s.scene_id); b.type = 'button'; b.dataset.id = s.scene_id;
        b.onclick = () => { document.querySelectorAll('#videos video').forEach(v => v.pause()); selected = s.scene_id; render(); };
        return b;
      }));
      render();
    } catch (error) { document.getElementById('progress').textContent = `预览读取失败：${error.message}`; }
  }
  document.getElementById('refresh').onclick = refresh;
  refresh(); setInterval(refresh, 15000);
})();
