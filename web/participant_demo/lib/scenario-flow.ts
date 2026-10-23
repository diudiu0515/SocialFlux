import {InputError, validateAnswers, type Answers, type Question} from './protocol.ts';
import {validateReview, reviewIssue, type ReviewAnswers, type ReviewTask} from './gate2-protocol.ts';
import {activeScene, validateGT, type Workflow} from './research-protocol.ts';

export const flowSteps = ['scenario', 'dialogue', 'media', 'answer', 'feedback', 'state'] as const;
export type FlowStep = typeof flowSteps[number];
export type FlowTask = ReviewTask & {step: FlowStep};
export type ScenarioFlow = {version: 2; sourcePacketSha256?: string; step: FlowStep; reviews: ReviewAnswers; machineVerdicts: Record<string, string>; locks: Record<string, Partial<Record<FlowStep, string>>>};
export const flowLabels: Record<FlowStep, string> = {scenario: '背景与角色', dialogue: '逐轮对话', media: '视频审核', answer: '8 题作答', feedback: '答案对照与修订', state: '逐轮 state'};
const canonical = (v: unknown) => JSON.stringify(v, (_k, x) => x && typeof x === 'object' && !Array.isArray(x) ? Object.fromEntries(Object.entries(x).sort(([a], [b]) => a.localeCompare(b))) : x);
function scoped(value: unknown, allowed: string[], saved: Record<string, unknown>, label: string) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new InputError(label + '格式无效。');
  const result: Record<string, any> = {};
  for (const [id, row] of Object.entries(value)) {
    if (allowed.includes(id)) result[id] = row;
    else if (!Object.hasOwn(saved, id) || canonical(saved[id]) !== canonical(row)) throw new InputError('当前步骤尚未开放该项，或该项已锁定，不能修改。');
  }
  return result;
}
export function flowTaskComplete(task: FlowTask, reviews: ReviewAnswers) {
  const row = reviews[task.id];
  return !!row && task.questions.every(q => Object.hasOwn(q.choices, row.values[q.id] || '')) && !reviewIssue(task, row) &&
    (!Object.values(row.values).some(v => ['no', 'uncertain', 'revise', 'unusable', 'unavailable', 'partial'].includes(v)) || !!row.rationale.trim());
}
function validateFlowReviews(value: unknown, tasks: FlowTask[], complete: boolean) {
  const clean = validateReview(value, tasks, false);
  if (complete) for (const task of tasks) if (!flowTaskComplete(task, clean)) throw new InputError('请完成逐项判断；有问题或无法判断时请说明：' + task.title);
  return clean;
}
export function transitionScenarioFlow(workflow: Workflow, action: string, data: Record<string, unknown>, questions: Question[], now: string, tasks: FlowTask[]): {workflow: Workflow; answers: Answers} {
  const scene = activeScene(workflow), flow = workflow.scenarioFlow;
  if (!scene || !flow || data.sceneId !== scene.id || data.flowStep !== flow.step) throw new InputError('场景或步骤已变化，请刷新恢复当前进度。');
  if (!['draft', 'lock', 'submit'].includes(action) || (action === 'submit' && flow.step !== 'state') || (action === 'lock' && flow.step === 'state')) throw new InputError('请按顺序完成当前步骤。');
  const step = flow.step, complete = action !== 'draft', currentQuestions = questions.filter(q => scene.itemIds.includes(q.instance_id));
  const stepTasks = tasks.filter(t => t.scene_id === scene.id && t.step === step);
  const next = structuredClone(workflow), progress = next.scenarioFlow!;
  const incomingAnswers = scoped(data.answers || {}, step === 'answer' ? scene.itemIds : [], workflow.blind || {}, '答案');
  const incomingGT = scoped(data.gt || {}, step === 'feedback' ? scene.itemIds : [], workflow.gt || {}, '最终答案');
  const incomingReviews = scoped(data.flowReviews || {}, stepTasks.map(t => t.id), flow.reviews, '审核');
  const machine = scoped(data.machineVerdicts || {}, step === 'feedback' ? scene.itemIds : [], flow.machineVerdicts, '机器答案判断');
  // No newly forged legacy review records can bypass the staged workflow.
  scoped(data.gate2Answers || {}, [], workflow.gate2?.answers || {}, '环境核对');
  let answers: Answers = {...workflow.blind};
  if (step === 'answer') {
    const clean = validateAnswers(incomingAnswers, currentQuestions, complete);
    answers = {...workflow.blind, ...clean};
    if (complete) {next.blind = answers; next.blindLockedAt = now; next.phase = 'gt';}
  } else if (step === 'feedback') {
    const clean = validateGT(incomingGT, currentQuestions, complete);
    for (const [id, verdict] of Object.entries(machine)) if (!['', 'reasonable', 'unreasonable', 'uncertain'].includes(verdict)) throw new InputError('机器答案合理性判断无效。');
    if (complete && scene.itemIds.some(id => !machine[id])) throw new InputError('请逐题判断机器答案是否合理。');
    next.gt = {...workflow.gt, ...clean}; progress.machineVerdicts = {...flow.machineVerdicts, ...machine};
  } else {
    if (complete && step !== 'media' && !stepTasks.length) throw new InputError('当前步骤材料缺失，请联系研究者。');
    progress.reviews = {...flow.reviews, ...validateFlowReviews(incomingReviews, stepTasks, complete)};
  }
  if (complete) {
    progress.locks[scene.id] = {...progress.locks[scene.id], [step]: now};
    if (step === 'state') {
      if (data.attestation !== true) throw new InputError('请确认已逐轮核对所有已提供的 state，并如实记录材料缺失。');
      if (flowSteps.slice(0, -1).some(s => !progress.locks[scene.id][s])) throw new InputError('本场景还有未完成步骤。');
      next.sceneSequence!.completed[scene.id] = {blindLockedAt: next.blindLockedAt!, submittedAt: now};
      next.sceneSequence!.index += 1;
      if (activeScene(next)) {progress.step = 'scenario'; next.phase = 'blind'; delete next.blindLockedAt;}
      else {next.phase = 'complete'; next.attestedAt = now;}
    } else progress.step = flowSteps[flowSteps.indexOf(step) + 1];
  }
  return {workflow: next, answers};
}
