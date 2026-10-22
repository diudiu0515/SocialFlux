// Server only: never import this bundle from client components.
import {gunzipSync} from 'node:zlib';
import compressed from '../data/gate2-review-server.json';
import {InputError} from './protocol';
import {reviewApplies, type Gate2Workflow} from './gate2-protocol';
import {registryBundle, type ReviewRegistry} from './gate2-registry';
const registry = JSON.parse(gunzipSync(Buffer.from(compressed.gzip_base64, 'base64')).toString()) as ReviewRegistry;
export const gate2Hash = registry.current;
export const gate2DatasetHash = registry.versions.find(b => b.sha256 === registry.current)?.dataset_sha256;
export function gate2Tasks(scenes: string[], workflow?: Gate2Workflow, track?: string) {
  if (!workflow) return [];
  const bundle = registryBundle(registry, workflow.packet_sha256);
  if (!bundle) throw new InputError('环境核对版本不匹配，请保留记录并联系研究者。');
  return bundle.tasks.filter(t => scenes.includes(t.scene_id) && reviewApplies(t, track));
}
export function gate2Material(scenes: string[], workflow: Gate2Workflow | undefined, phase: string, track?: string) {
  if (!workflow || phase === 'blind') return [];
  if (track === 't4' && !['t4_review', 'complete'].includes(phase)) return [];
  return gate2Tasks(scenes, workflow, track).filter(t => phase !== 'gate2' || t.stage === 'independent').map(({machine: _machine, ...task}) => task);
}
export function gate2Export(scenes: string[], workflow: Gate2Workflow | undefined, track?: string) {
  if (!workflow) return null;
  return {packet_sha256: workflow.packet_sha256, independent_locked_at: workflow.independentLockedAt || null,
    answers: workflow.answers, task_hashes: Object.fromEntries(gate2Tasks(scenes, workflow, track).map(t => [t.id, t.sha256])),
    formal_admission: false, status: 'individual_human_review_requires_aggregation'};
}
