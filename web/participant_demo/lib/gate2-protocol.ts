import {InputError} from './protocol.ts';

export type ReviewTask = {id: string; scene_id: string; kind: string; title: string; stage: 'independent' | 'review'; sha256: string;
  tracks?: string[]; evidence: unknown; questions: {id: string; label: string; choices: Record<string, string>}[]; video?: {url: string; sha256: string}};
export type ReviewAnswers = Record<string, {values: Record<string, string>; rationale: string}>;
export type Gate2Workflow = {packet_sha256: string; answers: ReviewAnswers; independentLockedAt?: string};
export function reviewApplies(task: ReviewTask, track?: string) {
  // Omitted track retains historical callers. New assignments always pass it.
  if (!track) return true;
  if (task.tracks) return task.tracks.includes(track);
  if (task.kind.startsWith('T4-')) return track === 't4';
  if (track === 't4') return false;
  return task.kind !== 'media-quality' || track === 'offline_video';
}
export function reviewComplete(task: ReviewTask, answers: ReviewAnswers) {
  const row = answers[task.id];
  return !!row?.rationale?.trim() && task.questions.every(q => Object.hasOwn(q.choices, row.values?.[q.id] || '')) && !reviewIssue(task, row);
}
export function reviewIssue(task: ReviewTask, row: ReviewAnswers[string]) {
  if (['media-quality', 'T4-video'].includes(task.kind) && row.values.usability === 'usable') {
    if (row.values.playback !== 'watched_listened') return '标记可用前须完整观看并听完；未完成时请选择无法判断。';
    if (Object.entries(row.values).some(([key,value]) => !['playback','usability'].includes(key) && ['no','uncertain'].includes(value))) return '有缺陷或尚未确认的项目不能同时标记可用，请调整可用性或补充核对。';
  }
  if (task.kind === 'T4-trigger') {
    const coverage = (task.evidence as {media_coverage?: {missing?:number; available_exact_bound?:number}})?.media_coverage;
    if (coverage && row.values.media_verifiability === 'complete' && (coverage.missing || 0) > 0) return '材料清单仍有缺失片段，不能标记所有触发视频可核验。';
    if (coverage && row.values.media_verifiability === 'partial' && !coverage.available_exact_bound) return '本轨迹没有精确绑定的成品视频，请选择无实际视频或无法判断。';
  }
  return '';
}
export function validateReview(value: unknown, tasks: ReviewTask[], complete: boolean): ReviewAnswers {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new InputError('环境核对格式无效。');
  const rows = value as ReviewAnswers, clean: ReviewAnswers = {};
  if (Object.keys(rows).some(id => !tasks.some(t => t.id === id))) throw new InputError('环境核对包含其他场景或未开放的任务。');
  for (const task of tasks) {
    const row = rows[task.id];
    if (!row) {if (complete) throw new InputError('请完成环境核对：' + task.title); continue;}
    if (!row || typeof row !== 'object' || !row.values || typeof row.values !== 'object' || Array.isArray(row.values) || typeof row.rationale !== 'string' || row.rationale.length > 4000) throw new InputError('环境核对依据格式无效（最多 4000 字）。');
    for (const [key, v] of Object.entries(row.values)) {
      const q = task.questions.find(q => q.id === key);
      if (!q || typeof v !== 'string' || (v !== '' && !Object.hasOwn(q.choices, v))) throw new InputError('环境核对选项无效。');
    }
    if (complete && !reviewComplete(task, rows)) throw new InputError(reviewIssue(task, row) || '请填写全部判断与依据：' + task.title);
    clean[task.id] = {values: {...row.values}, rationale: row.rationale};
  }
  return clean;
}
