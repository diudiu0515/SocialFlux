export default function VideoTranscript({text, language = 'en'}: {text?: unknown; language?: string}) {
  if (typeof text !== 'string' || !text.trim()) return null;
  return <section className="spoken-script video-transcript" aria-label="视频台词">
    <h3>视频台词</h3>
    <p lang={language}>{text}</p>
    <p className="small muted">仅对应这段视频的口述内容。</p>
  </section>;
}
