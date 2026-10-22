'use client';
import {ArrowRight} from 'lucide-react';

export type ReleaseInfo = {isCurrent: boolean; currentTotal: number; assignedCount: number; latestTotal: number; latestSceneCount: number; latestQuestionsPerScene: number | null; latestVideoTotal?: number; latestVideoScenes?: number};

export default function ReleaseNotice({info, disabled, onSwitch}: {info?: ReleaseInfo; disabled: boolean; onSwitch: () => Promise<void>}) {
  if (!info) return null;
  return <section className={'release-notice' + (info.isCurrent ? '' : ' outdated')} aria-label="题库版本">
    <div><strong>{info.isCurrent ? '当前题库' : '你正在继续旧版标注'} · 共 {info.currentTotal} 题</strong><p>本次分配 {info.assignedCount} 题。{info.isCurrent ? `全库包含 ${info.latestSceneCount} 个场景${info.latestQuestionsPerScene ? `，每场景 ${info.latestQuestionsPerScene} 题` : ''}。` : `最新题库已更新为 ${info.latestTotal} 题、${info.latestSceneCount} 个场景${info.latestQuestionsPerScene ? `，每场景 ${info.latestQuestionsPerScene} 题` : ''}。`}</p>
      {info.latestVideoTotal !== undefined && <p>新版音视频已开放 {info.latestVideoTotal} 题（{info.latestVideoScenes} 个完整场景）。</p>}
      {!info.isCurrent && <p className="small muted">旧会话保留原题量、素材和答案。进入新版会另建记录，请保留原恢复码；旧答案不会填入新版题目。</p>}
    </div>
    {!info.isCurrent && <div className="release-actions"><button id="switch-latest-release" className="primary" disabled={disabled} onClick={onSwitch}>保存并进入新版题库<ArrowRight size={16}/></button><a href="/api/demo/export" download>下载旧版记录</a></div>}
  </section>;
}
