import { useEffect, useRef, useState } from 'react'
import { api, post } from '../api'
import { fmtTime } from '../format'

// The caption editor. Two ways to arrive here:
//   - "review":  the job is paused after the AI picked the clips. Fix the captions, then render all clips.
//   - "edit":    a finished clip. Fix the captions, then re-render just that clip (focusClip).
// The server does the saving: we only send the lines whose text changed.

const tagList = (s) => s.split(/[\s,]+/).filter(Boolean)
// A caption is one line of text, so Enter jumps to the next caption instead of adding a line break.
function nextOnEnter(e) {
  if (e.key !== 'Enter') return
  e.preventDefault()
  e.currentTarget.closest('.ed-line')?.nextElementSibling?.querySelector('textarea')?.focus()
}
const rowsFor = (text) => Math.min(4, Math.max(1, Math.ceil(text.length / 40)))

export default function CaptionEditor({ jobId, focusClip, onSubmitted, onCancel, onNew }) {
  const [data, setData] = useState(null)
  const [problem, setProblem] = useState('')

  useEffect(() => {
    let stopped = false
    api(`/api/jobs/${jobId}/review`)
      .then((d) => { if (!stopped) setData(d) })
      .catch((e) => { if (!stopped) setProblem(e.message) })
    return () => { stopped = true }
  }, [jobId])

  if (problem) {
    return (
      <section className="panel">
        <h2>We can't open the caption editor</h2>
        <div className="err">{problem}</div>
        <div className="actions" style={{ marginTop: 16 }}>
          {onCancel && <button className="btn" type="button" onClick={onCancel}>Back to my clips</button>}
          <button className="btn" type="button" onClick={onNew}>New video</button>
        </div>
      </section>
    )
  }
  if (!data) return <div className="boot" role="status">Loading captions…</div>
  return <EditorBody jobId={jobId} data={data} focusClip={focusClip} onSubmitted={onSubmitted} onCancel={onCancel} />
}

function EditorBody({ jobId, data, focusClip, onSubmitted, onCancel }) {
  const reviewing = data.status === 'review'
  const clips = focusClip ? data.clips.filter((c) => c.n === focusClip) : data.clips

  // what the user has typed so far, keyed by line number / clip number
  const [drafts, setDrafts] = useState(() => Object.fromEntries(data.clips.flatMap((c) => c.lines.map((l) => [l.i, l.text]))))
  const [titles, setTitles] = useState(() => Object.fromEntries(data.clips.map((c) => [c.n, c.title])))
  const [tags, setTags] = useState(() => Object.fromEntries(data.clips.map((c) => [c.n, (c.hashtags || []).join(' ')])))
  const [activeN, setActiveN] = useState(clips[0]?.n)
  const [nowI, setNowI] = useState(-1)                 // the line being spoken right now
  const [noVideo, setNoVideo] = useState(!data.has_video)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const videoRef = useRef(null)

  const clip = clips.find((c) => c.n === activeN) || clips[0]
  const lang = data.language

  const changedIn = (c) => c.lines.filter((l) => drafts[l.i] !== l.text).length
    + (titles[c.n] !== c.title ? 1 : 0) + (tags[c.n] !== (c.hashtags || []).join(' ') ? 1 : 0)
  const totalChanges = clips.reduce((n, c) => n + changedIn(c), 0)
  const unclearIn = (c) => c.lines.filter((l) => l.low_conf && drafts[l.i] === l.orig).length

  function setLine(i, text) { setDrafts((d) => ({ ...d, [i]: text })) }

  function pickClip(n) {
    setActiveN(n)
    setNowI(-1)
  }

  function onTime(e) {
    const v = e.currentTarget
    const cur = clip.lines.find((l) => v.currentTime >= l.start && v.currentTime < l.end)
    setNowI(cur ? cur.i : -1)
    if (v.currentTime >= clip.end) v.pause()          // stay inside this clip
  }

  function playLine(l) {
    const v = videoRef.current
    if (!v) return
    v.currentTime = l.start
    v.play().catch(() => {})
  }

  async function submit() {
    setBusy(true); setError('')
    const body = {
      clips: clips.map((c) => ({
        n: c.n,
        ...(titles[c.n] !== c.title ? { title: titles[c.n] } : {}),
        ...(tags[c.n] !== (c.hashtags || []).join(' ') ? { hashtags: tagList(tags[c.n]) } : {}),
        lines: c.lines.filter((l) => drafts[l.i] !== l.text).map((l) => ({ i: l.i, text: drafts[l.i] })),
      })),
      ...(focusClip ? { only: [focusClip] } : {}),
    }
    try {
      await post(`/api/jobs/${jobId}/render`, body)
      onSubmitted()
    } catch (e) {
      setBusy(false)
      setError(e.message)
    }
  }

  if (!clip) {
    return (
      <section className="panel">
        <h2>Nothing to edit</h2>
        <div className="muted">This video has no clips.</div>
      </section>
    )
  }

  const submitLabel = busy ? 'Starting…'
    : reviewing ? `Render ${clips.length} ${clips.length === 1 ? 'clip' : 'clips'}`
      : `Update clip ${clip.n}`

  return (
    <section className="panel editor">
      <div className="row">
        <div>
          <h2>{reviewing ? 'Check your captions' : `Edit captions · Clip ${clip.n}`}</h2>
          <p className="muted ed-sub">
            {reviewing
              ? 'Fix any spelling, then render. Press a time to hear that line. Yellow lines are where the AI was least sure.'
              : 'Fix any spelling, then update the clip. Only this clip is rendered again.'}
          </p>
        </div>
      </div>

      {clips.length > 1 && (
        <div className="tabs" role="tablist" aria-label="Clips">
          {clips.map((c) => {
            const unclear = unclearIn(c)
            return (
              <button key={c.n} type="button" role="tab" aria-selected={c.n === clip.n}
                className={`tab${c.n === clip.n ? ' on' : ''}`} onClick={() => pickClip(c.n)}>
                Clip {c.n}
                {unclear > 0 && <span className="badge warn" title="Lines the AI was unsure about">{unclear} unclear</span>}
                {changedIn(c) > 0 && <span className="badge ok">edited</span>}
              </button>
            )
          })}
        </div>
      )}

      <div className="ed-grid">
        <div className="ed-side">
          {noVideo ? (
            <div className="note">
              We can't play the original video here, but you can still fix the text. Lines are in speaking order.
            </div>
          ) : (
            <video key={clip.n} ref={videoRef} controls playsInline preload="metadata"
              src={`/api/jobs/${jobId}/source#t=${clip.start},${clip.end}`}
              onTimeUpdate={onTime} onError={() => setNoVideo(true)} />
          )}
          <div className="field">
            <label htmlFor={`title-${clip.n}`}>Title</label>
            <input id={`title-${clip.n}`} type="text" lang={lang} maxLength={200} value={titles[clip.n] ?? ''}
              onChange={(e) => setTitles((t) => ({ ...t, [clip.n]: e.target.value }))} />
          </div>
          <div className="field">
            <label htmlFor={`tags-${clip.n}`}>Hashtags</label>
            <input id={`tags-${clip.n}`} type="text" lang={lang} value={tags[clip.n] ?? ''} placeholder="#reels #shorts"
              onChange={(e) => setTags((t) => ({ ...t, [clip.n]: e.target.value }))} />
          </div>
        </div>

        <div className="ed-lines">
          {clip.lines.length === 0 && <div className="muted">There are no spoken lines in this clip.</div>}
          {clip.lines.map((l) => {
            const text = drafts[l.i] ?? ''
            const removed = text.trim() === ''
            const edited = text !== l.orig
            const unclear = l.low_conf && !edited
            const cls = ['ed-line', l.i === nowI ? 'now' : '', unclear ? 'low' : '', removed ? 'removed' : ''].join(' ').trim()
            return (
              <div key={l.i} className={cls}>
                <button type="button" className="ed-time" onClick={() => playLine(l)} disabled={noVideo}
                  aria-label={`Play line at ${fmtTime(l.start)}`}>
                  <span aria-hidden="true">▶</span> {fmtTime(l.start)}
                </button>
                <div>
                  <textarea lang={lang} rows={rowsFor(text)} value={text} aria-label={`Caption at ${fmtTime(l.start)}`}
                    placeholder="Removed. Type to bring it back."
                    onKeyDown={nextOnEnter}
                    onChange={(e) => setLine(l.i, e.target.value.replace(/\n/g, ' '))} />
                  <div className="ed-meta">
                    {unclear && <span className="badge warn">Unclear audio, please check</span>}
                    {edited && !removed && <span className="badge ok">edited</span>}
                    {removed && <span className="badge">removed</span>}
                  </div>
                </div>
                <div className="ed-tools">
                  {edited && <button type="button" className="link-btn" onClick={() => setLine(l.i, l.orig)}>
                    {removed ? 'Restore' : 'Reset'}
                  </button>}
                  {!removed && <button type="button" className="link-btn" onClick={() => setLine(l.i, '')}>Remove</button>}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="ed-foot">
        <div className="ed-status" role="status">
          {error ? <span style={{ color: 'var(--bad)' }}>{error}</span>
            : totalChanges > 0 ? `${totalChanges} ${totalChanges === 1 ? 'change' : 'changes'} to save`
              : 'No changes yet'}
        </div>
        {onCancel && <button className="btn" type="button" onClick={onCancel} disabled={busy}>Cancel</button>}
        <button className="btn primary ed-go" type="button" onClick={submit} disabled={busy}>{submitLabel}</button>
      </div>
    </section>
  )
}
