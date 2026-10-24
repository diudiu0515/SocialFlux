"""Build a private reviewer index from durable receipts, without editing source data."""
import argparse
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path
import time
import uuid


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = value.encode() if isinstance(value, str) else value
    if path.exists() and path.read_bytes() == raw:
        return
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def archive(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Source receipts and derived archive must be separate directories')
    rows, people, errors = [], {}, []
    for folder in sorted(source.iterdir()):
        if not folder.is_dir():
            continue
        versions = []
        for path in folder.glob('*.json'):
            try:
                raw = path.read_bytes()
                data = json.loads(raw)
                revision = int(data.get('revision', path.stem))
                versions.append((revision, path, raw, data))
            except (ValueError, TypeError, OSError):
                errors.append(str(path.relative_to(source)))
        if not versions:
            continue
        versions.sort(key=lambda x: x[0])
        latest = versions[-1][3]
        alias = str(latest.get('reviewer_alias') or latest.get('alias') or '未命名')
        # Treat aliases as labels, never filesystem paths or verified real identities.
        person_key = hashlib.sha256(alias.encode()).hexdigest()[:24]
        session_key = hashlib.sha256(folder.name.encode()).hexdigest()[:24]
        relative = Path('reviewers') / person_key / session_key
        for revision, path, raw, data in versions:
            target = output / relative / 'versions' / f'{revision}.json'
            if target.exists() and target.read_bytes() != raw:
                raise ValueError('Archived revision changed: ' + str(path))
            atomic(target, raw)
        atomic(output / relative / 'latest.json', versions[-1][2])
        assignment = latest.get('assignment') or {}
        if not isinstance(assignment, dict):
            assignment = {}
        row = dict(reviewer=alias, session_id=folder.name,
                   release=latest.get('release', ''), assignment=assignment.get('label', assignment.get('id', '')),
                   status=latest.get('status', ''), latest_revision=versions[-1][0],
                   archived_versions=len(versions), created_at=latest.get('created_at', ''), submitted_at=latest.get('submitted_at') or '',
                   latest_file=str(relative / 'latest.json'))
        rows.append(row)
        people.setdefault(alias, []).append((row, latest, versions))
    fields = ['reviewer','session_id','release','assignment','status','latest_revision','archived_versions','created_at','submitted_at','latest_file']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    # Avoid spreadsheet formulas in user-supplied aliases or other text fields.
    writer.writerows({k: "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in row.items()} for row in rows)
    atomic(output / 'summary.csv', '\ufeff'+stream.getvalue())
    atomic(output / 'index.json', json.dumps({'reviewers':len(people),'sessions':len(rows),'unreadable_receipts':errors,'records':rows}, ensure_ascii=False, indent=2)+'\n')
    esc = lambda value: html.escape(str(value), quote=True)
    body = ['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>标注人档案</title><style>body{max-width:1100px;margin:32px auto;padding:0 20px;font:16px/1.6 system-ui;color:#173d31}details{border:1px solid #d5ded8;border-radius:8px;padding:12px;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f6f1;padding:16px;color:#222}summary{cursor:pointer}a{color:#17644d}</style><h1>按标注编号查看档案</h1>',
            '<p>此文件包含私人标注，请勿上传到公开网站。编号不是经过验证的真实身份；同名会话独立保留。</p>',
            f'<p>{len(people)} 个编号 · {len(rows)} 份会话 · <a href="summary.csv">下载汇总 CSV</a></p>',
            '<p>服务器每 60 秒扫描已保存回执。下载到本地的此页面是当时的快照，需重新下载才会更新。草稿不等于最终提交，也不自动成为 GT。</p>']
    if errors:
        body.append('<p>部分回执无法读取，原文件仍保留：'+esc(', '.join(errors))+'</p>')
    for alias, sessions in sorted(people.items()):
        body.append('<details open><summary><b>'+esc(alias)+f'</b> · {len(sessions)} 份会话</summary>')
        for row, latest, versions in sessions:
            body.append('<details><summary>'+esc(row['release'])+' · '+esc(row['assignment'])+' · '+esc(row['status'])+' · 版本 '+esc(row['latest_revision'])+'</summary>')
            body.append('<p>会话 '+esc(row['session_id'])+' · <a href="'+esc(row['latest_file'])+'">下载完整 JSON</a></p>')
            for label, key in [('保存的草稿答案','saved_draft_answers'),('独立作答','blind_responses'),('人工修订 GT','machine_assisted_gt'),('T4 评分','independent_t4_ratings'),('答案','answers'),('环境核对','gate2_human_review')]:
                if latest.get(key):
                    body.append('<h3>'+label+'</h3><pre>'+esc(json.dumps(latest[key],ensure_ascii=False,indent=2))+'</pre>')
            body.append('<details><summary>所有保存版本</summary>')
            for rev, _, raw, record in versions:
                body.append('<details><summary>版本 '+str(rev)+'</summary><pre>'+esc(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></details>')
            body.append('</details></details>')
        body.append('</details>')
    atomic(output / 'index.html', ''.join(body))
    return {'reviewers':len(people),'sessions':len(rows),'unreadable_receipts':len(errors)}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--watch', action='store_true')
    args=parser.parse_args()
    while True:
        try:
            print(json.dumps(archive(args.receipts,args.output)),flush=True)
        except Exception as error:
            if not args.watch:
                raise
            print('Archive update failed: '+str(error),flush=True)
        if not args.watch:
            break
        time.sleep(60)
