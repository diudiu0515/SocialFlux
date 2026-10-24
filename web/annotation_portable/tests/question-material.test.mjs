import test from 'node:test';
import assert from 'node:assert/strict';
import {scopedFlowTasks, questionEvidence} from '../lib/question-material.ts';

const task = (id, step, bindings) => ({id, step, sha256: 'frozen-' + id, evidence: {对应题目: bindings, text: id}});
const tasks = [task('shared-turn', 'dialogue', ['q1 · 对话 · t1', 'q2 · 对话 · t1']),
  task('future-turn', 'dialogue', ['q2 · 对话 · t3']), task('ab-history', 'dialogue', ['q3 · 情境 B · B:t1']),
  task('current-video', 'media', ['q1']), task('future-video', 'media', ['q2']),
  task('similar-prefix', 'dialogue', ['q10 · 对话 · t1']), task('private-state', 'state', ['q1']),
  task('unbound', 'dialogue', undefined)];

test('only exact current-question dialogue and media are visible', () => {
  assert.deepEqual(scopedFlowTasks(tasks, 'q1').map(t => t.id), ['shared-turn', 'current-video']);
  assert.deepEqual(scopedFlowTasks(tasks, ''), []);
  assert.deepEqual(scopedFlowTasks(tasks, 'unknown'), []);
});
test('shared evidence preserves frozen identity and digest; display omits other-question bindings', () => {
  const before = JSON.stringify(tasks);
  assert.equal(scopedFlowTasks(tasks, 'q1')[0], tasks[0]);
  assert.deepEqual(questionEvidence(tasks[0], 'q1').对应题目, ['q1 · 对话 · t1']);
  assert.equal(questionEvidence(tasks[1], 'q1'), null);
  assert.equal(JSON.stringify(tasks), before);
});
