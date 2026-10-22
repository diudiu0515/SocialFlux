import {ClipboardCheck} from 'lucide-react';

type Props = {t4: boolean; phase: string; hasGate2: boolean};

export default function ManualReviewReminder({t4, phase, hasGate2}: Props) {
  const gate2 = [
    ['Scenario 是否合理', '角色动机、背景约束与初始状态是否自洽。'],
    ['Rollout 是否合理', '对话与角色行为是否连贯；状态变化、行动后果与时间尺度是否合理。'],
    ['环境专项核对', '按已分配材料检查状态方向、释义及历史／人格干预。'],
    ['音视频质量', '已分配的视频按素材去重核对：台词、口型、表情、人物一致性、声音与可用性。'],
  ];
  const checks = t4 ? [
    ['轨迹五维评分', '先独立判断目标、适应、风险、恢复、关系；每维引用具体轮次。锁定后不可修改。'],
    ...(hasGate2 ? [
    ['Video trigger 是否合理', '评分锁定后逐条填写触发时机、频率、误触发和漏触发判断。'],
    ['触发与视频是否对应', '按轨迹导航核对轮次、人物、台词与状态表达；缺失材料或播放失败也须记录。'],
    ] : []),
  ] : [
    ['答案与题目质量', '先独立盲答；解锁后核对证据、歧义、多解与题目可用性。'],
    ...(hasGate2 ? gate2 : []),
  ];
  const stage = phase === 'complete' ? '已提交' : t4 ? (phase === 't4_review' ? 'T4 · 触发与视频' : 'T4 · 独立评分') : phase === 'blind' ? '独立盲答' : phase === 'gate2' ? 'Gate2 · 独立判断' : 'GT 与环境核对';
  const note = t4
    ? phase === 'complete' ? '人工记录已锁定，可下载本人标注。' : phase === 't4_review' ? '在主面板逐项填写审核表；全部完成后统一提交并查看机器评分对照。' : hasGate2 ? '先完成并锁定整组五维评分，之后开放触发与视频审核表。机器评分在最终提交后开放。' : '使用公开文字独立完成五维评分；提交后查看机器评分对照。'
    : phase === 'blind'
      ? '先完成整组盲答；场景、rollout 与私有证据解锁后再核对。'
      : phase === 'gate2'
        ? '先独立判断状态方向与释义，锁定后再看机器结果及完整场景、rollout。'
        : hasGate2
          ? '在「场景与 rollout 核对」填写全部已分配的环境和媒体任务；同一素材只填一次，问题写明轮次与依据。'
          : '判断依据请引用具体证据；证据不足时明确记录。';
  return <aside className="manual-review-reminder" aria-labelledby="manual-review-title">
    <div className="manual-review-heading"><ClipboardCheck size={17} aria-hidden="true"/><h2 id="manual-review-title">人工核对清单</h2><span>{stage}</span></div>
    <ul>{checks.map(([title, detail]) => <li key={title}><strong>{title}</strong><p>{detail}</p></li>)}</ul>
    <p className="manual-review-note">{note}</p>
  </aside>;
}
