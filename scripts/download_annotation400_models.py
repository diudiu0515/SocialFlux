"""Fetch public model weights with resumable ranges and upstream SHA checks.

Hub metadata uses the configured network route. Large public CDN objects are
downloaded directly; no project content or credentials are sent to the Hub.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import requests
from huggingface_hub import get_hf_file_metadata, hf_hub_url, list_repo_files

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 8 * 1024 * 1024


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(CHUNK), b''):
            h.update(data)
    return h.hexdigest()


def download(repo, name, directory, workers=8):
    target = directory / name
    for attempt in range(5):
        try:
            meta = get_hf_file_metadata(hf_hub_url(repo, name), timeout=30)
            break
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2)
    expected = meta.etag.strip('"')
    if target.exists() and target.stat().st_size == meta.size:
        if len(expected) != 64 or digest(target) == expected:
            print(json.dumps({'file': name, 'status': 'cached'}), flush=True)
            return
    parts = directory / '.ranges' / (name.replace('/', '_') + '.' + expected)
    parts.mkdir(parents=True, exist_ok=True)

    def get_part(index):
        first = index * CHUNK
        last = min(meta.size, first + CHUNK) - 1
        path = parts / str(index)
        if path.exists() and path.stat().st_size == last - first + 1:
            return
        for attempt in range(6):
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    with session.get(meta.location, headers={'Range': f'bytes={first}-{last}'}, stream=True, timeout=(15, 60)) as response:
                        response.raise_for_status()
                        if meta.size > CHUNK:
                            assert response.status_code == 206
                            assert response.headers['Content-Range'].startswith(f'bytes {first}-{last}/')
                        tmp = path.with_suffix('.partial')
                        with tmp.open('wb') as out:
                            for block in response.iter_content(1024 * 256):
                                out.write(block)
                        assert tmp.stat().st_size == last - first + 1
                        tmp.replace(path)
                return
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(2 + attempt)

    count = (meta.size + CHUNK - 1) // CHUNK
    print(json.dumps({'file': name, 'status': 'downloading', 'bytes': meta.size, 'parts': count}), flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, _ in enumerate(pool.map(get_part, range(count)), 1):
            if done % 8 == 0 or done == count:
                print(json.dumps({'file': name, 'parts_done': done, 'parts': count}), flush=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + '.assembling')
    with tmp.open('wb') as out:
        for index in range(count):
            with (parts / str(index)).open('rb') as f:
                for block in iter(lambda: f.read(CHUNK), b''):
                    out.write(block)
    assert tmp.stat().st_size == meta.size
    actual = digest(tmp)
    if len(expected) == 64:
        assert actual == expected, f'SHA256 mismatch for {repo}/{name}'
    tmp.replace(target)
    target.with_suffix(target.suffix + '.source.json').write_text(json.dumps({
        'repo': repo, 'filename': name, 'commit': meta.commit_hash,
        'bytes': meta.size, 'upstream_etag': expected, 'sha256': actual,
    }, indent=2) + '\n')
    for index in range(count):
        (parts / str(index)).unlink()
    # Interrupted attempts may leave an unused partial file. The final object
    # has already passed its upstream hash, so cleanup is not a download error.
    try:
        parts.rmdir()
    except OSError:
        pass
    print(json.dumps({'file': name, 'status': 'verified', 'sha256': actual}), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('model', choices=['kokoro', 'latentsync', 'liveportrait'])
    p.add_argument('--workers', type=int, default=8)
    a = p.parse_args()
    if a.model == 'kokoro':
        repo = 'hexgrad/Kokoro-82M'
        directory = ROOT / '.local_models/annotation400-kokoro'
        names = ['config.json', 'kokoro-v1_0.pth'] + ['voices/' + v + '.pt' for v in ['af_heart', 'af_sarah', 'am_michael', 'am_adam']]
    elif a.model == 'latentsync':
        repo = 'ByteDance/LatentSync-1.6'
        directory = ROOT / '.local_tools/annotation400-latentsync/checkpoints'
        names = ['whisper/tiny.pt', 'latentsync_unet.pt']
    else:
        repo = 'KlingTeam/LivePortrait'
        directory = ROOT / '.local_tools/annotation400-liveportrait-code/pretrained_weights'
        names = [n for n in list_repo_files(repo) if n.startswith(('liveportrait/', 'insightface/'))]
    for name in names:
        download(repo, name, directory, workers=a.workers)


if __name__ == '__main__':
    main()
