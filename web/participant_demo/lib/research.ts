import {gate2Material, gate2Export, gate2DatasetHash} from './gate2';
// Server-only: this module is imported exclusively by API/store modules.
import {gunzipSync} from 'node:zlib';
import compressed from '../data/research-server.json';
import previousDeltaCompressed from '../data/research-previous-delta-server.json';
import firstMediaSnapshot from '../data/research-annotation400-first-overlay.json';
import mediaHistoryCompressed from '../data/research-media-history-server.json';
import {restoreResearchDelta, unpackStored} from './research-storage';
import {restoreMediaSnapshot, type MediaSnapshot} from './research-snapshots';
import calibration from '../data/claude-calibration-server.json';
import {InputError, type Question} from './protocol';
import {activeScene, dimensions, type Workflow} from './research-protocol';

export type Assignment = {id: string; track: string; label: string; scene_ids: string[]; item_ids: string[]};
type Item = {id: string; scene_id: string; task: string; item_sha256: string; public_text: Question; public_video: Question | null; media: {asset_id: string; sha256: string; url: string; evidence_ids: string[]; spoken_scope?: string}[]; coverage: unknown};
// Evidence schemas are versioned in the Python release builder; pass through only at the gated endpoint.
type Trajectory = {id: string; packet: Record<string, any>; packet_sha256: string; trajectory_sha256: string; machine: Record<string, any> | null; policy_condition: string; policy_model: string; judge_condition: string};
type Research = {
  release: string; dataset_sha256: string; source_bank_sha256: string; items: Item[]; t4: Trajectory[];
  assignments: Assignment[]; rubric: unknown; sampling: Record<string, unknown>; private: Record<string, string>; evidence_blobs: Record<string, string>};
export const research = unpackStored<Research>(compressed);
const previousResearch = restoreResearchDelta(research, unpackStored(previousDeltaCompressed));
const mediaHistory = unpackStored<MediaSnapshot[]>(mediaHistoryCompressed);
const releases = new Map([previousResearch, research].map(value => [value.dataset_sha256, value]));
// Every published media batch keeps its original assignments and assets.
// Question and private evidence hashes remain frozen across these overlays.
for (const snapshot of [firstMediaSnapshot, ...mediaHistory] as Partial<MediaSnapshot>[]) {
  if (snapshot.dataset_sha256 && snapshot.dataset_sha256 !== research.dataset_sha256) {
    releases.set(snapshot.dataset_sha256, restoreMediaSnapshot(research, snapshot as MediaSnapshot));
  }
}
export const researchVersions = [...releases.keys()];
export function researchFor(hash: string) {
  const value = releases.get(hash);
  if (!value) throw new InputError('找不到这份记录对应的冻结标注版本。');
  return value;
}
if (gate2DatasetHash !== research.dataset_sha256) throw new Error('Gate2 review dataset mismatch; rebuild the bound review bundle');
const extra = JSON.parse(gunzipSync(Buffer.from(calibration.gzip_base64, 'base64')).toString());
if (!releases.has(extra.dataset_sha256)) throw new Error('Claude calibration dataset mismatch');
for (const bundle of releases.values()) for (const row of bundle.t4) {
  const score = extra.records[row.id];
  if (score) {if (score.packet_sha256 !== row.packet_sha256) throw new Error('Claude packet mismatch'); row.machine = score;}
}
// This dispatch covers offline annotation. Frozen releases keep every assignment
// so existing online records can still be recovered and exported.
const activeAssignments = research.assignments.filter(x => ['offline_text', 'offline_video'].includes(x.track));
function videoFormat(bundle?: Research) {
  const media = bundle?.items.flatMap(x => x.media) || [];
  return media.length ? media.every(x => x.spoken_scope === 'checkpoint_sentence') ? 'checkpoint' : 'full' : 'none';
}
export const researchCatalog = () => ({scope: 'offline', release: research.release, videoFormat: videoFormat(research), assignments: activeAssignments,
  videoCount: research.items.filter(x => x.public_video).length, textCount: research.items.length,
  mediaCount: new Set(research.items.flatMap(x => x.media.map(m => m.sha256))).size,
  videoScenes: new Set(research.items.filter(x => x.public_video).map(x => x.scene_id)).size,
  textScenes: new Set(research.items.map(x => x.scene_id)).size,
  language: 'en'});
export function researchReleaseInfo(hash: string, currentTotal: number, assignedCount: number) {
  const counts = new Map<string, number>();
  for (const item of research.items) counts.set(item.scene_id, (counts.get(item.scene_id) || 0) + 1);
  const sizes = new Set(counts.values());
  return {isCurrent: hash === research.dataset_sha256, currentTotal, assignedCount,
    currentVideoFormat: videoFormat(releases.get(hash)), latestVideoFormat: videoFormat(research),
    latestTotal: research.items.length, latestSceneCount: counts.size,
    latestVideoTotal: research.items.filter(x => x.public_video).length,
    latestVideoScenes: new Set(research.items.filter(x => x.public_video).map(x => x.scene_id)).size,
    latestQuestionsPerScene: sizes.size === 1 ? [...sizes][0] : null};
}
export function assignmentFor(id: unknown) {
  const assignment = activeAssignments.find(x => x.id === id);
  if (!assignment) throw new InputError('请选择本轮已开放的 T1–3 离线任务。');
  return assignment;
}
export function researchQuestions(a: Assignment, data = research) {
  return data.items.filter(x => a.item_ids.includes(x.id)).map(x => ({...(a.track === 'offline_video' ? x.public_video! : x.public_text), instance_id: x.id}));
}
export function researchTrajectories(a: Assignment, data = research) {
  return data.t4.filter(x => a.item_ids.includes(x.id));
}
export function sceneAssignment(a: Assignment, workflow: Workflow): Assignment {
  const scene = activeScene(workflow);
  return scene ? {...a, scene_ids: [scene.id], item_ids: scene.itemIds} : a;
}
export function researchMaterial(a: Assignment, workflow: Workflow, data = research) {
  if (a.track === 't4') return {assignment: a, rubric: data.rubric,
    gate2Tasks: gate2Material(a.scene_ids, workflow.gate2, workflow.phase, a.track),
    trajectories: researchTrajectories(a, data).map(x => ({id: x.id, packet: x.packet, packet_sha256: x.packet_sha256,
      ...(workflow.phase === 'complete' ? {machine: x.machine, policy_condition: x.policy_condition, policy_model: x.policy_model} : {})})), items: []};
  a = sceneAssignment(a, workflow);
  const referenceAnswers = workflow.sceneSequence && workflow.phase === 'gt' && workflow.blindLockedAt
    ? a.item_ids.map(id => ({id, answer: JSON.parse(gunzipSync(Buffer.from(data.private[id], 'base64')).toString()).machine?.answer || null})) : [];
  return {assignment: a, referenceAnswers, gate2Tasks: gate2Material(a.scene_ids, workflow.gate2, workflow.phase, a.track), items: data.items.filter(x => a.item_ids.includes(x.id)).map(x => ({id: x.id, scene_id: x.scene_id, task: x.task,
    public: a.track === 'offline_video' ? x.public_video : x.public_text,
    media: a.track === 'offline_video' ? x.media : [], coverage: a.track === 'offline_video' ? x.coverage : null})), trajectories: []};
}
export function researchEvidence(a: Assignment, workflow: Workflow, id: unknown, data = research) {
  if (typeof id !== 'string' || !a.item_ids.includes(id)) throw new InputError('题目不在本组任务中。');
  const scene = activeScene(workflow);
  if (scene && !scene.itemIds.includes(id)) throw new InputError('请先完成当前场景；其他场景的答案尚未开放。');
  if (a.track === 't4' || !['gt', 'complete'].includes(workflow.phase) || !workflow.blindLockedAt) throw new InputError(workflow.sceneSequence ? '先锁定本场景全部盲答和独立环境判断，才能查看答案与私有材料。' : '先完成并锁定本组全部盲答，才能查看私有材料和机器答案。');
  const value = JSON.parse(gunzipSync(Buffer.from(data.private[id], 'base64')).toString());
  for (const [key, field] of Object.entries(value.evidence) as [string, any][]) {
    if (field?.$ref) value.evidence[key] = JSON.parse(gunzipSync(Buffer.from(data.evidence_blobs[field.$ref], 'base64')).toString());
  }
  return value;
}
export function researchHashes(a: Assignment, data = research) {
  return Object.fromEntries(a.track === 't4' ? researchTrajectories(a, data).map(x => [x.id, x.packet_sha256]) : data.items.filter(x => a.item_ids.includes(x.id)).map(x => [x.id, x.item_sha256]));
}
export function researchExport(a: Assignment, w: Workflow, data = research) {
  return {assignment: a, workflow: w, gate2_human_review: gate2Export(a.scene_ids, w.gate2, a.track), source_bank_sha256: data.source_bank_sha256,
    blind_responses: w.blind || {}, machine_assisted_gt: w.gt || {}, independent_t4_ratings: w.ratings || {},
    ...(a.track === 't4' ? {rubric: data.rubric, judge_condition: 'text_only',
      provenance: researchTrajectories(a, data).map(x => ({id: x.id, trajectory_sha256: x.trajectory_sha256, packet_sha256: x.packet_sha256,
        ...(w.phase === 'complete' ? {policy_condition: x.policy_condition, policy_model: x.policy_model} : {})})),
      comparisons: w.phase === 'complete' ? researchTrajectories(a, data).flatMap(x => dimensions.map(d => {
        const human = w.ratings?.[x.id]?.[d].score ?? null, claude = x.machine?.judgment?.dimensions?.[d]?.score ?? null;
        return {scenario_id: x.id, dimension: d, human, claude, delta_human_minus_claude: human !== null && claude !== null ? human - claude : null,
          packet_sha256: x.packet_sha256, machine_status: x.machine ? 'available' : 'pending'};
      })) : []} : {}),
    gt_status: 'individual_proposal_requires_two_distinct_reviewers_or_adjudication', formal_ground_truth: false};
}
