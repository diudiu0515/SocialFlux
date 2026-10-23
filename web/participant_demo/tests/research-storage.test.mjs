import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {isDeepStrictEqual} from 'node:util';
import {restoreResearchDelta, unpackStored} from '../lib/research-storage.ts';
import {restoreMediaSnapshot} from '../lib/research-snapshots.ts';

const read = name => JSON.parse(readFileSync(new URL('../data/' + name, import.meta.url)));
const current = unpackStored(read('research-server.json'));
const previous = unpackStored(read('research-20261022-v1-server.json'));
const delta = unpackStored(read('research-previous-delta-server.json'));
const history = read('research-media-history.json');
const storedHistory = unpackStored(read('research-media-history-server.json'));

test('the real derived previous release restores the entire frozen object exactly', () => {
  const beforeBase = JSON.stringify(current), beforeDelta = JSON.stringify(delta);
  const restored = restoreResearchDelta(current, delta);
  assert.ok(isDeepStrictEqual(restored, previous), 'Every frozen field, item, private blob, trajectory and assignment must roundtrip');
  assert.equal(restored.dataset_sha256, '6dffb119b7295ea192bb8fc047d6e90df624df44b44108f9bb391e4b1b958184');
  assert.equal(delta.base_dataset_sha256, current.dataset_sha256);
  assert.ok(delta.shared_evidence_blob_keys.length > 0);
  assert.equal(Object.keys(restored.evidence_blobs).length, Object.keys(previous.evidence_blobs).length);
  assert.equal(Object.keys(delta.values.evidence_blobs).length + delta.shared_evidence_blob_keys.length, Object.keys(previous.evidence_blobs).length);
  for (const key of delta.shared_fields) assert.notEqual(restored[key], current[key], 'Frozen releases retain separate mutable runtime objects');
  assert.equal(JSON.stringify(current), beforeBase, 'Restoring a release must not mutate its current base');
  assert.equal(JSON.stringify(delta), beforeDelta, 'Derived storage remains immutable');
});

test('gzip history preserves every original snapshot and restores frozen assignments and media', () => {
  assert.ok(isDeepStrictEqual(storedHistory, history), 'The entire historical snapshot array must roundtrip');
  assert.ok(history.length > 0);
  const first = read('research-annotation400-first-overlay.json');
  for (const snapshot of [first, ...storedHistory].filter(x => x.dataset_sha256)) {
    const restored = restoreMediaSnapshot(current, snapshot);
    assert.equal(restored.dataset_sha256, snapshot.dataset_sha256);
    assert.ok(isDeepStrictEqual(restored.assignments, snapshot.assignments));
    assert.equal(restored.items.length, snapshot.items.length);
    const rows = new Map(snapshot.items.map(x => [x.id, x]));
    for (const item of restored.items) {
      const frozen = rows.get(item.id);
      assert.equal(item.item_sha256, frozen.item_sha256);
      assert.ok(isDeepStrictEqual(item.media, frozen.media), 'Historical media metadata, URLs and SHA must remain exact');
      assert.ok(isDeepStrictEqual(item.coverage, frozen.coverage));
      assert.equal(!!item.public_video, frozen.has_video);
    }
  }
});

function tiny() {
  const base = {dataset_sha256: 'current', evidence_blobs: {shared: 'same-encoded-blob', future: 'not-in-previous'},
    rubric: {rubric: 'same'}, t4: [{id: 'frozen-trajectory'}], sampling: {seed: 42}, future_only: true};
  const delta = {format: 'socialflux_research_delta_v1', base_dataset_sha256: 'current', dataset_sha256: 'old',
    shared_fields: ['rubric', 't4', 'sampling'], shared_evidence_blob_keys: ['shared'],
    values: {dataset_sha256: 'old', evidence_blobs: {old_only: 'previous-encoded-blob'}, items: [{id: 'old-item'}]}};
  return {base, delta};
}
test('unlisted current fields and blobs never become part of an older release', () => {
  const {base, delta} = tiny(); const restored = restoreResearchDelta(base, delta);
  assert.equal(restored.future_only, undefined);
  assert.deepEqual(restored.evidence_blobs, {old_only: 'previous-encoded-blob', shared: 'same-encoded-blob'});
  assert.deepEqual(restored.items, [{id: 'old-item'}]);
  restored.t4[0].machine = {answer: 'previous-only'};
  restored.rubric.rubric = 'previous-only';
  assert.equal(base.t4[0].machine, undefined, 'Runtime calibration must not mutate a different frozen release');
  assert.equal(base.rubric.rubric, 'same');
});
test('wrong bases, targets, missing references, collisions and malformed deltas fail closed', () => {
  const changes = [
    ({delta}) => delta.format = 'unknown',
    ({delta}) => delta.base_dataset_sha256 = 'other',
    ({delta}) => delta.dataset_sha256 = 'forged-old',
    ({delta}) => delta.values.dataset_sha256 = 'forged-old',
    ({delta}) => delta.shared_fields.push('private'),
    ({delta}) => delta.shared_fields.push('rubric'),
    ({base}) => delete base.rubric,
    ({delta}) => delta.values.rubric = {collision: true},
    ({delta}) => delta.shared_evidence_blob_keys.push('missing'),
    ({delta}) => delta.shared_evidence_blob_keys.push('shared'),
    ({delta}) => delta.values.evidence_blobs.shared = 'collision',
    ({delta}) => delta.shared_evidence_blob_keys = null,
    ({delta}) => delta.shared_fields = null,
    ({delta}) => delta.values.evidence_blobs = [],
  ];
  for (const change of changes) {const values = tiny(); change(values); assert.throws(() => restoreResearchDelta(values.base, values.delta));}
});
