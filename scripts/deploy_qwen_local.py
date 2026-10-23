#!/usr/bin/env python3
"""Deploy local Qwen, optionally running an explicitly selected diagnostic.

Long-running deployment state is written atomically to status.json. Never marks
the deployment ready before a real generation, or the diagnostic completed
before every prepared checkpoint has been attempted.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared.artifacts import atomic_json

WORK = ROOT / 'build/qwen_deployment'


def run(command, logfile, *, env=None, timeout=None):
    with (WORK / logfile).open('a') as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=timeout)


def direct_environment():
    result = dict(os.environ)
    for key in ('HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'https_proxy', 'http_proxy', 'all_proxy'):
        result.pop(key, None)
    result.update(UV_CACHE_DIR=str(WORK / 'cache/uv'), UV_HTTP_TIMEOUT='120',
                  UV_CONCURRENT_DOWNLOADS='8', TMPDIR=str(WORK / 'tmp'))
    return result


def install(config, existing_pid):
    if existing_pid:
        deadline = time.monotonic() + 8 * 3600
        cmdline = Path('/proc') / str(existing_pid) / 'cmdline'
        while cmdline.exists():
            try:
                command = cmdline.read_bytes()
                if not any(value in command for value in (b'qwen_deployment/venv/bin/uv', b'install_qwen_runtime.py')):
                    break
            except FileNotFoundError:
                break
            if time.monotonic() > deadline:
                raise TimeoutError('Existing dependency installation exceeded eight hours')
            time.sleep(10)
    python = str(WORK / 'venv/bin/python')
    check = [python, '-c', 'import importlib.metadata as m; assert m.version("vllm") == ' + repr(config['vllm_version'])]
    if subprocess.run(check, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run([sys.executable, str(ROOT / 'scripts/install_qwen_runtime.py')],
            'install_pipeline.log', env=direct_environment(), timeout=8 * 3600)
    run([python, '-c', 'import vllm, torch; print(vllm.__version__, torch.__version__, torch.version.cuda); assert torch.cuda.device_count() == 4'],
        'runtime_check.log', timeout=180)
    with (WORK / 'requirements.lock.txt').open('w') as out:
        subprocess.run([python, '-m', 'pip', 'freeze'], stdout=out, check=True)


def download():
    command = ['aria2c', '--input-file=' + str(WORK / 'download.aria2'),
               '--max-concurrent-downloads=12', '--max-connection-per-server=4', '--split=4',
               '--min-split-size=8M', '--continue=true', '--check-integrity=true',
               '--auto-file-renaming=false', '--allow-overwrite=true', '--file-allocation=none',
               '--max-tries=5', '--retry-wait=5', '--summary-interval=60', '--console-log-level=warn']
    for attempt in range(3):
        try:
            run(command, 'download_pipeline.log', env=direct_environment(), timeout=12 * 3600)
            return
        except subprocess.CalledProcessError:
            if attempt == 2:
                raise
            time.sleep(10)


def api(path, payload=None):
    opener = build_opener(ProxyHandler({}))
    req = Request('http://127.0.0.1:8010/' + path,
                  data=json.dumps(payload).encode() if payload is not None else None,
                  headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=180 if payload else 5) as response:
        return json.loads(response.read())


def available_gpus(config):
    result = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.free,memory.total',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True)
    cards = [dict(zip(('index', 'free_mib', 'total_mib'), map(int, row.split(','))))
             for row in result.stdout.strip().splitlines()]
    selected = [c for c in cards if c['index'] in (0, 1, 2, 3)]
    ready = len(selected) == config['tensor_parallel_size'] and all(
        c['free_mib'] >= c['total_mib'] * config['gpu_memory_utilization'] for c in selected)
    return ready, selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--evaluation', type=Path)
    mode.add_argument('--deploy-only', action='store_true', help='Stop after a real smoke generation; do not evaluate prompts')
    parser.add_argument('--install-pid', type=int)
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    lock = (WORK / 'deployment.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    config = json.loads((ROOT / 'configs/qwen_local_deployment.json').read_text())
    evaluation = args.evaluation.resolve() if args.evaluation else None
    manifest = json.loads((evaluation / 'manifest.json').read_text()) if evaluation else None
    if manifest and manifest['deployment'] != config:
        raise ValueError('Prepared diagnostic and deployment configuration differ')
    state = {'pid': os.getpid(), 'model': config['model'], 'evaluation': str(evaluation) if evaluation else None,
             'diagnostic_requested': bool(evaluation),
             'ready': False, 'diagnostic_completed': False}
    def update(stage, **fields):
        state.update(stage=stage, updated_at_utc=datetime.now(timezone.utc).isoformat(), **fields)
        atomic_json(WORK / 'status.json', state)
        print(json.dumps(state), flush=True)
    try:
        update('downloading_and_installing')
        with ThreadPoolExecutor(max_workers=2) as pool:
            dependencies = pool.submit(install, config, args.install_pid)
            weights = pool.submit(download)
            try:
                dependencies.result()
            except Exception as exc:
                update('dependency_failure_download_continues', error_type=type(exc).__name__, error=str(exc))
                raise
            update('runtime_installed_waiting_for_weights')
            weights.result()
        gpu_deadline = time.monotonic() + 24 * 3600
        while True:
            ready, cards = available_gpus(config)
            if ready:
                break
            update('waiting_for_gpu', gpu_memory=cards)
            if time.monotonic() > gpu_deadline:
                raise TimeoutError('GPUs remained occupied for 24 hours; existing workloads were left running')
            time.sleep(30)
        update('starting_server')
        if json.loads((ROOT / 'configs/qwen_local_deployment.json').read_text()) != config:
            raise ValueError('Deployment configuration changed while downloading')
        run([str(WORK / 'venv/bin/supervisord'), '-c', 'configs/qwen.supervisord.conf'], 'service_start.log', timeout=30)
        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            try:
                models = api('v1/models')
                if config['model'] not in [m['id'] for m in models['data']]:
                    raise ValueError('Unexpected model identity at local endpoint')
                break
            except (OSError, ValueError, KeyError):
                status = subprocess.run([str(WORK / 'venv/bin/supervisorctl'), '-c',
                    'configs/qwen.supervisord.conf', 'status', 'socialflux-qwen'],
                    capture_output=True, text=True, timeout=10)
                if any(word in status.stdout.split() for word in ('FATAL', 'STOPPED', 'EXITED')):
                    raise RuntimeError('Qwen server stopped during startup: ' + status.stdout.strip())
                time.sleep(15)
        else:
            raise TimeoutError('Qwen service did not become healthy within one hour; inspect server.log')
        smoke = api('v1/chat/completions', {
            'model': config['model'], 'messages': [{'role': 'user', 'content': 'Return exactly the JSON object {"status":"ok"}.'}],
            'temperature': 0, 'max_tokens': 128, 'chat_template_kwargs': {'enable_thinking': False},
        })
        atomic_json(WORK / 'smoke.json', smoke)
        content = smoke['choices'][0]['message']['content'].strip()
        if json.loads(content) != {'status': 'ok'} or smoke['choices'][0]['finish_reason'] != 'stop':
            raise ValueError('Local model smoke generation failed')
        if args.deploy_only:
            update('ready', ready=True)
            return
        update('running_prompt_diagnostic', ready=True)
        runtime = Path(manifest['frozen_runtime'])
        run([sys.executable, str(runtime / 'scripts/evaluate_environment_prompt.py'),
             '--run-prepared', '--output', str(evaluation)], 'evaluation.log', timeout=6 * 3600)
        results = json.loads((evaluation / 'results.json').read_text())
        if results['summary']['attempted'] != len(manifest['cases']):
            raise ValueError('Diagnostic did not attempt every prepared case')
        update('completed', diagnostic_completed=True, summary=results['summary'])
    except Exception as exc:
        update('failed', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        lock.close()


if __name__ == '__main__':
    main()
