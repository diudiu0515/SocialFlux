import {scenarioFlowTasks} from './scenario-material';
import {gate2Hash, gate2Tasks} from './gate2';
import { and, eq, inArray } from "drizzle-orm";
import { getDb } from "../db";
import { demoSessions } from "../db/schema";
import legacy from "../data/questions.json";
import multimedia from "../data/multimodal.json";
import { type Answers, type MediaReviews, type Question, type ReviewAsset, InputError, validateAnswers, validateMediaReviews, validateRevision, validateStart } from "./protocol";
import {research, researchFor, researchVersions, researchCatalog, researchReleaseInfo, assignmentFor, sceneAssignment, researchQuestions, researchTrajectories, researchMaterial, researchEvidence, researchHashes, researchExport, type Assignment} from './research';
import {transition, type Workflow} from './research-protocol';
import {mediaRetired} from './retired-media';
export {researchCatalog};

type Bundle = {dataset_sha256: string; release: string; items: {public: Question; item_sha256: string}[]; videos?: ReviewAsset[]; scenes?: unknown[]};
const currentBundle = multimedia as unknown as Bundle, legacyBundle = legacy as unknown as Bundle;
function bundleFor(hash: string): Bundle {
  if (hash === legacyBundle.dataset_sha256) return legacyBundle;
  if (hash === currentBundle.dataset_sha256) return currentBundle;
  throw new InputError("找不到这份记录对应的材料版本，请联系研究者。");
}
// A recovery code retains its original release, including the original six-question demo.
export async function current(userId: string) {
  return getDb().select().from(demoSessions).where(and(eq(demoSessions.userId, userId),
    inArray(demoSessions.datasetSha256, [legacyBundle.dataset_sha256, currentBundle.dataset_sha256, ...researchVersions]))).get();
}
type Session = NonNullable<Awaited<ReturnType<typeof current>>>;
export function present(row: Session | undefined) {
  return row ? {id: row.id, alias: row.alias, priorExposure: row.priorExposure,
    answers: JSON.parse(row.draftJson) as Answers, mediaReviews: JSON.parse(row.mediaReviewsJson) as MediaReviews,
    revision: row.revision, status: row.status, createdAt: row.createdAt, updatedAt: row.updatedAt, submittedAt: row.submittedAt,
    ...(researchVersions.includes(row.datasetSha256) ? {workflow: JSON.parse(row.workflowJson)} : {})} : null;
}
export function payload(row: Session | undefined) {
  if (row && researchVersions.includes(row.datasetSha256)) {
    const frozen = researchFor(row.datasetSha256);
    const assignment = JSON.parse(row.assignmentJson) as Assignment, workflow = JSON.parse(row.workflowJson) as Workflow;
    return {session: present(row), research: researchMaterial(assignment, workflow, frozen), questions: researchQuestions(sceneAssignment(assignment, workflow), frozen),
      ...(assignment.track !== 't4' ? {releaseInfo: researchReleaseInfo(frozen.dataset_sha256, frozen.items.length, assignment.item_ids.length)} : {}),
      dataset: {sha256: frozen.dataset_sha256, release: frozen.release, count: assignment.item_ids.length, kind: 'research'}};
  }
  const bundle = bundleFor(row?.datasetSha256 || currentBundle.dataset_sha256);
  return {session: present(row), questions: bundle.items.map(item => item.public), videos: bundle.videos || [], scenes: bundle.scenes || [],
    releaseInfo: {...researchReleaseInfo(bundle.dataset_sha256, bundle.items.length, bundle.items.length),
      currentMediaRetired: bundle.videos?.some(video => typeof video.url === 'string' && mediaRetired(video.url)) || false},
    dataset: {sha256: bundle.dataset_sha256, release: bundle.release, count: bundle.items.length,
      kind: bundle.videos ? "multimodal_review" : "text", videoCount: bundle.videos?.length || 0}};
}
export async function start(userId: string, data: Record<string, unknown>) {
  const clean = validateStart(data), time = new Date().toISOString(), existing = await current(userId);
  if (existing) return payload(existing);
  const assignment = assignmentFor(data.assignmentId);
  const previous = await getDb().select().from(demoSessions).where(eq(demoSessions.alias, clean.alias)).all();
  const exclusions = clean.priorExposure ? ['self_reported_prior_exposure'] : [];
  if (previous.some(row => {
    const old = JSON.parse(row.assignmentJson) as Partial<Assignment>;
    return old.scene_ids?.some(id => assignment.scene_ids.includes(id)) || row.datasetSha256 !== research.dataset_sha256;
  })) exclusions.push('prior_or_repeated_scene_exposure');
  await getDb().insert(demoSessions).values({id: crypto.randomUUID(), userId,
    datasetSha256: research.dataset_sha256, release: research.release, ...clean, createdAt: time, updatedAt: time,
    assignmentJson: JSON.stringify(assignment), workflowJson: JSON.stringify({phase: 'blind', baselineEligible: !exclusions.length, exclusions, ...(assignment.track === 't4' ? {gate2: {packet_sha256: gate2Hash, answers: {}}} : {}),
      ...(assignment.track !== 't4' ? {scenarioFlow: {version: 2, sourcePacketSha256: gate2Hash, step: 'scenario', reviews: {}, machineVerdicts: {}, locks: {}}, sceneSequence: {version: 1, index: 0, completed: {}, scenes: assignment.scene_ids.map(id => ({id, itemIds: research.items.filter(x => x.scene_id === id && assignment.item_ids.includes(x.id)).map(x => x.id)}))}} : {})}),
    itemHashesJson: JSON.stringify(researchHashes(assignment)),
    mediaHashesJson: JSON.stringify(Object.fromEntries(research.items.filter(x => assignment.item_ids.includes(x.id)).map(x => [x.id, assignment.track === 'offline_video' ? x.media : []]))),
  }).onConflictDoNothing().run();
  return payload(await current(userId));
}
export class ConflictError extends Error {}
export async function save(userId: string, data: Record<string, unknown>, complete = false, action = complete ? 'submit' : 'draft') {
  const previous = await current(userId);
  if (!previous) throw new InputError("请先开始本次标注。");
  if (previous.status === "submitted") {
    if (complete) return payload(previous);
    throw new ConflictError("这份标注已提交并锁定，不能再修改。");
  }
  if (researchVersions.includes(previous.datasetSha256)) {
    const frozen = researchFor(previous.datasetSha256);
    const assignment = JSON.parse(previous.assignmentJson) as Assignment, workflow = JSON.parse(previous.workflowJson) as Workflow;
    if (!workflow.sceneSequence && action === 'lock' && workflow.phase === 'gt' && JSON.stringify(data.answers) === JSON.stringify(workflow.blind)) return payload(previous);
    if (action === 'submit' && workflow.phase === 't4_review' && data.revision === previous.revision - 1
        && JSON.stringify(data.ratings) === JSON.stringify(workflow.ratings)
        && (!data.gate2Answers || Object.keys(data.gate2Answers as object).length === 0)) return payload(previous);
    const revision = validateRevision(data.revision), time = new Date().toISOString();
    const next = transition(workflow, action, data, researchQuestions(assignment, frozen), researchTrajectories(assignment, frozen).map(x => ({id: x.id, turn_ids: x.packet.observable_trajectory.map((t: {turn_id: string}) => t.turn_id)})), time, workflow.scenarioFlow ? scenarioFlowTasks(sceneAssignment(assignment, workflow), workflow, frozen) : gate2Tasks(assignment.scene_ids, workflow.gate2, assignment.track));
    const serialized = JSON.stringify(next.workflow), answers = JSON.stringify(next.answers);
    const result = await getDb().update(demoSessions).set({workflowJson: serialized, draftJson: answers, revision: revision + 1, updatedAt: time,
      ...(next.workflow.phase === 'complete' ? {status: 'submitted', submittedAt: time} : {})})
      .where(and(eq(demoSessions.id, previous.id), eq(demoSessions.revision, revision), eq(demoSessions.status, 'in_progress'))).returning().get();
    if (result) return payload(result);
    throw new ConflictError('另一页面更新了这份标注。当前草稿已留在本设备，请刷新后核对。');
  }
  if (action === 'lock') throw new InputError('旧版任务保持原提交流程。');
  const bundle = bundleFor(previous.datasetSha256), questions = bundle.items.map(row => row.public), revision = validateRevision(data.revision);
  const answers = validateAnswers(data.answers, questions, complete && !bundle.videos);
  const mediaReviews = bundle.videos ? validateMediaReviews(data.mediaReviews, bundle.videos, complete) : {};
  if (complete && Object.values(answers).some(answer => answer.answer && !answer.confidence)) throw new InputError("已作答的题目还需填写把握程度。");
  if (complete && data.attestation !== true) throw new InputError("请确认这些判断由你独立完成。");
  const serialized = JSON.stringify(answers), serializedMedia = JSON.stringify(mediaReviews), time = new Date().toISOString();
  if (new TextEncoder().encode(serialized + serializedMedia).length > 800000) throw new InputError("备注总量过长，请适当缩短后保存。");
  const result = await getDb().update(demoSessions).set({draftJson: serialized, mediaReviewsJson: serializedMedia,
    revision: revision + 1, updatedAt: time, ...(complete ? {status: "submitted", submittedAt: time} : {}),
  }).where(and(eq(demoSessions.id, previous.id), eq(demoSessions.userId, userId),
    eq(demoSessions.revision, revision), eq(demoSessions.status, "in_progress"))).returning().get();
  if (result) return payload(result);
  const latest = await current(userId);
  if (latest && latest.draftJson === serialized && latest.mediaReviewsJson === serializedMedia && (!complete || latest.status === "submitted")) return payload(latest);
  throw new ConflictError("另一页面更新了这份标注。请刷新以读取最新进度，当前页面的输入仍保留在此设备。");
}
export function exportRecord(row: Session) {
  if (researchVersions.includes(row.datasetSha256)) {
    const workflow = JSON.parse(row.workflowJson) as Workflow;
    const assignment = JSON.parse(row.assignmentJson) as Assignment;
    const mediaHashes = JSON.parse(row.mediaHashesJson) as Record<string, unknown>;
    const visibleAssignment = workflow.sceneSequence && workflow.phase !== 'complete' ? {...assignment, scene_ids: workflow.sceneSequence.scenes.slice(0, workflow.sceneSequence.index + 1).map(s => s.id)} : assignment;
    const exported = researchExport(visibleAssignment, workflow, researchFor(row.datasetSha256));
    exported.assignment = assignment;
    // Media rows contain full dialogue and playable URLs. In-progress downloads
    // may include completed/current scenes, but must not reveal future scenes.
    if (workflow.sceneSequence && workflow.phase !== 'complete') {
      const visibleScenes = workflow.sceneSequence.scenes.slice(0, workflow.sceneSequence.index + 1);
      const visibleIds = new Set(visibleScenes.flatMap(scene => scene.itemIds));
      for (const id of Object.keys(mediaHashes)) if (!visibleIds.has(id)) delete mediaHashes[id];
      // Media review IDs themselves contain the video SHA, which otherwise
      // allows a future /media/<SHA>.mp4 URL to be reconstructed.
      if (exported.gate2_human_review) {
        const visibleTasks = new Set(gate2Tasks(visibleScenes.map(scene => scene.id), workflow.gate2, assignment.track).map(task => task.id));
        exported.gate2_human_review.task_hashes = Object.fromEntries(Object.entries(exported.gate2_human_review.task_hashes).filter(([id]) => visibleTasks.has(id)));
      }
    }
    return {format: 'socialflux_human_gt_v1', release: row.release,
    receipt_id: row.id, reviewer_alias: row.alias, dataset_sha256: row.datasetSha256, item_hashes: JSON.parse(row.itemHashesJson),
    media_hashes: mediaHashes, status: row.status, revision: row.revision, created_at: row.createdAt, submitted_at: row.submittedAt,
    prior_exposure: row.priorExposure, ...exported};
  }
  const multimodal = !!bundleFor(row.datasetSha256).videos;
  return {format: multimodal ? "socialflux_multimodal_review_v1" : "socialflux_public_demo_annotation_v1",
    release: row.release, receipt_id: row.id, reviewer_alias: row.alias, dataset_sha256: row.datasetSha256,
    item_hashes: JSON.parse(row.itemHashesJson), answers: JSON.parse(row.draftJson),
    ...(multimodal ? {media_hashes: JSON.parse(row.mediaHashesJson), media_reviews: JSON.parse(row.mediaReviewsJson),
      watched_basis: "participant_report_or_browser_playback_end", usage: "media_usability_review_not_a_randomized_modality_trial"} : {}),
    prior_exposure: row.priorExposure, modality: multimodal ? "text+video_review" : "text",
    revision: row.revision, status: row.status, created_at: row.createdAt, submitted_at: row.submittedAt,
    formal_ground_truth: false, purpose: "invited_public_material_demo"};
}
export function evidence(row: Session, id: unknown) {
  if (!researchVersions.includes(row.datasetSha256)) throw new InputError('旧版记录不开放新的材料。');
  return researchEvidence(JSON.parse(row.assignmentJson), JSON.parse(row.workflowJson), id, researchFor(row.datasetSha256));
}
