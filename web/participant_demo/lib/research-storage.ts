import {gunzipSync} from 'node:zlib';

export function unpackStored<T>(value: {gzip_base64: string}): T {
  return JSON.parse(gunzipSync(Buffer.from(value.gzip_base64, 'base64')).toString()) as T;
}

type ResearchBase = {dataset_sha256: string; evidence_blobs: Record<string, string>};
type Delta = {format: string; base_dataset_sha256: string; dataset_sha256: string;
  shared_fields: string[]; shared_evidence_blob_keys: string[];
  values: Record<string, unknown> & ResearchBase};
const sharedFields = new Set(['rubric', 't4', 'sampling']);

// Derived storage only: restore the exact frozen previous object without
// borrowing any unlisted current fields or extra current evidence blobs.
export function restoreResearchDelta<T extends ResearchBase>(base: T, value: unknown): T {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid research delta');
  const delta = value as Delta;
  if (delta.format !== 'socialflux_research_delta_v1') throw new Error('Unsupported research delta format');
  if (delta.base_dataset_sha256 !== base.dataset_sha256) throw new Error('Research delta base dataset mismatch');
  const own = delta.values;
  if (!own || typeof own !== 'object' || Array.isArray(own) || !own.evidence_blobs || typeof own.evidence_blobs !== 'object' || Array.isArray(own.evidence_blobs)) throw new Error('Invalid research delta values');
  if (typeof delta.dataset_sha256 !== 'string' || !delta.dataset_sha256 || own.dataset_sha256 !== delta.dataset_sha256) throw new Error('Research delta frozen dataset mismatch');
  if (!Array.isArray(delta.shared_fields) || new Set(delta.shared_fields).size !== delta.shared_fields.length) throw new Error('Invalid shared research fields');
  if (!Array.isArray(delta.shared_evidence_blob_keys) || new Set(delta.shared_evidence_blob_keys).size !== delta.shared_evidence_blob_keys.length) throw new Error('Invalid shared evidence references');
  const restored: Record<string, unknown> = {...own};
  const source = base as unknown as Record<string, unknown>;
  for (const key of delta.shared_fields) {
    if (!sharedFields.has(key) || !Object.hasOwn(source, key)) throw new Error('Missing or unsupported shared research field');
    if (Object.hasOwn(own, key)) throw new Error('Shared research field conflicts with frozen values');
    restored[key] = structuredClone(source[key]);
  }
  const shared = delta.shared_evidence_blob_keys.map(key => {
    if (typeof key !== 'string' || !Object.hasOwn(base.evidence_blobs, key)) throw new Error('Missing shared evidence blob');
    if (Object.hasOwn(own.evidence_blobs, key)) throw new Error('Shared evidence blob conflicts with frozen values');
    return [key, base.evidence_blobs[key]];
  });
  restored.evidence_blobs = {...own.evidence_blobs, ...Object.fromEntries(shared)};
  return restored as T;
}
