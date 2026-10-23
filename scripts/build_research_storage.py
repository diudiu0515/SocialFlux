"""Derive smaller runtime files without changing any frozen research material.

Keep the full inputs as local archives. A deployment uses the derived previous
release and compressed media history instead of shipping those two full inputs.
"""
import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

FORMAT = 'socialflux_research_delta_v1'
SHARED_FIELDS = ('rubric', 't4', 'sampling')
PREVIOUS_INPUT = 'research-20261022-v1-server.json'
HISTORY_INPUT = 'research-media-history.json'
PREVIOUS_OUTPUT = 'research-previous-delta-server.json'
HISTORY_OUTPUT = 'research-media-history-server.json'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unpack(raw):
    return json.loads(gzip.decompress(base64.b64decode(json.loads(raw)['gzip_base64'])))


def pack(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    return (json.dumps({'gzip_base64': base64.b64encode(gzip.compress(raw, mtime=0)).decode()},
                       separators=(',', ':')) + '\n').encode()


def restore_previous(current, delta):
    if (delta.get('format') != FORMAT
            or delta.get('base_dataset_sha256') != current.get('dataset_sha256')):
        raise ValueError('Research storage base/format mismatch')
    fields, keys = delta['shared_fields'], delta['shared_evidence_blob_keys']
    if (not isinstance(fields, list) or len(fields) != len(set(fields))
            or not set(fields) <= set(SHARED_FIELDS)
            or not isinstance(keys, list) or len(keys) != len(set(keys))):
        raise ValueError('Invalid shared research references')
    result = deepcopy(delta['values'])
    for key in fields:
        if key in result or key not in current:
            raise ValueError('Missing or conflicting shared research field')
        result[key] = deepcopy(current[key])
    for key in keys:
        if key in result['evidence_blobs'] or key not in current['evidence_blobs']:
            raise ValueError('Missing or conflicting shared evidence blob')
        result['evidence_blobs'][key] = current['evidence_blobs'][key]
    if result.get('dataset_sha256') != delta.get('dataset_sha256'):
        raise ValueError('Reconstructed research dataset mismatch')
    return result


def derive_previous(current, previous):
    # Canonical bytes distinguish 10 from 10.0; Python equality alone does not.
    fields = [key for key in SHARED_FIELDS if key in previous and key in current
              and canonical(previous[key]) == canonical(current[key])]
    keys = sorted(key for key, value in previous['evidence_blobs'].items()
                  if key in current['evidence_blobs'] and value == current['evidence_blobs'][key])
    values = {key: deepcopy(value) for key, value in previous.items() if key not in fields}
    values['evidence_blobs'] = {key: value for key, value in previous['evidence_blobs'].items() if key not in keys}
    delta = dict(format=FORMAT, base_dataset_sha256=current['dataset_sha256'],
                 dataset_sha256=previous['dataset_sha256'], shared_fields=fields,
                 shared_evidence_blob_keys=keys, values=values)
    if canonical(restore_previous(current, delta)) != canonical(previous):
        raise ValueError('Research storage roundtrip changed frozen content')
    return delta


def build(site):
    directory = Path(site).resolve() / 'data'
    inputs = {name: (directory / name).read_bytes()
              for name in ('research-server.json', PREVIOUS_INPUT, HISTORY_INPUT)}
    current, previous = unpack(inputs['research-server.json']), unpack(inputs[PREVIOUS_INPUT])
    history = json.loads(inputs[HISTORY_INPUT])
    delta = derive_previous(current, previous)
    outputs = {PREVIOUS_OUTPUT: pack(delta), HISTORY_OUTPUT: pack(history)}
    reconstructed = restore_previous(current, unpack(outputs[PREVIOUS_OUTPUT]))
    if (canonical(reconstructed) != canonical(previous)
            or canonical(unpack(outputs[HISTORY_OUTPUT])) != canonical(history)):
        raise ValueError('Compressed research storage roundtrip changed content')
    for name, raw in outputs.items():
        (directory / name).write_bytes(raw)
    if any((directory / name).read_bytes() != raw for name, raw in inputs.items()):
        raise ValueError('Frozen research inputs changed while deriving storage')
    original_bytes = len(inputs[PREVIOUS_INPUT]) + len(inputs[HISTORY_INPUT])
    derived_bytes = sum(map(len, outputs.values()))
    return dict(site=str(Path(site).resolve()), format=FORMAT,
        base_dataset_sha256=current['dataset_sha256'], previous_dataset_sha256=previous['dataset_sha256'],
        inputs={name: dict(sha256=sha(raw), bytes=len(raw), unchanged=True) for name, raw in inputs.items()},
        outputs={name: dict(sha256=sha(raw), bytes=len(raw)) for name, raw in outputs.items()},
        shared_fields=delta['shared_fields'], shared_evidence_blobs=len(delta['shared_evidence_blob_keys']),
        remaining_previous_evidence_blobs=len(delta['values']['evidence_blobs']),
        original_previous_canonical_sha256=sha(canonical(previous)),
        reconstructed_previous_canonical_sha256=sha(canonical(reconstructed)),
        history_canonical_sha256=sha(canonical(history)), history_snapshots=len(history),
        previous_exact_roundtrip=True, history_exact_roundtrip=True,
        original_runtime_bytes=original_bytes, derived_runtime_bytes=derived_bytes,
        bytes_saved_when_originals_excluded=original_bytes-derived_bytes,
        replaced_runtime_imports=[PREVIOUS_INPUT, HISTORY_INPUT],
        savings_scope='Source input bytes only; dist bundling may minify JSON. Measure the rebuilt archive independently.',
        frozen_inputs_preserved_locally=True, media_modified=False, dataset_hashes_modified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', action='append', type=Path, required=True)
    parser.add_argument('--audit', type=Path)
    args = parser.parse_args()
    results = [build(site) for site in args.site]
    audit = dict(format='socialflux_research_storage_roundtrip_audit_v1',
        created_at=datetime.now(timezone.utc).isoformat(), results=results,
        archive_size_requires_fresh_build=True, published=False)
    if args.audit:
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps([dict(site=r['site'], shared_evidence_blobs=r['shared_evidence_blobs'],
        bytes_saved_when_originals_excluded=r['bytes_saved_when_originals_excluded'],
        outputs=r['outputs'], exact_roundtrip=True) for r in results]))


if __name__ == '__main__':
    main()
