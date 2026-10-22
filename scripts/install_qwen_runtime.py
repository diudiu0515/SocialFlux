#!/usr/bin/env python3
"""Install pinned Qwen runtime wheels using resumable, verified transfers."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler

from packaging.requirements import Requirement
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/qwen_deployment'


def compatible_wheel(files, tags):
    ranking = {tag: i for i, tag in enumerate(tags)}
    candidates = []
    for item in files:
        if item.get('packagetype') != 'bdist_wheel' or item.get('yanked'):
            continue
        _, _, _, wheel_tags = parse_wheel_filename(item['filename'])
        ranks = [ranking[t] for t in wheel_tags if t in ranking]
        if ranks:
            candidates.append((min(ranks), item['filename'], item))
    if not candidates:
        raise ValueError('No compatible non-yanked wheel')
    return min(candidates, key=lambda x: x[:2])[2]


def main():
    config = json.loads((ROOT / 'configs/qwen_local_deployment.json').read_text())
    work = WORK
    uv = str(work / 'venv/bin/uv')
    python = str(work / 'venv/bin/python')
    env = dict(os.environ)
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        env.pop(key, None)
    env.update(UV_CACHE_DIR=str(work / 'cache/uv'), UV_HTTP_TIMEOUT='120', TMPDIR=str(work / 'tmp'))
    source = work / 'requirements.in'
    source.write_text('vllm==' + config['vllm_version'] + '\n')
    resolved = work / 'requirements.resolved.txt'
    compile_cmd = [uv, 'pip', 'compile', '--index-url', 'https://pypi.org/simple',
                   '--python', python, str(source), '--output-file', str(resolved)]
    result = subprocess.run(compile_cmd + ['--offline'], env=env, stdout=subprocess.DEVNULL)
    if result.returncode:
        subprocess.run(compile_cmd, env=env, check=True, timeout=600, stdout=subprocess.DEVNULL)
    requirements = [Requirement(s.strip()) for s in resolved.read_text().splitlines()
                    if s.strip() and not s.strip().startswith(('#', '--'))]
    tags = list(sys_tags())
    meta = work / 'wheel_metadata'
    meta.mkdir(parents=True, exist_ok=True)

    def fetch(req):
        version = next(iter(req.specifier)).version
        path = meta / (req.name + '-' + version + '.json')
        if path.exists():
            return json.loads(path.read_text())
        for attempt in range(4):
            try:
                opener = build_opener(ProxyHandler({}))
                with opener.open('https://pypi.org/pypi/' + req.name + '/' + version + '/json', timeout=30) as response:
                    data = json.loads(response.read())
                selected = compatible_wheel(data['urls'], tags)
                record = {k: selected[k] for k in ('filename', 'url', 'size', 'digests')}
                record.update(name=req.name, version=version)
                path.write_text(json.dumps(record, indent=2) + '\n')
                print(json.dumps({'package': req.name, 'bytes': record['size']}), flush=True)
                return record
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(1 + attempt)
    with ThreadPoolExecutor(max_workers=8) as pool:
        wheels = list(pool.map(fetch, requirements))
    directory = work / 'wheels'
    directory.mkdir(exist_ok=True)
    lines = []
    for item in wheels:
        lines += [item['url'], '  dir=' + str(directory), '  out=' + item['filename'],
                  '  checksum=sha-256=' + item['digests']['sha256']]
    inputs = work / 'wheels.aria2'
    inputs.write_text('\n'.join(lines) + '\n')
    lock = work / 'requirements.wheels.txt'
    lock.write_text('\n'.join(x['name'] + '==' + x['version'] + ' --hash=sha256:' + x['digests']['sha256'] for x in wheels) + '\n')
    print(json.dumps({'stage': 'downloading_wheels', 'packages': len(wheels),
                      'GB': round(sum(x['size'] for x in wheels) / 1e9, 3)}), flush=True)
    command = ['aria2c', '--input-file=' + str(inputs), '--max-concurrent-downloads=8',
               '--max-connection-per-server=8', '--split=8', '--min-split-size=1M',
               '--continue=true', '--check-integrity=true', '--auto-file-renaming=false',
               '--allow-overwrite=true', '--file-allocation=none', '--max-tries=5',
               '--retry-wait=5', '--summary-interval=30', '--console-log-level=warn']
    for attempt in range(3):
        result = subprocess.run(command, env=env, timeout=7200)
        if result.returncode == 0:
            break
    else:
        raise RuntimeError('Wheel transfers failed after three resumable attempts')
    # Check the exact artifacts again before an offline installation.
    for item in wheels:
        path = directory / item['filename']
        if path.stat().st_size != item['size']:
            raise ValueError('Wrong wheel size: ' + path.name)
        with path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        if digest != item['digests']['sha256']:
            raise ValueError('Wrong wheel checksum: ' + path.name)
    subprocess.run([uv, 'pip', 'install', '--python', python, '--no-index', '--find-links',
                    str(directory), '--require-hashes', '-r', str(lock)], env=env, check=True, timeout=600)
    subprocess.run([uv, 'pip', 'check', '--python', python], env=env, check=True, timeout=60)
    print('Qwen runtime dependency installation complete', flush=True)


if __name__ == '__main__':
    main()
