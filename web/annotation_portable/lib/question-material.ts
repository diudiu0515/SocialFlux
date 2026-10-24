import type {FlowTask} from './scenario-flow';

/** Select only evidence explicitly bound to this question. Never infer scope
 * from a scene ID, turn number, or prefix shared with another question.
 * Retain the canonical task and digest so saved reviews remain auditable.
 */
export function scopedFlowTasks(tasks: FlowTask[], itemId: string): FlowTask[] {
  if (!itemId) return [];
  return tasks.filter(task => {
    if (!['dialogue', 'media'].includes(task.step)) return false;
    const bindings = (task.evidence as {对应题目?: unknown} | null)?.对应题目;
    return Array.isArray(bindings) && bindings.some(binding =>
      typeof binding === 'string' && (binding === itemId || binding.startsWith(itemId + ' · ')));
  });
}

/** Task digests cover the full source task, while this display projection omits
 * references to other questions that happen to reuse the same evidence.
 */
export function questionEvidence(task: FlowTask, itemId: string): unknown {
  if (!scopedFlowTasks([task], itemId).length) return null;
  const evidence = task.evidence as Record<string, unknown>;
  return {...(task.step === 'media' ? {} : evidence), 对应题目: (evidence.对应题目 as string[]).filter(binding =>
    binding === itemId || binding.startsWith(itemId + ' · '))};
}
