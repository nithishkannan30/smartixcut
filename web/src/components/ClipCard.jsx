import { useState } from 'react'
import { attachmentUrl, fmtTime } from '../format'

export default function ClipCard({ clip, onEdit, updated }) {
  const [copied, setCopied] = useState(false)
  const caption = clip.title + (clip.hashtags?.length ? `\n${clip.hashtags.join(' ')}` : '')

  async function copy() {
    try {
      await navigator.clipboard.writeText(caption)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      window.prompt('Copy this caption:', caption)
    }
  }

  return (
    <article className="clip">
      <video controls playsInline preload="metadata" src={`${clip.video_url}#t=0.1`} />
      <div className="body">
        <div>
          <span className="pill">Clip {clip.n}</span>{' '}
          {updated && <span className="pill ok">Updated</span>}{' '}
          <span className="muted">{fmtTime(clip.duration)} from {fmtTime(clip.start)}</span>
        </div>
        <h3>{clip.title || 'Untitled clip'}</h3>
        {clip.hashtags?.length > 0 && <div className="tags">{clip.hashtags.join(' ')}</div>}
        {clip.reason && (
          <details className="why"><summary>Why this clip</summary><p>{clip.reason}</p></details>
        )}
        <div className="actions">
          {/* a plain link: the browser starts the download at once and shows its own progress */}
          <a className="btn small" href={attachmentUrl(clip.download_url || clip.video_url, clip.n)}
            download={`smartixcut_clip_${clip.n}.mp4`}>Download</a>
          <button className="btn small" type="button" onClick={copy}>{copied ? 'Copied' : 'Copy caption'}</button>
          {onEdit && (
            <button className="btn small" type="button" onClick={() => onEdit(clip.n)}>Edit</button>
          )}
        </div>
      </div>
    </article>
  )
}