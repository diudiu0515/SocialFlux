import test from 'node:test';
import assert from 'node:assert/strict';
import {transition} from '../lib/research-protocol.ts';
import {activeQuestionId, flowSteps, flowStepsFor} from '../lib/scenario-flow.ts';
import {scopedFlowTasks} from '../lib/question-material.ts';

const scenes = [{id: 's1', itemIds: ['q1', 'q2']}, {id: 's2', itemIds: ['q3', 'q4']}];
const questions = scenes.flatMap(scene => scene.itemIds.map(instance_id => ({instance_id, options: {A: 'a', B: 'b'}})));
function task(scene, id, step, bindings) {
  return {id, scene_id: scene, step, kind: step === 'media' ? 'media-quality' : 'review', title: id, stage: 'review', sha256: 'hash-' + id,
    evidence: {对应题目: bindings}, questions: step === 'media' ? [{id: 'playback', choices: {watched_listened: 'watched', unavailable: 'failed'}},
      {id: 'expression', choices: {yes: 'yes', no: 'no'}}, {id: 'usability', choices: {usable: 'yes', revise: 'no'}}] : [{id: 'ok', choices: {yes: 'yes', no: 'no', uncertain: 'uncertain'}}]};
}
const tasks = scenes.flatMap(scene => [task(scene.id, scene.id + '-scenario', 'scenario'), task(scene.id, scene.id + '-state', 'state'),
  ...scene.itemIds.flatMap(id => [task(scene.id, id + '-dialogue', 'dialogue', [id + ' · 对话 · t1']), task(scene.id, id + '-media', 'media', [id])])]);
const initial = (version = 3) => ({phase: 'blind', baselineEligible: true, exclusions: [], sceneSequence: {version: 1, index: 0, scenes, completed: {}},
  scenarioFlow: {version, questionIndex: 0, questionLocks: {}, step: 'scenario', reviews: {}, machineVerdicts: {}, locks: {}}, gate2: {packet_sha256: 'hash', answers: {}}});
const answer = {answer: 'A', confidence: 'medium', rationale: '', issue: 'none'};
const gt = {answer: 'B', acceptable_answers: ['B'], decision: 'usable', rationale: 'checked'};
const vote = task => ({values: Object.fromEntries(task.questions.map(q => [q.id, Object.keys(q.choices)[0]])), rationale: ''});
const sceneOf = w => scenes[w.sceneSequence.index];
function currentTasks(w) {
  const all = tasks.filter(t => t.scene_id === sceneOf(w).id);
  return w.scenarioFlow.version === 3 && w.scenarioFlow.step === 'answer' ? scopedFlowTasks(all, activeQuestionId(w)) : all.filter(t => t.step === w.scenarioFlow.step);
}
const votes = w => Object.fromEntries(currentTasks(w).map(t => [t.id, vote(t)]));
const act = (w, action, data = {}) => transition(w, action, {sceneId: sceneOf(w)?.id, flowStep: w.scenarioFlow.step, itemId: activeQuestionId(w), ...data}, questions, [], 'now', tasks);
function advance(w) {
  const ids = sceneOf(w).itemIds;
  const answerIds = w.scenarioFlow.version === 3 ? [activeQuestionId(w)] : ids;
  return act(w, w.scenarioFlow.step === 'state' ? 'submit' : 'lock', {flowReviews: votes(w),
    answers: w.scenarioFlow.step === 'answer' ? Object.fromEntries(answerIds.map(id => [id, answer])) : {},
    gt: w.scenarioFlow.step === 'feedback' ? Object.fromEntries(ids.map(id => [id, gt])) : {},
    machineVerdicts: w.scenarioFlow.step === 'feedback' ? Object.fromEntries(ids.map(id => [id, 'unreasonable'])) : {}, attestation: true}).workflow;
}

test('v3 presents four stages and locks each question before exposing the next', () => {
  let w = initial();
  assert.deepEqual(flowStepsFor(w.scenarioFlow), ['scenario', 'answer', 'feedback', 'state']);
  w = advance(w);
  assert.equal(w.scenarioFlow.step, 'answer');
  assert.equal(activeQuestionId(w), 'q1');
  w = advance(w);
  assert.equal(w.scenarioFlow.step, 'answer');
  assert.equal(activeQuestionId(w), 'q2');
  assert.equal(w.phase, 'blind');
  assert.equal(w.blindLockedAt, undefined);
  assert.deepEqual(w.scenarioFlow.questionLocks.s1, {q1: 'now'});
  w = advance(w);
  assert.equal(w.scenarioFlow.step, 'feedback');
  assert.equal(w.phase, 'gt');
  assert.equal(w.blindLockedAt, 'now');
  assert.deepEqual(w.scenarioFlow.questionLocks.s1, {q1: 'now', q2: 'now'});
});

test('future answers, other-question dialogue/media and early private judgments are rejected', () => {
  const w = advance(initial());
  assert.throws(() => act(w, 'draft', {answers: {q2: answer}}));
  assert.throws(() => act(w, 'draft', {answers: {q3: answer}}));
  for (const id of ['q2-dialogue', 'q2-media', 's1-state', 'q3-dialogue']) assert.throws(() => act(w, 'draft', {flowReviews: {[id]: vote(tasks.find(t => t.id === id))}}));
  assert.throws(() => act(w, 'draft', {gt: {q1: gt}}));
  assert.throws(() => act(w, 'draft', {machineVerdicts: {q1: 'reasonable'}}));
  assert.throws(() => act(w, 'lock', {itemId: 'q2', answers: {q2: answer}, flowReviews: votes(w)}));
});

test('question lock requires its answer and every bound dialogue/video review', () => {
  const w = advance(initial());
  assert.throws(() => act(w, 'lock', {answers: {q1: answer}, flowReviews: {}}));
  assert.throws(() => act(w, 'lock', {answers: {}, flowReviews: votes(w)}));
  const reviews = votes(w);
  delete reviews['q1-media'];
  assert.throws(() => act(w, 'lock', {answers: {q1: answer}, flowReviews: reviews}));
  reviews['q1-media'] = {values: {playback: 'unavailable', expression: 'yes', usability: 'usable'}, rationale: ''};
  assert.throws(() => act(w, 'lock', {answers: {q1: answer}, flowReviews: reviews}));
});

test('drafts do not advance and prior locked answers/reviews cannot be changed', () => {
  let w = advance(initial());
  const draft = act(w, 'draft', {answers: {q1: answer}, flowReviews: votes(w)});
  assert.equal(draft.answers.q1.answer, 'A');
  assert.equal(draft.workflow.scenarioFlow.questionIndex, 0);
  assert.deepEqual(draft.workflow.scenarioFlow.questionLocks, {});
  w = advance(w);
  assert.throws(() => act(w, 'draft', {answers: {q1: {...answer, answer: 'B'}}}));
  assert.throws(() => act(w, 'draft', {itemId: 'q1', answers: {q1: answer}}));
  assert.throws(() => act(w, 'draft', {flowReviews: {'q1-dialogue': {values: {ok: 'no'}, rationale: 'changed'}}}));
  assert.doesNotThrow(() => act(w, 'draft', {answers: w.blind, flowReviews: w.scenarioFlow.reviews}));
});

test('new scene resets question cursor and preserves locked original answers and reviews', () => {
  let w = initial();
  for (let i = 0; i < 5; i++) w = advance(w);
  assert.equal(w.sceneSequence.index, 1);
  assert.equal(w.scenarioFlow.step, 'scenario');
  assert.equal(w.scenarioFlow.questionIndex, 0);
  assert.equal(w.phase, 'blind');
  assert.equal(w.blind.q1.answer, 'A');
  assert.equal(w.gt.q1.answer, 'B');
  assert.equal(w.scenarioFlow.machineVerdicts.q1, 'unreasonable');
  assert.throws(() => act(w, 'draft', {answers: {q1: {...answer, answer: 'B'}}}));
  for (let i = 0; i < 5; i++) w = advance(w);
  assert.equal(w.phase, 'complete');
  assert.equal(Object.keys(w.blind).length, 4);
  assert.equal(Object.keys(w.scenarioFlow.questionLocks).length, 2);
});

test('frozen v2 sessions still use all six original stages and group answer lock', () => {
  let w = initial(2);
  assert.deepEqual(flowStepsFor(w.scenarioFlow), flowSteps);
  for (const step of flowSteps) {
    assert.equal(w.scenarioFlow.step, step);
    if (step === 'answer') assert.throws(() => act(w, 'lock', {answers: {q1: answer}}));
    w = advance(w);
  }
  assert.equal(w.sceneSequence.index, 1);
  assert.deepEqual(w.scenarioFlow.questionLocks, {});
  assert.equal(w.blind.q1.answer, 'A');
  assert.equal(w.gt.q1.answer, 'B');
  assert.equal(Object.keys(w.scenarioFlow.locks.s1).length, 6);
});

test('shared evidence is reviewed once and cannot be overwritten after its first question lock',()=>{
  const shared=task('s1','shared-dialogue','dialogue',['q1 · 对话 · t1','q2 · 对话 · t1']);
  tasks.push(shared);
  try {
    let w=advance(initial());w=advance(w);
    assert.equal(activeQuestionId(w),'q2');
    assert.throws(()=>act(w,'draft',{flowReviews:{[shared.id]:{values:{ok:'no'},rationale:'changed prior locked review'}}}));
    const next=advance(w);assert.equal(next.phase,'gt');assert.deepEqual(next.scenarioFlow.reviews[shared.id],w.scenarioFlow.reviews[shared.id]);
  } finally {tasks.pop();}
});
