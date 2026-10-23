'use client';
import {ArrowRight} from 'lucide-react';

type VideoFormat = 'checkpoint' | 'full' | 'none';
export type ReleaseInfo = {isCurrent: boolean; currentTotal: number; assignedCount: number; latestTotal: number; latestSceneCount: number; latestQuestionsPerScene: number | null; latestVideoTotal?: number; latestVideoScenes?: number; currentVideoFormat?: VideoFormat; latestVideoFormat?: VideoFormat; currentMediaRetired?: boolean};

export default function ReleaseNotice({info, disabled, onSwitch}: {info?: ReleaseInfo; disabled: boolean; onSwitch: () => Promise<void>}) {
  if (!info) return null;
  const short = info.latestVideoFormat === 'checkpoint';
  if (info.isCurrent) return <p className="release-current" aria-label="题库版本">{short ? '新版素材 · 每段视频约 5 秒' : '当前题库'} · 本次 {info.assignedCount} 题</p>;
  return <section className="release-notice outdated" aria-label="题库版本">
    <div><strong>{info.currentVideoFormat === 'full' && short ? '你正在恢复旧版长视频任务' : '你正在继续旧版标注'}</strong>
      <p>{info.currentMediaRetired ? '旧版视频已清理，原题目和标注记录仍保留。请进入新版入口继续使用视频材料。' : short ? '新版已使用每段约 5 秒的短视频。旧恢复码仍对应原来的素材。' : `新版已开放 ${info.latestTotal} 题。`}</p>
      <p className="small muted">请保留旧恢复码。保存后可返回入口，另开新版任务；原记录保留，答案不会混入新版。</p>
    </div>
    <div className="release-actions"><button id="switch-latest-release" className="primary" disabled={disabled} onClick={onSwitch}>保存并进入新版入口<ArrowRight size={16}/></button><a href="/api/demo/export" download>下载旧版记录</a></div>
  </section>;
}
