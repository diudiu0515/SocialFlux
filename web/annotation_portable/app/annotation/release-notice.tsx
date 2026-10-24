'use client';
import {ArrowRight} from 'lucide-react';

type VideoFormat = 'checkpoint' | 'full' | 'none';
export type ReleaseInfo = {isCurrent: boolean; latestSeedanceReady?: boolean; currentTotal: number; assignedCount: number; latestTotal: number; latestSceneCount: number; latestQuestionsPerScene: number | null; latestVideoTotal?: number; latestVideoScenes?: number; currentVideoFormat?: VideoFormat; latestVideoFormat?: VideoFormat; latestPublicContextReady?: boolean; currentPublicContextReady?: boolean};

export default function ReleaseNotice({info, disabled, onSwitch}: {info?: ReleaseInfo; disabled: boolean; onSwitch: () => Promise<void>}) {
  if (!info) return null;
  const short = info.latestVideoFormat === 'checkpoint';
  const contextUpdate = info.latestPublicContextReady && !info.currentPublicContextReady;
  if (info.isCurrent) return <p className="release-current" aria-label="题库版本">{info.latestSeedanceReady ? 'Seedance 视频 · 逐题材料审核' : info.currentPublicContextReady ? '公开背景已补齐' : short ? '新版素材 · 每段视频 4–5 秒' : '当前题库'} · 本次 {info.assignedCount} 题</p>;
  return <section className="release-notice outdated" aria-label="题库版本">
    <div><strong>{info.latestSeedanceReady ? '新版已恢复 Seedance 视频与逐题审核' : contextUpdate ? '新版已补齐三项公开背景' : info.currentVideoFormat === 'full' && short ? '你正在恢复旧版长视频任务' : '你正在继续旧版标注'}</strong>
      <p>{info.latestSeedanceReady ? '新版按题开放对应对话与视频，T2 保持文字条件。当前记录保留旧材料；请从新版入口开始新任务。' : contextUpdate ? '人物关系、权力与资源、显性目标冲突现在可在首次作答前查看。此任务保留原材料，请从新版入口领取新任务。' : short ? '新版已使用每段 4–5 秒的短视频。旧恢复码仍对应原来的素材。' : `新版已开放 ${info.latestTotal} 题。`}</p>
      <p className="small muted">请保留旧恢复码。保存后可返回入口，另开新版任务；原记录保留，答案不会混入新版。</p>
    </div>
    <div className="release-actions"><button id="switch-latest-release" className="primary" disabled={disabled} onClick={onSwitch}>保存并进入新版入口<ArrowRight size={16}/></button><a href="/api/annotation/export" download>下载旧版记录</a></div>
  </section>;
}
