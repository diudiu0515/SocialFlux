// Server only. New sessions derive an immutable review plan from their frozen release.
import {createHash} from 'node:crypto';
import {gate2Tasks} from './gate2';
import type {Workflow} from './research-protocol';
import type {FlowTask, FlowStep} from './scenario-flow';
const quality = {yes: '合理 / 可接受', minor: '轻微瑕疵，不影响判断', no: '不合理 / 影响判断', uncertain: '材料不足 / 无法判断'};
const question = (id: string, label: string, choices: Record<string, string> = quality) => ({id, label, choices});
const sha = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export function scenarioFlowTasks(assignment: {scene_ids: string[]; item_ids: string[]; track: string}, workflow: Workflow, data: {items: any[]}): FlowTask[] {
  const source = gate2Tasks(assignment.scene_ids, workflow.gate2 || (workflow.scenarioFlow?.sourcePacketSha256 ? {packet_sha256: workflow.scenarioFlow.sourcePacketSha256, answers: {}} : undefined), assignment.track), tasks: FlowTask[] = [];
  function add(scene: string, step: FlowStep, key: string, title: string, evidence: unknown, questions: FlowTask['questions'], video?: FlowTask['video']) {
    const body = {id: `flow2:${scene}:${step}:${key}`, scene_id: scene, step, kind: step === 'media' ? 'media-quality' : 'scenario-' + step, title, stage: 'review' as const, evidence, questions, ...(video ? {video} : {})};
    tasks.push({...body, sha256: sha(body)});
  }
  for (const scene of assignment.scene_ids) {
    const items = data.items.filter(x => x.scene_id === scene && assignment.item_ids.includes(x.id));
    if (!items.length) continue;
    const publicQuestion = (x: any) => assignment.track === 'offline_video' ? x.public_video || x.public_text : x.public_text;
    const input = publicQuestion(items[0]).input;
    add(scene, 'scenario', 'public', '场景背景与公开角色卡', {背景: input.context, 行动角色: input.role, 对话对象: input.target_character}, [question('background', '场景背景与约束是否合理？'), question('roles', '公开角色身份、目标和人物关系是否合理？')]);
    const dialogue = new Map<string, {turn: any; bindings: string[]}>();
    for (const item of items) {
      const context = publicQuestion(item).input;
      for (const [label, turns] of [['对话', context.history], ['情境 A', context.history_a], ['情境 B', context.history_b], ['共同结尾', context.shared_ending ? [context.shared_ending] : []]] as [string, any[] | undefined][]) {
        for (const turn of turns || []) {
          const visible = Object.fromEntries(['turn_id', 'evaluated_agent', 'environment_character', 'current_response', 'observable_expression', 'public_events'].filter(k => turn[k] !== undefined).map(k => [k, turn[k]]));
          const key = sha(visible), entry = dialogue.get(key) || {turn: visible, bindings: []};
          entry.bindings.push(`${item.id} · ${label} · ${turn.turn_id || 'ending'}`); dialogue.set(key, entry);
        }
      }
    }
    let turnIndex = 0;
    for (const [key, entry] of dialogue) add(scene, 'dialogue', key.slice(0, 16), `公开对话 ${++turnIndex} · ${entry.turn.turn_id || '共同结尾'}`, {对应题目: entry.bindings, ...entry.turn}, [question('plausible', '本轮对话、角色行为和上下文衔接是否合理？')]);
    if (assignment.track === 'offline_video') {
      const media = new Map(items.flatMap(x => x.media).map((m: any) => [m.sha256, m]));
      for (const [hash, asset] of media as Map<string, any>) {
        const old = source.find(t => t.kind === 'media-quality' && t.video?.sha256 === hash);
        const ev = old?.evidence as Record<string, unknown> | undefined;
        const evidence = {对应题目: items.filter(i => i.media.some((m: any) => m.sha256 === hash)).map(i => i.id), ...(Object.fromEntries(['spoken_text', 'context', 'target_character', 'public_turns', 'spoken_scope', 'full_public_response'].filter(k => ev?.[k] !== undefined).map(k => [k, ev![k]])))};
        add(scene, 'media', hash, '题目视频 · ' + asset.asset_id, evidence, [question('playback', '观看与听音频情况', {watched_listened: '已完整观看并听完', unavailable: '无法播放', partial: '只能部分观看或听音频'}), question('dialogue', '台词与对应文字是否一致？'), question('lipsync', '口型与发声是否协调？'), question('expression', '表情、视线和动作是否符合对话？'), question('context', '人物、场景及表达是否合理？'), question('audio', '音频是否清楚且符合预期？'), question('usability', '整体是否可用于作答？', {usable: '可用（可含不影响判断的轻微瑕疵）', revise: '需修订', unusable: '不可用', uncertain: '无法判断'})], {url: asset.url, sha256: hash});
      }
    }
    const rollout = source.find(t => t.scene_id === scene && t.kind === 'rollout'), scenario = source.find(t => t.scene_id === scene && t.kind === 'scenario');
    const evidence = rollout?.evidence as Record<string, any> | undefined, turns: any[] = evidence?.turns || [];
    const partial = !evidence || evidence.source_complete === false || ['generation_error', 'partial_source_prefix'].includes(evidence.source_status);
    add(scene, 'state', 'initial', '初始 state 与完整角色设定', {角色与场景: scenario?.evidence || {}, initial_state: evidence?.initial_state, 已提供轮数: turns.length, 完整性: partial ? '仅有部分轨迹，未提供轮次无法审核。' : '已提供冻结来源中的完整轨迹。'}, [question('plausible', '初始 state 与角色设定是否一致？')]);
    for (const turn of turns) add(scene, 'state', String(turn.turn_id), `逐轮 state · ${turn.turn_id}`, {turn_id: turn.turn_id, 行动: turn.policy_action, 回应: turn.environment_response, state_before: turn.state_before, state_delta: turn.numeric_state_delta, state_after: turn.state_after}, [question('plausible', '本轮 state 更新的方向、幅度和对话依据是否合理？')]);
    if (partial) add(scene, 'state', 'coverage', '缺失轨迹确认', {说明: `本场景仅提供 ${turns.length} 轮同源记录。请审核所有已提供轮次；未提供部分无法判断，不得视为通过。`, source_status: evidence?.source_status || 'missing', provenance: evidence?.provenance || null}, [question('coverage', '对未提供部分的判断', {unverifiable: '记录缺失，无法审核完整轨迹'})]);
  }
  return tasks;
}
export function scenarioFlowView(tasks: FlowTask[], workflow: Workflow) {
  const flow = workflow.scenarioFlow!;
  const unlocked = ['gt', 'complete'].includes(workflow.phase);
  return {version: 2, step: flow.step, tasks: tasks.filter(t => t.step === flow.step), stateTimeline: unlocked ? tasks.filter(t => t.step === 'state') : []};
}
