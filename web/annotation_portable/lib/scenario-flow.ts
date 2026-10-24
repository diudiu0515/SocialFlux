import {scopedFlowTasks} from './question-material.ts';
import {InputError, validateAnswers, type Answers, type Question} from './protocol.ts';
import {validateReview, reviewIssue, type ReviewAnswers, type ReviewTask} from './gate2-protocol.ts';
import {activeScene, validateGT, type Workflow} from './research-protocol.ts';

export const flowSteps = ['scenario', 'dialogue', 'media', 'answer', 'feedback', 'state'] as const;
export type FlowStep = typeof flowSteps[number];
export type FlowTask = ReviewTask & {step: FlowStep};
export type ScenarioFlow = {version: 2 | 3; questionIndex?: number; questionLocks?: Record<string, Record<string, string>>; sourcePacketSha256?: string; step: FlowStep; reviews: ReviewAnswers; machineVerdicts: Record<string, string>; locks: Record<string, Partial<Record<FlowStep, string>>>};
export const flowLabels: Record<FlowStep, string> = {scenario: '背景与角色', dialogue: '逐轮对话', media: '视频审核', answer: '8 题作答', feedback: '答案对照与修订', state: '逐轮 state'};
export const flowStepsFor = (flow: ScenarioFlow): readonly FlowStep[] => flow.version === 3 ? ['scenario', 'answer', 'feedback', 'state'] : flowSteps;
export const activeQuestionId = (workflow: Workflow) => activeScene(workflow)?.itemIds[workflow.scenarioFlow?.questionIndex || 0];
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
  const perQuestion = flow.version === 3 && step === 'answer';
  const questionId = activeQuestionId(workflow);
  if (perQuestion && data.itemId !== questionId) throw new InputError('当前题目已变化，请刷新恢复进度。');
  const permitted = perQuestion ? [questionId!] : scene.itemIds;
  const stepTasks = perQuestion ? scopedFlowTasks(tasks.filter(t => t.scene_id === scene.id && ['dialogue','media'].includes(t.step)), questionId!) : tasks.filter(t => t.scene_id === scene.id && t.step === step);
  const next = structuredClone(workflow), progress = next.scenarioFlow!;
  const incomingAnswers = scoped(data.answers || {}, step === 'answer' ? permitted : [], workflow.blind || {}, '答案');
  const incomingGT = scoped(data.gt || {}, step === 'feedback' ? scene.itemIds : [], workflow.gt || {}, '最终答案');
  const lockedReviewIds = new Set(perQuestion ? Object.keys(flow.questionLocks?.[scene.id] || {}).flatMap(id => scopedFlowTasks(tasks, id).map(t => t.id)) : []);
  const incomingReviews = scoped(data.flowReviews || {}, stepTasks.filter(t => !lockedReviewIds.has(t.id)).map(t => t.id), flow.reviews, '审核');
  const machine = scoped(data.machineVerdicts || {}, step === 'feedback' ? scene.itemIds : [], flow.machineVerdicts, '机器答案判断');
  // No newly forged legacy review records can bypass the staged workflow.
  scoped(data.gate2Answers || {}, [], workflow.gate2?.answers || {}, '环境核对');
  let answers: Answers = {...workflow.blind};
  if (step === 'answer') {
    const clean = validateAnswers(incomingAnswers, currentQuestions.filter(q => permitted.includes(q.instance_id)), complete);
    answers = {...workflow.blind, ...clean};
    if (perQuestion) {
      progress.reviews = {...flow.reviews, ...validateFlowReviews(Object.fromEntries(stepTasks.filter(t => incomingReviews[t.id] || flow.reviews[t.id]).map(t => [t.id, incomingReviews[t.id] || flow.reviews[t.id]])), stepTasks, complete)};
      if (complete) {
        next.blind = answers;
        progress.questionLocks = {...flow.questionLocks, [scene.id]: {...flow.questionLocks?.[scene.id], [questionId!]: now}};
        progress.questionIndex = (flow.questionIndex || 0) + 1;
        if (progress.questionIndex < scene.itemIds.length) return {workflow: next, answers};
      }
    }
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
      if (flowStepsFor(flow).slice(0, -1).some(s => !progress.locks[scene.id][s])) throw new InputError('本场景还有未完成步骤。');
      next.sceneSequence!.completed[scene.id] = {blindLockedAt: next.blindLockedAt!, submittedAt: now};
      next.sceneSequence!.index += 1;
      if (activeScene(next)) {progress.step = 'scenario'; progress.questionIndex = 0; next.phase = 'blind'; delete next.blindLockedAt;}
      else {next.phase = 'complete'; next.attestedAt = now;}
    } else progress.step = flowStepsFor(flow)[flowStepsFor(flow).indexOf(step) + 1];
  }
  return {workflow: next, answers};
}
