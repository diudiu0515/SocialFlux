"""Compare old/new public motion curves on CPU without changing any media."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REQUEST_ROOT = ROOT / 'data/offline_annotation400_en_20261022/local_av'
CURRENT_SOURCE = ROOT / 'scripts/animate_annotation400_local.py'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_controls(path):
    """Load only pure rule functions; never import a renderer or initialize GPU."""
    tree = ast.parse(Path(path).read_text())
    names = {'affirmed', 'public_motion_cues', 'controls'}
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    scope = {'json': json, 'math': math, 're': re}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), scope)
    version = 'public_motion_cues_v1_unversioned'
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CONTROLS_VERSION' for t in node.targets):
            version = ast.literal_eval(node.value)
    return scope, version


def audit(old_source, output=None):
    old_source = Path(old_source).resolve()
    old_scope, old_version = read_controls(old_source)
    new_scope, new_version = read_controls(CURRENT_SOURCE)
    old_hash, new_hash = sha(old_source), sha(CURRENT_SOURCE)
    output = output or REQUEST_ROOT / 'controls_audit' / old_hash / new_hash / 'report.json'
    rows = []
    for path in sorted(REQUEST_ROOT.glob('GPT50_*/*/request.json')):
        request = json.loads(path.read_text())
        speech = json.loads(path.with_name('speech.json').read_text())
        duration = speech['duration_seconds']
        frames = math.ceil(duration * 25)
        before = [old_scope['controls'](request, i / 25) for i in range(frames)]
        after = [new_scope['controls'](request, i / 25) for i in range(frames)]
        differences = {}
        for key in before[0]:
            changed = [i for i in range(frames) if abs(before[i][key] - after[i][key]) > 1e-12]
            if changed:
                first = changed[0]
                differences[key] = {'max_absolute_difference': max(abs(before[i][key] - after[i][key]) for i in changed),
                    'first_changed_seconds': first / 25, 'first_old': before[first][key], 'first_new': after[first][key]}
        motion_path = path.with_name('motion.json')
        motion = json.loads(motion_path.read_text()) if motion_path.exists() else None
        old_behavior = json.dumps(request['source_observable_expression'].get('behavioral_cues', [])).lower()
        rows.append({'node_id': request['node_id'], 'scenario_id': request['scenario_id'], 'location': request['location'],
            'spec_sha256': request['spec_sha256'], 'request_sha256': sha(path),
            'public_expression': request['source_observable_expression'],
            'public_expression_sha256': digest(request['source_observable_expression']),
            'duration_seconds': duration, 'frames_compared': frames, 'fps': 25,
            'old_selected_cues': ['facial_expression', 'behavioral_cues' if 'nod' in old_behavior else 'gaze'],
            'new_selected_cues': new_scope['public_motion_cues'](request)['selected_cues'],
            'old_control_curve_sha256': digest(before), 'new_control_curve_sha256': digest(after),
            'changed_channels': differences, 'needs_rerender': bool(differences),
            'motion_at_audit': {'receipt_sha256': sha(motion_path), 'asset_sha256': motion.get('sha256'),
                'spec_sha256': motion.get('spec_sha256'), 'controls_version': motion.get('controls_version'),
                'controls_source_sha256': motion.get('controls_source_sha256')} if motion else None})
    assert len(rows) == 150
    report = {'format': 'socialflux_public_motion_controls_audit_v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'old_source_path': str(Path(old_source).relative_to(ROOT)), 'old_source_sha256': old_hash,
        'new_source_path': str(CURRENT_SOURCE.relative_to(ROOT)), 'new_source_sha256': new_hash,
        'old_controls_version': old_version, 'new_controls_version': new_version,
        'scope': 'Public request expressions only; full control curves at 25 fps; no media changes or GPU execution.',
        'node_count': len(rows), 'changed_node_count': sum(r['needs_rerender'] for r in rows),
        'rerender_node_ids': [r['node_id'] for r in rows if r['needs_rerender']],
        'unchanged_control_nodes': [r['node_id'] for r in rows if not r['needs_rerender']], 'nodes': rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = output.parent / 'animate_annotation400_local.after.py'
    snapshot.write_bytes(CURRENT_SOURCE.read_bytes())
    assert sha(snapshot) == new_hash
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('node_count', 'changed_node_count', 'rerender_node_ids',
                                           'old_source_sha256', 'new_source_sha256')}))
    print(str(output))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--old-source', type=Path, required=True)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    audit(a.old_source, a.output)
