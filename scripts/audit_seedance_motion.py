"""Detect copied reference motion; this is not a semantic/human quality score."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import argparse
import json
import subprocess
import numpy as np
from scripts.seedance_state_batch import ROOT, OUT, load, save, sha, utc_now, native_frame_reference
from scripts.refresh_online_state_videos import TARGET

@lru_cache(maxsize=100)
def frames(path):
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-threads', '1', '-i', str(path),
        '-t', '4', '-vf', 'fps=6,crop=iw*0.5:ih*0.7:iw*0.25:ih*0.1,scale=96:96,format=gray',
        '-threads', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'])
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, 96, 96).astype(np.float32)

def compare(video, reference):
    a, b = frames(str(video)), frames(str(reference))
    n = min(len(a), len(b))
    if n < 20:
        raise ValueError('Insufficient full-clip frame sample')
    da, db = np.diff(a[:n], axis=0).ravel(), np.diff(b[:n], axis=0).ravel()
    corr = float(np.corrcoef(da, db)[0, 1]) if da.std() and db.std() else 1.0
    mae = float(np.abs(a[:n]-b[:n]).mean())
    windows = []
    for start in range(0, n-5, 6):
        aa, bb = a[start:start+6], b[start:start+6]
        xa, xb = np.diff(aa, axis=0).ravel(), np.diff(bb, axis=0).ravel()
        cc = float(np.corrcoef(xa, xb)[0, 1]) if xa.std() and xb.std() else 1.0
        mm = float(np.abs(aa-bb).mean())
        windows.append(dict(start_seconds=start/6, face_pixel_mae=mm, motion_correlation=cc))
    copied_windows = sum(w['face_pixel_mae'] < 12 and w['motion_correlation'] > .35 for w in windows)
    return dict(sampled_frames=n, face_pixel_mae=mae, temporal_motion_correlation=corr,
                windows=windows, reference_motion_suspected=bool((mae < 10 and corr > .25) or copied_windows >= 2))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', default='build/seedance-reference-motion-audit-20261023.json')
    args = p.parse_args()
    indexed, images = {}, {}
    for root in [OUT, TARGET]:
        for path in root.rglob('provider-state.json'):
            try:
                state = load(path)
            except FileNotFoundError:
                continue  # A completed revision may be moving into its archive.
            url = state.get('latest_query_response', {}).get('content', {}).get('video_url')
            native = path.parent / 'native.mp4'
            if state.get('status') == 'downloaded' and native.is_file() and url:
                indexed[url] = (native, state['video_sha256'])
            if (path.parent / 'frame-receipt.json').is_file():
                image_url = native_frame_reference(path.parent)
                images[image_url] = path.parent
    rows = load(OUT/'manifest.json')['nodes'] + load(TARGET/'manifest.json')['requests']
    def work(row):
        directory = ROOT / row['directory']
        try:
            state = load(directory / 'provider-state.json')
        except FileNotFoundError:
            return dict(node=row['node_id'], status='not_ready')
        if state.get('status') != 'downloaded':
            return dict(node=row['node_id'], status='not_ready')
        refs = [x['video_url']['url'] for x in state['request'].get('content', []) if x.get('type') == 'video_url']
        stills = [x['image_url']['url'] for x in state['request'].get('content', []) if x.get('type') == 'image_url']
        if stills:
            if refs or len(stills) != 1 or stills[0] not in images:
                return dict(node=row['node_id'], status='reference_not_resolved')
            reference = images[stills[0]]
            if sha(directory / 'native.mp4') != state['video_sha256']:
                raise ValueError('Output changed during still-reference audit')
            return dict(node=row['node_id'], scenario=row['scenario_id'], location=row['location'],
                status='original_still_reference', source_native_sha256=state['video_sha256'],
                reference_frame_sha256=sha(reference / 'native-last-frame.jpg'),
                reference=str(reference.relative_to(ROOT)), reference_motion_suspected=False,
                motion_scope='Input contains an original provider still and no motion timeline; expression semantics require visual review')
        if not refs:
            return dict(node=row['node_id'], status='text_only_generation', source_native_sha256=state['video_sha256'])
        if len(refs) != 1 or refs[0] not in indexed:
            return dict(node=row['node_id'], status='reference_not_resolved')
        reference, expected = indexed[refs[0]]
        native = directory / 'native.mp4'
        if sha(reference) != expected or sha(native) != state['video_sha256']:
            raise ValueError('Reference or output changed during motion audit')
        return dict(node=row['node_id'], scenario=row['scenario_id'], location=row['location'],
            status='compared', source_native_sha256=state['video_sha256'], reference_sha256=expected,
            reference=str(reference.relative_to(ROOT)), **compare(native, reference))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, rows))
    summary = dict(at=utc_now(), scope='Reference-copy diagnostic only; does not approve expression semantics',
        suspected=sum(r.get('reference_motion_suspected', False) for r in results),
        online_suspected=sum(r.get('reference_motion_suspected', False) and r.get('location')=='online' for r in results),
        offline_suspected=sum(r.get('reference_motion_suspected', False) and r.get('location')=='t2' for r in results),
        unresolved=sum(r['status'] in ('not_ready','reference_not_resolved') for r in results), results=results)
    save(ROOT / args.output, summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='results'}))

if __name__ == '__main__':
    main()
