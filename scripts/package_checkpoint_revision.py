"""Package public checkpoint candidates for portable, file:// playback.

Only standard-library Python and ffprobe are required; no models are loaded.
Example: python scripts/package_checkpoint_revision.py --manifest PATH --zip
Verify an unpacked snapshot: python scripts/package_checkpoint_revision.py --verify DIR
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'socialflux_checkpoint_preview_v1'
EXPRESSION_KEYS = ('facial_expression', 'gaze', 'speech_style', 'prosody', 'behavioral_cues')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def probe_video(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', str(path)], check=True, capture_output=True,
                            text=True, timeout=30)
    metadata = json.loads(result.stdout)
    video = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in metadata['streams'] if s['codec_type'] == 'audio')
    return {'duration_seconds': float(metadata['format']['duration']),
            'video_seconds': float(video['duration']), 'audio_seconds': float(audio['duration'])}


def check(status, *reasons, **details):
    return {'status': status, 'reasons': list(reasons), **details}


def public_expression(value):
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if k in EXPRESSION_KEYS
            and (isinstance(v, str) or (isinstance(v, list) and all(isinstance(x, str) for x in v)))}


def build_card(row, manifest_dir, destination, root=ROOT, probe=probe_video):
    """Read one current revision. Fail closed for scores, retain failed clips for review."""
    card = {'node_id': str(row.get('node_id', '')), 'scene': str(row.get('scenario_id', '')),
            'location': '', 'checkpoint_text': '', 'full_response': '', 'expression': {},
            'video': None, 'duration_seconds': None, 'human_review': 'pending',
            'status': 'pending', 'checks': {}, 'hashes': {}}
    checks, hashes = card['checks'], card['hashes']
    tracked = {}

    def remember(path, key):
        value = file_sha(path)
        tracked[path] = value
        hashes[key] = value
        return value

    def receipt(name):
        path = directory / name
        if not path.is_file():
            return None
        try:
            value, fingerprint = read_json(path)
            tracked[path] = fingerprint
            hashes[name] = fingerprint
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    try:
        request_path = Path(row['request_path'])
        if not request_path.is_absolute():
            request_path = root / request_path
        request_path = request_path.resolve()
        if not request_path.is_relative_to(manifest_dir.resolve()):
            raise ValueError('request outside revision directory')
        directory = request_path.parent
        if not request_path.is_file():
            checks['request'] = check('missing', '尚未生成当前请求文件。')
            card['status'] = 'missing'
            return card
        request, fingerprint = read_json(request_path)
        tracked[request_path] = fingerprint
        hashes['request.json'] = fingerprint
        spec = request['spec_sha256']
        if (digest({k: v for k, v in request.items() if k != 'spec_sha256'}) != spec
                or spec != row.get('spec_sha256') or request.get('node_id') != row.get('node_id')
                or request.get('scenario_id') != row.get('scenario_id')
                or request.get('method') != 'checkpoint_4s5s_v2'):
            raise ValueError('request hash or identity mismatch')
        text = request['source_public_response']
        full = request['full_public_response']
        if not isinstance(text, str) or not isinstance(full, str):
            raise ValueError('invalid public text')
        line = request.get('checkpoint_line', {})
        if (line.get('checkpoint_text') != text or line.get('original_response') != full
                or not line.get('source_quote') or line['source_quote'] not in full):
            raise ValueError('checkpoint public source mismatch')
        card.update(location=str(request.get('location', '')), checkpoint_text=text,
                    full_response=full, expression=public_expression(request.get('source_observable_expression')),
                    spec_sha256=spec)
        checks['request'] = check('passed')
    except (KeyError, TypeError, ValueError, OSError):
        checks['request'] = check('invalid', '请求内容、清单 SHA 或公开台词来源不一致；未收录视频。')
        card['status'] = 'invalid'
        return card

    # Hash the actual media, never infer freshness from file names or old flags.
    media = {}
    for name in ('speech.wav', 'motion.mp4', 'video.mp4'):
        path = directory / name
        if path.is_file():
            media[name] = remember(path, name)
    speech, audio_screen = receipt('speech.json'), receipt('audio_screen.json')
    motion, video, sync = receipt('motion.json'), receipt('video.json'), receipt('lipsync_screen.json')
    identity = request.get('identity', {})
    if not isinstance(identity, dict):
        identity = {}
    identity_hash = None
    try:
        identity_path = (root / identity['identity_path']).resolve()
        if identity_path.is_relative_to(root.resolve()) and identity_path.is_file():
            identity_hash = remember(identity_path, 'identity_source')
    except (KeyError, TypeError, OSError):
        pass

    if 'speech.wav' not in media:
        checks['audio'] = check('missing', '新版音频尚未生成。')
    elif speech is None or audio_screen is None:
        checks['audio'] = check('pending', '音频生成回执或独立语音检查尚未齐全。')
    else:
        generation = speech.get('generation_spec', {})
        if not isinstance(generation, dict):
            generation = {}
        bound = (speech.get('spec_sha256') == spec and speech.get('sha256') == media['speech.wav']
                 and speech.get('spoken_text') == text and generation.get('spec_sha256') == spec
                 and speech.get('generation_sha256') == digest(generation)
                 and audio_screen.get('spec_sha256') == spec
                 and audio_screen.get('sha256') == media['speech.wav']
                 and audio_screen.get('expected') == text)
        passed = (audio_screen.get('machine_screen_passed') is True
                  and audio_screen.get('language') == 'en'
                  and number(audio_screen.get('normalized_similarity'))
                  and audio_screen['normalized_similarity'] >= .98
                  and audio_screen.get('critical_content_match') is True
                  and audio_screen.get('unprompted') is True)
        if not bound:
            checks['audio'] = check('invalid', '音频或语音检查 SHA/台词不匹配，旧结果不可用。')
        else:
            details = {}
            if number(audio_screen.get('normalized_similarity')):
                details['normalized_similarity'] = audio_screen['normalized_similarity']
            if isinstance(audio_screen.get('transcript'), str):
                details['transcript'] = audio_screen['transcript']
            checks['audio'] = check('passed' if passed else 'failed',
                                    *([] if passed else ['独立语音机器检查未通过。']), **details)

    motion_bound = (motion is not None and 'motion.mp4' in media
                    and motion.get('spec_sha256') == spec
                    and motion.get('sha256') == media.get('motion.mp4')
                    and 'speech.wav' in media and motion.get('audio_sha256') == media['speech.wav']
                    and identity_hash is not None
                    and identity_hash == identity.get('identity_sha256') == motion.get('identity_sha256'))
    checks['motion_binding'] = (check('passed') if motion_bound else
        check('pending' if motion is None or 'motion.mp4' not in media else 'invalid',
              '表情素材尚未齐全，或其音频/身份/内容 SHA 绑定失效。'))
    video_bound = (video is not None and 'video.mp4' in media
                   and video.get('sha256') == media['video.mp4']
                   and video.get('spec_sha256') == spec and video.get('spoken_text') == text)
    if 'video.mp4' not in media:
        checks['video_binding'] = check('missing', '新版视频尚未生成。')
    elif not video_bound:
        checks['video_binding'] = check('invalid', '视频与当前请求或视频回执 SHA 不一致；未收录视频。')
    else:
        generation = video.get('generation_spec', {})
        if not isinstance(generation, dict):
            generation = {}
        bound = (video.get('generation_sha256') == digest(generation)
                 and generation.get('spec_sha256') == spec
                 and media.get('speech.wav') is not None and media.get('motion.mp4') is not None
                 and video.get('audio_sha256') == generation.get('audio_sha256') == media['speech.wav']
                 and video.get('motion_sha256') == generation.get('motion_sha256') == media['motion.mp4']
                 and motion_bound)
        if 'motion_receipt_sha256' in generation:
            bound = bound and generation['motion_receipt_sha256'] == hashes.get('motion.json')
        if 'motion_source_sha256' in generation:
            bound = bound and generation['motion_source_sha256'] == (motion or {}).get('controls_source_sha256')
        checks['video_binding'] = check('passed' if bound else 'invalid',
            *([] if bound else ['视频对应的音频/表情输入或生成回执已变化；旧检查不可用。']))
        target = destination / 'videos' / (media['video.mp4'] + '.mp4')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(directory / 'video.mp4', target, follow_symlinks=True)
        if target.is_symlink() or file_sha(target) != media['video.mp4']:
            target.unlink(missing_ok=True)
            checks['video_binding'] = check('invalid', '复制时视频发生变化；未收录视频。')
        else:
            card['video'] = target.relative_to(destination).as_posix()
            try:
                structural = probe(target)
                card['duration_seconds'] = structural['duration_seconds']
                valid = (all(number(v) for v in structural.values())
                         and 4 <= structural['duration_seconds'] <= 5
                         and abs(structural['video_seconds'] - structural['audio_seconds']) <= .1)
                checks['duration'] = check('passed' if valid else 'failed',
                    *([] if valid else ['实测时长或音视频长度差不符合 4–5 秒要求。']), **structural)
            except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError):
                checks['duration'] = check('failed', '无法实测视频和音频时长，请检查文件及 ffprobe。')

    # A sync score has meaning only for these exact bytes and current inputs.
    if sync is None:
        checks['sync'] = check('pending', '口型同步机器检查尚未生成。')
    elif (not video_bound or sync.get('video_sha256') != media.get('video.mp4')
          or checks['video_binding']['status'] != 'passed'):
        checks['sync'] = check('invalid', '同步检查与当前视频/输入 SHA 不一致，旧分数不可用。')
    else:
        confidence, offset = sync.get('confidence'), sync.get('offset_frames')
        passed = (sync.get('complete_clip') is True and sync.get('machine_screen_passed') is True
                  and number(confidence) and confidence >= 3 and number(offset) and abs(offset) <= 2)
        details = {k: v for k, v in {'confidence': confidence, 'offset_frames': offset}.items() if number(v)}
        checks['sync'] = check('passed' if passed else 'failed',
            *([] if passed else ['完整片段口型同步机器检查未通过。']), **details)

    # Batch rendering may continue while packaging; never retain scores from a torn snapshot.
    if any(not path.is_file() or file_sha(path) != fingerprint for path, fingerprint in tracked.items()):
        checks['snapshot'] = check('invalid', '打包期间源文件发生变化，请重新打包。')
        for key in ('audio', 'sync'):
            checks[key] = check('invalid', '打包期间输入发生变化；旧结果不可用。')
    statuses = {item['status'] for item in checks.values()}
    card['status'] = next((s for s in ('invalid', 'failed', 'missing', 'pending') if s in statuses), 'passed')
    return card


HTML = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Checkpoint 视频候选版 · 本地预览</title>
<style>
:root{font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;color:#173042;background:#f2f5f8}*{box-sizing:border-box}body{margin:0}main{max-width:1200px;margin:auto;padding:24px 16px 60px}h1{font-size:26px;margin:8px 0 12px}p{line-height:1.6}.notice{background:#fff3d6;border-left:4px solid #c08b19;padding:12px 16px;border-radius:8px}.filters{display:flex;flex-wrap:wrap;gap:16px;margin:20px 0}label{display:flex;gap:8px;align-items:center}select{max-width:100%;padding:8px;border:1px solid #aebccc;border-radius:6px;background:white}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:18px}.card{min-width:0;background:white;border:1px solid #d8e0e7;border-radius:12px;padding:16px;overflow-wrap:anywhere}h2{font-size:18px;margin:0 0 10px}.meta{color:#546679;font-size:13px}.pill{display:inline-block;border-radius:5px;padding:4px 8px;background:#e9edf3}.passed{background:#e0f3e9}.failed,.invalid{background:#ffe5df}.missing,.pending{background:#fff1ce}video{width:100%;max-height:440px;background:#101b27;border-radius:8px;margin:12px 0}.line{font-size:18px;line-height:1.5}details{margin-top:12px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;font:inherit;line-height:1.5;font-size:14px}.checks{padding-left:20px;font-size:14px;line-height:1.7}.empty{background:#edf1f6;padding:22px;border-radius:8px}.hash{font-size:11px;color:#66758a}footer{margin-top:28px;font-size:13px;color:#546679}
footer{overflow-wrap:anywhere}
</style><main>
<h1>4–5秒 checkpoint 候选版</h1>
<div class="notice"><strong>未发布 / 待观感复核</strong><p>视频只读一句 checkpoint，完整原回复仍保留为文本。请重点看神情、口型和自然度。机器检查通过不代表人工已通过，也不代表可以派发正式标注。</p></div>
<p>解压整个文件夹后，双击 index.html 即可播放。视频在同目录的 videos 文件夹中，无需服务或网络。此包是打包时的快照；未生成和检查不通过的条目会明确标出。</p>
<div class="filters"><label>场景<select id="scene"><option value="">全部场景</option></select></label><label>检查状态<select id="status"><option value="">全部</option><option value="issues">全部待处理</option><option value="failed">检验失败 / 绑定失效</option><option value="pending">未生成 / 待检查</option><option value="passed">机器检查通过</option></select></label></div>
<p id="summary" aria-live="polite"></p><div id="cards" class="grid"></div><footer id="footer"></footer>
</main><script id="preview-data" type="application/json">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('preview-data').textContent);
const labels={passed:'机器检查通过',failed:'检验失败',invalid:'绑定失效',missing:'尚未生成',pending:'待检查'};
const checkNames={request:'请求与台词',audio:'音频 / ASR',motion_binding:'表情素材绑定',video_binding:'视频绑定',duration:'实际时长',sync:'口型同步',snapshot:'快照一致性'};
const make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const scene=document.getElementById('scene'),status=document.getElementById('status'),cards=document.getElementById('cards');
[...new Set(data.nodes.map(x=>x.scene))].sort().forEach(s=>{const o=make('option',s);o.value=s;scene.append(o)});
function details(title,text){const d=make('details');d.append(make('summary',title),make('pre',text));return d;}
function render(){
 cards.replaceChildren();
 const selected=data.nodes.filter(n=>(!scene.value||n.scene===scene.value)&&(!status.value||(status.value==='issues'?n.status!=='passed':status.value==='failed'?['failed','invalid'].includes(n.status):status.value==='pending'?['missing','pending'].includes(n.status):n.status==='passed')));
 document.getElementById('summary').textContent=`显示 ${selected.length} / ${data.nodes.length} 条；本包包含 ${data.video_count} 个新版视频。全部待人工观感复核。`;
 selected.forEach(n=>{const c=make('article',undefined,'card');c.append(make('h2',`${n.scene} · ${n.location||'未知位置'}`),make('div',n.node_id,'meta'),make('p',labels[n.status],`pill ${n.status}`),make('p',n.checkpoint_text||'当前请求未通过校验，未展示台词。','line'));
 if(n.video){const v=make('video');v.controls=true;v.preload='metadata';v.playsInline=true;v.src=n.video;v.addEventListener('error',()=>{if(!v.dataset.error){v.dataset.error='1';v.after(make('p','视频无法播放：请确认完整解压 videos 文件夹，并使用支持 MP4 的浏览器。','empty'))}});c.append(v)}else c.append(make('p','新版视频未生成或 SHA 绑定失效，本卡片没有可播放文件。','empty'));
 c.append(make('p',n.duration_seconds===null?'实际秒数：尚未测得':`实际秒数：${n.duration_seconds.toFixed(2)} 秒`,'meta'));
 const ul=make('ul',undefined,'checks');Object.entries(n.checks).forEach(([key,x])=>{let text=`${checkNames[key]||key}：${labels[x.status]}`;if(x.confidence!==undefined)text+=` · confidence ${x.confidence.toFixed(3)} / offset ${x.offset_frames??'未知'} 帧`;if(x.normalized_similarity!==undefined)text+=` · 相似度 ${x.normalized_similarity.toFixed(3)}`;if(x.reasons.length)text+='；'+x.reasons.join(' ');ul.append(make('li',text))});c.append(ul);
 c.append(details('完整原回复',n.full_response||'请求尚未通过校验。'),details('公开表情与动作线索',JSON.stringify(n.expression,null,2)),details('本条 SHA 绑定',JSON.stringify({spec_sha256:n.spec_sha256,...n.hashes},null,2)));cards.append(c)});
 if(!selected.length)cards.append(make('p','没有符合筛选条件的条目。','empty'));
}
scene.addEventListener('change',render);status.addEventListener('change',render);
document.getElementById('footer').textContent=`打包时间：${data.created_at} · manifest SHA256：${data.source_manifest_sha256}。仅含公开回复、公开表情和候选视频；未收集人工审核结论。`;
render();
</script></html>'''


def render_html(data):
    embedded = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    for char, replacement in [('&', '\\u0026'), ('<', '\\u003c'), ('>', '\\u003e'),
                              ('\u2028', '\\u2028'), ('\u2029', '\\u2029')]:
        embedded = embedded.replace(char, replacement)
    return HTML.replace('__DATA__', embedded)


def verify_package(directory):
    directory = Path(directory).resolve()
    checksums, _ = read_json(directory / 'SHA256SUMS.json')
    files = checksums['files']
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if actual != set(files) | {'SHA256SUMS.json'}:
        raise ValueError('Package file list differs from its checksum manifest')
    for name, fingerprint in files.items():
        path = directory / name
        if path.is_symlink() or not path.resolve().is_relative_to(directory) or file_sha(path) != fingerprint:
            raise ValueError('Package file SHA mismatch: ' + name)
    payload, _ = read_json(directory / 'package.json')
    if payload.get('format') != FORMAT:
        raise ValueError('Unexpected package format')
    for card in payload['nodes']:
        if card.get('video') and files.get(card['video']) != card['hashes']['video.mp4']:
            raise ValueError('Packaged video is not bound to its evidence: ' + card['node_id'])
    return {'verified_files': len(files), 'nodes': len(payload['nodes']), 'videos': payload['video_count']}


def package(manifest, output, zip_path=None, root=ROOT, probe=probe_video):
    manifest, output, root = Path(manifest).resolve(), Path(output).absolute(), Path(root).resolve()
    if output.is_symlink() or output.resolve().is_relative_to(manifest.parent) or manifest.is_relative_to(output.resolve()):
        raise ValueError('Output must be separate from revision inputs')
    if output.exists():
        marker = output / 'package.json'
        if not marker.is_file() or read_json(marker)[0].get('format') != FORMAT:
            raise ValueError('Refusing to replace a directory not created by this packager')
    if zip_path is not None:
        zip_path = Path(zip_path).absolute()
        if (zip_path.suffix.lower() != '.zip' or zip_path.is_symlink()
                or zip_path.resolve().is_relative_to(output.resolve())
                or zip_path.resolve().is_relative_to(manifest.parent)
                or (zip_path.exists() and not zipfile.is_zipfile(zip_path))):
            raise ValueError('ZIP must be a ZIP file outside package and revision inputs')
    source, source_sha = read_json(manifest)
    if source.get('version') != 'checkpoint_4s5s_v2' or not isinstance(source.get('nodes'), list):
        raise ValueError('Expected the independent checkpoint revision manifest')
    if source.get('node_count') != len(source['nodes']):
        raise ValueError('Manifest node count mismatch')
    if len({r['node_id'] for r in source['nodes']}) != len(source['nodes']):
        raise ValueError('Duplicate manifest nodes')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + output.name + '-', dir=output.parent))
    try:
        nodes = [build_card(row, manifest.parent, stage, root=root, probe=probe) for row in source['nodes']]
        if file_sha(manifest) != source_sha:
            raise ValueError('Manifest changed during packaging; retry with a stable manifest')
        data = {'format': FORMAT, 'version': source['version'],
                'created_at': datetime.now(timezone.utc).isoformat(), 'source_manifest_sha256': source_sha,
                'human_review': 'pending', 'published': False, 'release_eligible': False,
                'nodes': nodes, 'node_count': len(nodes),
                'video_count': sum(bool(n['video']) for n in nodes),
                'status_counts': dict(Counter(n['status'] for n in nodes))}
        (stage / 'package.json').write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        (stage / 'index.html').write_text(render_html(data))
        # Nothing else is copied: no requests, model receipts, raw audio, or historical videos.
        files = {p.relative_to(stage).as_posix(): file_sha(p) for p in sorted(stage.rglob('*')) if p.is_file()}
        (stage / 'SHA256SUMS.json').write_text(json.dumps({'format': FORMAT, 'files': files}, indent=2)+'\n')
        verify_package(stage)
        if output.exists():
            shutil.rmtree(output)
        stage.replace(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    if zip_path is not None:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_STORED) as archive:
            for path in sorted(output.rglob('*')):
                if path.is_file():
                    archive.write(path, (Path(output.name) / path.relative_to(output)).as_posix())
    return {'output': str(output), 'zip': str(zip_path) if zip_path else None,
            'node_count': data['node_count'], 'video_count': data['video_count'],
            'status_counts': data['status_counts'], 'human_review': 'pending', 'published': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/offline_checkpoint_v2_20261022/manifest.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/offline-checkpoint-preview')
    parser.add_argument('--zip', action='store_true', help='Also create a portable ZIP beside the output directory')
    parser.add_argument('--zip-path', type=Path)
    parser.add_argument('--verify', type=Path, metavar='DIRECTORY', help='Verify an existing unpacked snapshot')
    args = parser.parse_args()
    if args.verify:
        result = verify_package(args.verify)
    else:
        zip_path = args.zip_path or args.output.with_suffix('.zip') if args.zip or args.zip_path else None
        result = package(args.manifest, args.output, zip_path=zip_path)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
