import {validateReview, type ReviewTask, type Gate2Workflow} from './gate2-protocol.ts';
import {InputError, validateAnswers, type Answers, type Question} from './protocol.ts';

export const dimensions = ['goal_achievement', 'state_adaptation', 'risk_management', 'recovery', 'relationship_outcome'] as const;
export type Dimension = typeof dimensions[number];
export type Rating = {score: number | null; evidence_turn_ids: string[]; rationale: string; insufficient_evidence: boolean};
export type Ratings = Record<string, Record<Dimension, Rating>>;
export type GT = Record<string, {answer: string | null; acceptable_answers: string[]; decision: 'usable' | 'revise' | 'reject'; rationale: string}>;
export type Workflow = {phase: 'blind' | 'gate2' | 'gt' | 't4_review' | 'complete'; gate2?: Gate2Workflow; blind?: Answers; blindLockedAt?: string; gt?: GT; ratings?: Ratings; ratingsLockedAt?: string; attestedAt?: string; baselineEligible: boolean; exclusions: string[]};

export function validateGT(value: unknown, questions: Question[], complete: boolean): GT {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new InputError('GT 格式无效。');
  const source = value as GT, clean: GT = {};
  if (Object.keys(source).some(id => !questions.some(q => q.instance_id === id))) throw new InputError('GT 包含其他任务的题目。');
  for (const q of questions) {
    const row = source[q.instance_id];
    if (!row) {if (complete) throw new InputError('请完成本组全部 GT 判断。'); continue;}
    if (!row || typeof row !== 'object' || !['usable', 'revise', 'reject'].includes(row.decision)) throw new InputError('请选择有效的题目质量判断。');
    const answer = row.answer;
    if (answer !== null && !Object.hasOwn(q.options, answer)) throw new InputError('GT 答案无效。');
    if (!Array.isArray(row.acceptable_answers) || new Set(row.acceptable_answers).size !== row.acceptable_answers.length || row.acceptable_answers.some(a => !Object.hasOwn(q.options, a))) throw new InputError('可接受选项无效。');
    if (answer && !row.acceptable_answers.includes(answer)) throw new InputError('可接受选项须包含主答案。');
    if (typeof row.rationale !== 'string' || row.rationale.length > 4000) throw new InputError('GT 依据请控制在 4000 字以内。');
    if (complete && (!row.rationale.trim() || (row.decision !== 'reject' && !answer) || (row.decision === 'usable' && row.acceptable_answers.length !== 1))) throw new InputError('可用题须有唯一答案；所有 GT 判断都须填写依据。多个合理选项请标记需修改。');
    clean[q.instance_id] = {answer, acceptable_answers: row.acceptable_answers, decision: row.decision, rationale: row.rationale};
  }
  return clean;
}

export function validateRatings(value: unknown, items: {id: string; turn_ids: string[]}[], complete: boolean): Ratings {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new InputError('评分格式无效。');
  const source = value as Ratings, clean: Ratings = {};
  if (Object.keys(source).some(id => !items.some(x => x.id === id))) throw new InputError('包含未分配的轨迹。');
  for (const item of items) {
    const scores = source[item.id];
    if (!scores) {if (complete) throw new InputError('请完成本组全部轨迹。'); continue;}
    if (typeof scores !== 'object' || Array.isArray(scores) || Object.keys(scores).some(k => !dimensions.includes(k as Dimension))) throw new InputError('评分维度无效。');
    const result: Partial<Record<Dimension, Rating>> = {};
    for (const name of dimensions) {
      const row = scores[name];
      if (!row) {if (complete) throw new InputError('请填写全部五个维度。'); continue;}
      if (row.score !== null && (!Number.isInteger(row.score) || row.score < 0 || row.score > 10)) throw new InputError('评分须为 0–10 的整数。');
      if (typeof row.insufficient_evidence !== 'boolean' || typeof row.rationale !== 'string' || row.rationale.length > 4000) throw new InputError('评分依据无效。');
      if (!Array.isArray(row.evidence_turn_ids) || row.evidence_turn_ids.length > 3 || new Set(row.evidence_turn_ids).size !== row.evidence_turn_ids.length || row.evidence_turn_ids.some(id => !item.turn_ids.includes(id))) throw new InputError('请引用本条轨迹中的 1–3 个轮次编号。');
      if (complete && (!row.rationale.trim() || !row.evidence_turn_ids.length || (row.score === null && (name !== 'recovery' || !row.insufficient_evidence)))) throw new InputError('每维须有分数、依据及 1–3 个轮次；仅恢复维度可在无修复机会时选择不适用。');
      result[name] = {score: row.score, evidence_turn_ids: row.evidence_turn_ids, rationale: row.rationale, insufficient_evidence: row.insufficient_evidence};
    }
    clean[item.id] = result as Record<Dimension, Rating>;
  }
  return clean;
}

export function transition(workflow: Workflow, action: string, data: Record<string, unknown>, questions: Question[], trajectories: {id: string; turn_ids: string[]}[], now: string, reviewTasks: ReviewTask[] = []) {
  if (workflow.phase === 'complete') throw new InputError('已提交并锁定。');
  const next = structuredClone(workflow);
  const t4 = trajectories.length > 0;
  if (!['draft', 'lock', 'gate2-lock', 'submit'].includes(action) || (action === 'gate2-lock' && workflow.phase !== 'gate2')) throw new InputError('当前阶段不支持此操作。');
  if (t4) {
    if (action === 'lock') throw new InputError('轨迹评分请使用最终提交。');
    if (workflow.phase === 't4_review') {
      if (!next.gate2 || !next.ratingsLockedAt || !next.ratings) throw new InputError('请先锁定独立五维评分。');
      // Submitted score edits are ignored: the stored independent ratings are immutable.
      next.gate2.answers = validateReview(data.gate2Answers, reviewTasks, action === 'submit');
      if (action === 'submit') {
        if (data.attestation !== true) throw new InputError('请确认已亲自核对触发记录和已提供的视频材料。');
        next.phase = 'complete'; next.attestedAt = now;
      }
    } else {
      if (workflow.phase !== 'blind') throw new InputError('当前阶段不能修改轨迹评分。');
      next.ratings = validateRatings(data.ratings, trajectories, action === 'submit');
      if (action === 'submit') {
        if (data.attestation !== true) throw new InputError('请确认是本人独立评分。');
        if (next.gate2) {
          if (!reviewTasks.length) throw new InputError('本组触发核对材料缺失，请联系研究者。');
          next.ratingsLockedAt = now; next.phase = 't4_review';
        } else {next.phase = 'complete'; next.attestedAt = now;}
      }
    }
  } else if (workflow.phase === 'blind') {
    if (action === 'submit') throw new InputError('请先锁定本组盲答，再完成 GT。');
    const answers = validateAnswers(data.answers, questions, action === 'lock');
    if (action === 'lock') {next.blind = answers; next.blindLockedAt = now; next.phase = next.gate2 && reviewTasks.some(t => t.stage === 'independent') ? 'gate2' : 'gt'; if (next.gate2 && next.phase === 'gt') next.gate2.independentLockedAt = now;}
    return {workflow: next, answers};
  } else if (workflow.phase === 'gate2') {
    if (!next.gate2 || !['draft', 'gate2-lock'].includes(action)) throw new InputError('请先锁定独立环境判断。');
    next.gate2.answers = validateReview(data.gate2Answers, reviewTasks.filter(t => t.stage === 'independent'), action === 'gate2-lock');
    if (action === 'gate2-lock') {next.gate2.independentLockedAt = now; next.phase = 'gt';}
  } else {
    if (next.gate2) {
      if (!next.gate2.independentLockedAt) throw new InputError('独立环境判断尚未锁定。');
      const independentIds = reviewTasks.filter(t => t.stage === 'independent').map(t => t.id);
      const incoming = data.gate2Answers as Record<string, unknown> | undefined;
      if (!incoming || Object.keys(incoming).some(id => !reviewTasks.some(t => t.id === id))) throw new InputError('环境核对包含未分配任务。');
      const independent = Object.fromEntries(Object.entries(next.gate2.answers).filter(([id]) => independentIds.includes(id)));
      const reviews = Object.fromEntries(Object.entries(incoming).filter(([id]) => !independentIds.includes(id)));
      next.gate2.answers = {...independent, ...validateReview(reviews, reviewTasks.filter(t => t.stage === 'review'), action === 'submit')};
    }
    if (action === 'lock' || action === 'gate2-lock') throw new InputError('盲答已经锁定。');
    next.gt = validateGT(data.gt, questions, action === 'submit');
    if (action === 'submit') {if (data.attestation !== true) throw new InputError('请确认已核对私有材料并亲自完成 GT 判断。'); next.phase = 'complete'; next.attestedAt = now;}
  }
  return {workflow: next, answers: workflow.blind || {}};
}
