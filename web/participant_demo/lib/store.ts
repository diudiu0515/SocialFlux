import { and, eq } from "drizzle-orm";
import { getDb } from "../db";
import { demoSessions } from "../db/schema";
import bundle from "../data/questions.json";
import { type Answers, InputError, validateAnswers, validateRevision, validateStart } from "./protocol";

export const questions = bundle.items.map(row => row.public);
// userId stores SHA-256 of a random anonymous recovery code, not a platform identity.
const key = (userId: string) => and(eq(demoSessions.userId, userId), eq(demoSessions.datasetSha256, bundle.dataset_sha256));
export async function current(userId: string) { return getDb().select().from(demoSessions).where(key(userId)).get(); }
type Session = NonNullable<Awaited<ReturnType<typeof current>>>;
export function present(row: Session | undefined) {
  return row ? {id: row.id, alias: row.alias, priorExposure: row.priorExposure, answers: JSON.parse(row.draftJson) as Answers,
    revision: row.revision, status: row.status, createdAt: row.createdAt, updatedAt: row.updatedAt, submittedAt: row.submittedAt} : null;
}
export function payload(row: Session | undefined) {
  return {session: present(row), questions, dataset: {sha256: bundle.dataset_sha256, release: bundle.release, count: questions.length}};
}
export async function start(userId: string, data: Record<string, unknown>) {
  const clean = validateStart(data), time = new Date().toISOString();
  await getDb().insert(demoSessions).values({id: crypto.randomUUID(), userId, datasetSha256: bundle.dataset_sha256,
    release: bundle.release, ...clean, createdAt: time, updatedAt: time,
    itemHashesJson: JSON.stringify(Object.fromEntries(bundle.items.map(row => [row.public.instance_id, row.item_sha256]))),
  }).onConflictDoNothing().run();
  return payload(await current(userId));
}
export class ConflictError extends Error {}
export async function save(userId: string, data: Record<string, unknown>, complete = false) {
  const previous = await current(userId);
  if (!previous) throw new InputError("请先开始本次标注。");
  if (previous.status === "submitted") {
    if (complete) return payload(previous);
    throw new ConflictError("这份标注已提交并锁定，不能再修改。");
  }
  const revision = validateRevision(data.revision);
  const answers = validateAnswers(data.answers, questions, complete);
  if (complete && data.attestation !== true) throw new InputError("请确认这些判断由你独立完成。");
  const serialized = JSON.stringify(answers), time = new Date().toISOString();
  const result = await getDb().update(demoSessions).set({draftJson: serialized, revision: revision + 1, updatedAt: time,
    ...(complete ? {status: "submitted", submittedAt: time} : {}),
  }).where(and(key(userId), eq(demoSessions.revision, revision), eq(demoSessions.status, "in_progress"))).returning().get();
  if (result) return payload(result);
  const latest = await current(userId);
  // A lost HTTP response can be retried without creating a second submission.
  if (latest && latest.draftJson === serialized && (!complete || latest.status === "submitted")) return payload(latest);
  throw new ConflictError("另一页面更新了这份标注。请刷新以读取最新进度，当前页面的输入仍保留在此设备。");
}
export function exportRecord(row: Session) {
  return {format: "socialflux_public_demo_annotation_v1", release: row.release, receipt_id: row.id,
    reviewer_alias: row.alias, dataset_sha256: row.datasetSha256, item_hashes: JSON.parse(row.itemHashesJson),
    answers: JSON.parse(row.draftJson), prior_exposure: row.priorExposure, modality: "text",
    status: row.status, created_at: row.createdAt, submitted_at: row.submittedAt,
    formal_ground_truth: false, purpose: "invited_public_material_demo"};
}
