"use client";
import {useEffect, useRef, useState} from "react";
import {ArrowLeft, ArrowRight, Check, CheckCircle2, Download, LogOut, MessageSquare, Play, Save} from "lucide-react";
import {type Answer, type Answers, type MediaReview, type MediaReviews, validateMediaReviews} from "../lib/protocol";
import {Material, type Question} from "./material";
import {MediaVideo} from './media-video';
import ReleaseNotice, {type ReleaseInfo} from "./release-notice";

type Video = {asset_id: string; sha256: string; url: string; scene_id: string; kind: "nonverbal" | "talking_head";
  speaker: string; label: string; spoken_text: string | null; source_text: string | null;
  observable_expression: Record<string, unknown>; bindings: {instance_id: string; evidence_ids: string[]}[]};
type Scene = {scene_id: string; question_ids: string[]; video_ids: string[]};
type Session = {id: string; alias: string; answers: Answers; mediaReviews: MediaReviews; revision: number;
  status: string; submittedAt: string | null; updatedAt: string};
export type WorkspaceState = {releaseInfo?: ReleaseInfo; session: Session; questions: Question[]; videos: Video[]; scenes: Scene[];
  dataset: {sha256: string; release: string; kind: string}; invited: boolean};
const emptyReview: MediaReview = {verdict: "", issues: [], note: "", watched: false};
const emptyAnswer: Answer = {answer: null, confidence: "", rationale: "", issue: "none"};
const verdictNames = {usable: "可用", revise: "需修改", unusable: "不可用", uncertain: "无法判断"};
const issueNames = {dialogue: "台词不匹配 / 多读漏读", lip_sync: "口型不同步", expression: "表情与线索不符",
  unnatural: "说话或动作不自然", picture: "画面 / 人物异常", audio: "音质或语音问题",
  context: "与场景不匹配 / 引入额外信息", playback: "无法播放", other: "其他问题"};
const cueNames: Record<string, string> = {facial_expression: "神情", gaze: "视线", speech_style: "表达", prosody: "语气", behavioral_cues: "动作"};
const taskNames: Record<string, string> = {T1: "证据判断", T2: "情境比较", T3: "行动推断"};
function taskName(q: Question) { return taskNames[q.instance_id.match(/-T[123]-/)?.[0].slice(1, -1) || ""] || "题目"; }
function reviewComplete(video: Video, review?: MediaReview) {
  try {validateMediaReviews(review ? {[video.asset_id]: review} : {}, [video], true); return true;} catch {return false;}
}
// Server validation orders records by dataset; visiting scenes out of order must not leave a saved draft dirty.
function fingerprint(value: unknown) {
  return JSON.stringify(value, (_key, entry) => entry && typeof entry === "object" && !Array.isArray(entry)
    ? Object.fromEntries(Object.entries(entry).sort(([a], [b]) => a.localeCompare(b))) : entry);
}
function download(name: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: "application/json"}));
  const link = document.createElement("a"); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function MultimodalWorkspace({initial, onLogout}: {initial: WorkspaceState; onLogout: () => Promise<void>}) {
  const [state, setState] = useState(initial), [answers, setAnswers] = useState(initial.session.answers);
  const [reviews, setReviews] = useState(initial.session.mediaReviews || {}), [sceneIndex, setSceneIndex] = useState(0);
  const [videoId, setVideoId] = useState(""), [questionId, setQuestionId] = useState(""), [tab, setTab] = useState("media");
  const [checking, setChecking] = useState(false), [filter, setFilter] = useState("all"), [attestation, setAttestation] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [blocked, setBlocked] = useState(false);
  const [notice, setNotice] = useState(""), [conflictDraft, setConflictDraft] = useState<unknown>(null);
  const [restored, setRestored] = useState(false);
  const lock = useRef(false), videoRef = useRef<HTMLVideoElement>(null);
  const {session, videos, scenes, questions} = state, submitted = session.status === "submitted";
  const dirty = fingerprint(answers) !== fingerprint(session.answers) || fingerprint(reviews) !== fingerprint(session.mediaReviews || {});
  const ready = videos.filter(video => reviewComplete(video, reviews[video.asset_id])).length;
  const answered = questions.filter(q => answers[q.instance_id]?.answer && answers[q.instance_id]?.confidence).length;
  const missingConfidence = Object.values(answers).filter(a => a.answer && !a.confidence).length;
  const scene = scenes[sceneIndex], sceneVideos = videos.filter(v => v.scene_id === scene.scene_id);
  const video = sceneVideos.find(v => v.asset_id === videoId) || sceneVideos[0];
  const sceneQuestions = questions.filter(q => scene.question_ids.includes(q.instance_id));
  const q = sceneQuestions.find(q => q.instance_id === questionId) || sceneQuestions.find(q => video.bindings.some(b => b.instance_id === q.instance_id)) || sceneQuestions[0];
  const review = reviews[video.asset_id] || emptyReview, answer = answers[q.instance_id] || emptyAnswer;
  const visibleScenes = scenes.filter(s => filter === "pending" ? s.video_ids.some(id => !reviewComplete(videos.find(v => v.asset_id === id)!, reviews[id]))
    : filter === "flagged" ? s.video_ids.some(id => ["revise", "unusable", "uncertain"].includes(reviews[id]?.verdict)) : true);

  useEffect(() => {
    if (!submitted) {
      try {
        const saved = JSON.parse(localStorage.getItem("sf-media-draft-" + session.id) || "null");
        if (saved && saved.dataset === state.dataset.sha256) {
          if (saved.revision === session.revision) {
            setAnswers(saved.answers); setReviews(saved.mediaReviews);
            if (fingerprint(saved.answers) !== fingerprint(session.answers) || fingerprint(saved.mediaReviews) !== fingerprint(session.mediaReviews)) setNotice("已恢复当前设备上尚未保存的输入。");
          } else {
            localStorage.setItem("sf-media-conflict-" + session.id, JSON.stringify(saved));
            setConflictDraft(saved); setNotice("云端记录已有更新。当前显示云端版本，旧本地草稿可先下载保留。");
          }
        }
        const previousConflict = localStorage.getItem("sf-media-conflict-" + session.id);
        if (previousConflict) {
          setConflictDraft(JSON.parse(previousConflict));
          setNotice(current => current || "此设备保留着一次冲突前的旧草稿，可下载留存。");
        }
      } catch {setNotice("本地草稿无法读取，已加载云端记录。");}
    }
    const first = scenes.findIndex(s => s.video_ids.some(id => !reviewComplete(videos.find(v => v.asset_id === id)!, initial.session.mediaReviews?.[id])));
    const nextScene = scenes[first < 0 ? 0 : first];
    setSceneIndex(first < 0 ? 0 : first);
    setVideoId(nextScene.video_ids.find(id => !reviewComplete(videos.find(v => v.asset_id === id)!, initial.session.mediaReviews?.[id])) || nextScene.video_ids[0]);
    setRestored(true);
  // This initialization belongs to one recovered session.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!restored || submitted) return;
    try {localStorage.setItem("sf-media-draft-" + session.id, JSON.stringify({dataset: state.dataset.sha256, revision: session.revision, answers, mediaReviews: reviews}));}
    catch {setNotice("当前设备无法备份草稿，请留意云端保存状态。");}
  }, [answers, reviews, session.id, session.revision, restored, submitted, state.dataset.sha256]);
  useEffect(() => {
    if (!dirty || submitted) return;
    const warn = (event: BeforeUnloadEvent) => {event.preventDefault(); event.returnValue = "";};
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, submitted]);
  useEffect(() => {
    if (!restored || submitted || !dirty || busy || blocked) return;
    const timer = setTimeout(() => {void persist();}, 1400); return () => clearTimeout(timer);
  // persist captures this exact draft and server revision; edits made during a save stay dirty.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [answers, reviews, session.revision, restored, submitted, dirty, busy, blocked]);

  async function persist(complete = false) {
    if (lock.current) return false;
    lock.current = true; setBusy(true); setError("");
    try {
      const response = await fetch("/api/demo/" + (complete ? "submit" : "draft"), {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({answers, mediaReviews: reviews, revision: session.revision, attestation})});
      const next = await response.json() as WorkspaceState & {error?: string}; if (!response.ok) throw new Error(next.error || "保存失败，请重试。");
      setState(next); setBlocked(false);
      if (complete) {localStorage.removeItem("sf-media-draft-" + session.id); window.scrollTo({top: 0});}
      return true;
    } catch (e) {setError((e as Error).message); setBlocked(true); return false;}
    finally {lock.current = false; setBusy(false);}
  }
  function patchReview(id: string, change: Partial<MediaReview>) {setReviews(current => ({...current, [id]: {...(current[id] || emptyReview), ...change}}));}
  function patchAnswer(change: Partial<Answer>) {setAnswers(current => ({...current, [q.instance_id]: {...(current[q.instance_id] || emptyAnswer), ...change}}));}
  async function go(index: number, selectedVideo = "") {
    if (dirty && !await persist()) return;
    videoRef.current?.pause(); setSceneIndex(index); setVideoId(selectedVideo); setQuestionId(""); setChecking(false); window.scrollTo({top: 0, behavior: "smooth"});
  }
  async function nextVideo() {
    const current = videos.findIndex(v => v.asset_id === video.asset_id), next = videos[current + 1];
    if (next) await go(scenes.findIndex(s => s.scene_id === next.scene_id), next.asset_id);
    else if (!dirty || await persist()) {setChecking(true); window.scrollTo({top: 0});}
  }
  function chooseVideo(id: string) {videoRef.current?.pause(); setVideoId(id); setQuestionId("");}
  function chooseQuestion(id: string) {setQuestionId(id); if (!video.bindings.some(b => b.instance_id === id)) {const matching = sceneVideos.find(v => v.bindings.some(b => b.instance_id === id)); if (matching) chooseVideoForQuestion(matching.asset_id, id);}}
  function chooseVideoForQuestion(id: string, qid: string) {videoRef.current?.pause(); setVideoId(id); setQuestionId(qid);}

  return <><header className="topbar"><a className="brand" href="/"><span className="brand-icon"><MessageSquare size={21}/></span>SocialFlux<span className="brand-divider"/><small>答题与视频审核</small></a><div className="top-right"><span className="demo-tag">MULTIMODAL · 52</span><button className="text-button" disabled={busy || dirty} onClick={onLogout}><LogOut size={14}/>退出</button></div></header>
    <div className="release-shell"><ReleaseNotice info={state.releaseInfo} disabled={busy || blocked} onSwitch={async () => {if (!dirty || await persist()) await onLogout();}}/></div>
    {submitted ? <main className="receipt panel"><div className="success-icon"><CheckCircle2 size={36}/></div><div className="eyebrow">审核提交成功</div><h1>52 段视频，你的判断已保存。</h1><p className="muted">视频可用性与题目答案分别记录，已提交的这份记录已锁定。</p><dl className="receipt-data"><div><dt>匿名编号</dt><dd>{session.alias}</dd></div><div><dt>视频审核</dt><dd>{ready} / {videos.length}</dd></div><div><dt>选填题目</dt><dd>{answered} / {questions.length}</dd></div><div><dt>提交时间</dt><dd>{new Date(session.submittedAt!).toLocaleString("zh-CN")}</dd></div></dl><a className="primary" href="/api/demo/export" download><Download size={16}/>下载我的答题与审核记录</a><p className="small muted">审核意见用于素材筛选，仍需研究者汇总；不会自动成为标准答案。</p></main>
    : <main className="workspace multimodal-workspace">
      <div className="workspace-heading"><div><div className="eyebrow">{session.alias} · 按场景连续审核</div><h1>{checking ? "检查全部审核，再提交。" : "看视频，留下你的判断。"}</h1></div><div className="review-save"><span role="status" className={dirty ? "save-status unsaved" : "save-status"}>{busy ? "正在保存…" : dirty ? "有未保存修改" : "进度已保存"}</span><button className="secondary" disabled={busy} onClick={() => persist()}><Save size={14}/>保存</button></div></div>
      {error && <div className="error" role="alert">{error}<button className="text-button" onClick={() => download("socialflux-local-draft.json", {dataset: state.dataset, answers, mediaReviews: reviews})}>下载当前草稿</button></div>}
      {notice && <p className="notice">{notice}{!!conflictDraft && <button className="text-button" onClick={() => download("socialflux-previous-draft.json", conflictDraft)}>下载旧草稿</button>}</p>}
      <div className="progress-track"><div style={{width: `${ready / videos.length * 100}%`}}/></div><div className="progress-caption"><span>视频审核 {ready} / {videos.length} · 题目作答 {answered} / {questions.length}（选填）</span><button className="text-button" disabled={busy} onClick={async () => {if (!dirty || await persist()) {videoRef.current?.pause(); setChecking(true);}}}>检查提交<ArrowRight size={14}/></button></div>
      {checking ? <section className="review panel"><div className="section-kicker"><CheckCircle2 size={16}/>审核总览</div><h2>每段视频只审核一次</h2><p className="muted">视频可用性为必填；相关题目可选作答，已选择答案的题目需补充把握程度。</p><div className="review-counts">{Object.entries(verdictNames).map(([value, label]) => <span key={value}>{label}<b>{videos.filter(v => reviews[v.asset_id]?.verdict === value).length}</b></span>)}</div><div className="video-review-list">{videos.map(v => <button key={v.asset_id} className="review-row" disabled={busy} onClick={() => go(scenes.findIndex(s => s.scene_id === v.scene_id), v.asset_id)}><span><b>{v.scene_id} · {v.kind === "talking_head" ? "英文共同回应" : "前史表情片段"}</b><small>{v.speaker}</small></span><span className="review-confidence">{reviewComplete(v, reviews[v.asset_id]) ? verdictNames[reviews[v.asset_id].verdict as keyof typeof verdictNames] : "待补充审核"}<ArrowRight size={14}/></span></button>)}</div><label className="check-line attest"><input id="media-attestation" type="checkbox" checked={attestation} onChange={e => setAttestation(e.target.checked)}/><span>以上审核和已填写的答案由我独立完成。</span></label><button id="submit-media" className="primary" disabled={busy || ready !== videos.length || !!missingConfidence || !attestation} onClick={() => persist(true)}>确认提交 {videos.length} 段审核<ArrowRight size={16}/></button>{ready !== videos.length && <p className="notice">还有 {videos.length - ready} 段视频需要补充判断、观看确认或问题说明。</p>}{!!missingConfidence && <p className="notice">还有 {missingConfidence} 道已作答题目未填写把握程度。</p>}</section>
      : <><div className="scene-toolbar"><label>场景<select id="scene-select" value={scene.scene_id} disabled={busy} onChange={e => go(scenes.findIndex(s => s.scene_id === e.target.value))}>{(visibleScenes.some(s => s.scene_id === scene.scene_id) ? visibleScenes : [scene, ...visibleScenes]).map(s => <option value={s.scene_id} key={s.scene_id}>{s.scene_id} · {s.video_ids.filter(id => reviewComplete(videos.find(v => v.asset_id === id)!, reviews[id])).length}/{s.video_ids.length} 已审</option>)}</select></label><label>筛选<select value={filter} onChange={e => setFilter(e.target.value)}><option value="all">全部 45 个场景</option><option value="pending">尚未审完</option><option value="flagged">需修改或待判断</option></select></label><div className="scene-paging"><button className="secondary" disabled={busy || sceneIndex === 0} onClick={() => go(sceneIndex - 1)} aria-label="上一个场景"><ArrowLeft size={15}/></button><span>{sceneIndex + 1} / {scenes.length}</span><button className="secondary" disabled={busy || sceneIndex === scenes.length - 1} onClick={() => go(sceneIndex + 1)} aria-label="下一个场景"><ArrowRight size={15}/></button></div></div>
      <div className="media-work-grid"><div className="media-left"><section className="panel video-panel"><div className="section-kicker"><Play size={16}/>{scene.scene_id} · {video.speaker}<span>{videos.findIndex(v => v.asset_id === video.asset_id) + 1} / {videos.length}</span></div><div className="clip-tabs" aria-label="本场景视频">{sceneVideos.map(v => <button key={v.asset_id} className={v.asset_id === video.asset_id ? "active" : ""} onClick={() => chooseVideo(v.asset_id)}>{v.kind === "talking_head" ? "英文共同回应" : "前史表情片段"}{reviewComplete(v, reviews[v.asset_id]) && <Check size={13}/>}</button>)}</div><MediaVideo key={video.asset_id} ref={videoRef} src={video.url} controls playsInline preload="metadata" onEnded={() => patchReview(video.asset_id, {watched: true})}/><p className="clip-scope">{video.kind === "talking_head" ? "用于 T2 两段情境共用的 ending。这里只覆盖共同回应，完整前史对白尚未补齐。" : "用于对应前史的非语言表情线索，不是完整对白配音。请检查表情、动作及其与题面的对应关系。"}</p>{video.spoken_text && <div className="spoken-script"><h3>英文台词</h3><p lang="en">{video.spoken_text}</p>{video.source_text && video.source_text !== video.spoken_text && <details><summary>来源台词对照</summary><p>{video.source_text}</p></details>}</div>}<details className="expected-cues"><summary>对应的公开表情与动作</summary><dl>{Object.entries(video.observable_expression || {}).map(([key, value]) => <div key={key}><dt>{cueNames[key] || key}</dt><dd>{Array.isArray(value) ? value.join("；") : String(value)}</dd></div>)}</dl></details><p className="small muted">对应题目：{video.bindings.map(b => `${b.instance_id}（${b.evidence_ids.join("、")}）`).join("；")}</p></section><details className="material-expand" open={tab === "questions" ? true : undefined}><summary>查看当前题目的情境与对话 · {q.instance_id}</summary><Material q={q}/></details></div>
      <section className="panel media-decision"><div className="work-tabs" role="tablist"><button role="tab" aria-selected={tab === "media"} onClick={() => setTab("media")}>视频可用性</button><button role="tab" aria-selected={tab === "questions"} onClick={() => setTab("questions")}>题目作答 · 选填</button></div>{tab === "media" ? <div className="decision-body"><h2>这段视频能用于对应题目吗？</h2><p className="muted">结合左侧材料判断。视频外观是否自然、线索是否准确，都可以记录。</p><fieldset className="verdict-options"><legend className="sr-only">视频可用性判断</legend>{Object.entries(verdictNames).map(([value, label]) => <label key={value} className={review.verdict === value ? "selected" : ""}><input type="radio" name="media-verdict" value={value} checked={review.verdict === value} onChange={() => patchReview(video.asset_id, {verdict: value as MediaReview["verdict"]})}/>{label}</label>)}</fieldset><fieldset className="media-issues"><legend>发现的问题 <span>可多选</span></legend>{Object.entries(issueNames).map(([value, label]) => <label key={value}><input type="checkbox" name="media-issue" value={value} checked={review.issues.includes(value as MediaReview["issues"][number])} onChange={e => patchReview(video.asset_id, {issues: e.target.checked ? [...review.issues, value as MediaReview["issues"][number]] : review.issues.filter(x => x !== value)})}/>{label}</label>)}</fieldset><label className="field">修改建议或判断依据<textarea id="media-note" maxLength={2000} value={review.note} onChange={e => patchReview(video.asset_id, {note: e.target.value})} placeholder="例如：某个词没说清、口型错位、表情过于夸张，或无法播放的位置。"/></label><label className="check-line watched-confirm"><input id="media-watched" type="checkbox" checked={review.watched} onChange={e => patchReview(video.asset_id, {watched: e.target.checked})}/><span>我已查看这段视频。完整播放结束后会自动勾选；无法播放时请勾选对应问题。</span></label><button className="primary wide" id="save-next-video" disabled={busy} onClick={nextVideo}>保存并看下一段<ArrowRight size={16}/></button><p className="small muted">修改后自动保存，也可暂时跳过。一个视频的审核会复用于它对应的所有题目。</p></div>
      : <div className="decision-body answer-panel"><div className="scene-question-tabs" aria-label="当前场景题目">{sceneQuestions.map((item, i) => <button key={item.instance_id} className={q.instance_id === item.instance_id ? "active" : ""} onClick={() => chooseQuestion(item.instance_id)}>{i + 1} · {taskName(item)}{answers[item.instance_id]?.answer && <Check size={12}/>}</button>)}</div><div className="section-kicker">{q.instance_id}</div><h2 id="question-title">{q.question}</h2><fieldset className="options"><legend className="sr-only">选择答案</legend>{Object.entries(q.options).map(([value, text]) => <label className={answer.answer === value ? "option selected" : "option"} key={value}><input type="radio" name="answer" value={value} checked={answer.answer === value} onChange={() => patchAnswer({answer: value})}/><span className="option-key">{value}</span><span>{text}</span></label>)}</fieldset><fieldset className="confidence"><legend>把握程度 <span>作答后必填</span></legend><div>{Object.entries({high: "很有把握", medium: "比较有把握", low: "不太确定"}).map(([value, label]) => <label key={value} className={answer.confidence === value ? "selected" : ""}><input type="radio" name="confidence" value={value} checked={answer.confidence === value} onChange={() => patchAnswer({confidence: value as Answer["confidence"]})}/>{label}</label>)}</div></fieldset><label className="field">判断依据<textarea maxLength={2000} value={answer.rationale} onChange={e => patchAnswer({rationale: e.target.value})}/></label><label className="field">题目反馈<select value={answer.issue} onChange={e => patchAnswer({issue: e.target.value as Answer["issue"]})}><option value="none">没有发现问题</option><option value="unclear">表述不清楚</option><option value="multiple">多个选项都合理</option><option value="insufficient">材料不足以判断</option></select></label><button className="text-button" onClick={() => patchAnswer({answer: null, confidence: ""})}>清除这题的答案</button><button className="primary wide" disabled={busy} onClick={() => persist()}><Save size={15}/>保存答案和视频审核</button></div>}</section></div></>}
    </main>}<footer><span>SocialFlux · 视频审核与题目答案分别记录</span><span>公开材料 · 匿名参与 · 可恢复进度</span></footer></>;
}
