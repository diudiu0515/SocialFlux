import type {ReviewTask} from './gate2-protocol';

export type ReviewBundle = {sha256: string; dataset_sha256: string; tasks: (ReviewTask & {machine?: unknown})[]};
type StoredBundle = Omit<ReviewBundle, 'tasks'> & {tasks?: ReviewBundle['tasks']; task_refs?: string[]};
export type ReviewRegistry = {current: string; versions: StoredBundle[]; task_pool?: Record<string, ReviewBundle['tasks'][number]>};

// Historical bundles share immutable tasks. Resolve only the requested version;
// materializing every historical copy at startup exceeds the hosted memory limit.
export function registryBundle(registry: ReviewRegistry, hash: string): ReviewBundle | undefined {
  const bundle = registry.versions.find(value => value.sha256 === hash);
  if (!bundle) return undefined;
  if (Array.isArray(bundle.tasks)) return bundle as ReviewBundle;
  if (!bundle.task_refs || !registry.task_pool) throw new Error('Invalid review registry');
  const tasks = bundle.task_refs.map(sha => {
    const task = registry.task_pool![sha];
    if (!task || task.sha256 !== sha) throw new Error('Review task reference mismatch');
    return task;
  });
  return {...bundle, tasks};
}
