import { useEffect, useRef, useState } from 'react'
import { api, post } from '../api'
import { fmtTime } from '../format'
import CaptionStudio from './CaptionStudio'

// The editor behind the "Edit" button on a finished clip. The user can
//   - trim where the clip starts and ends,
//   - fix the caption text (and play any line to check it),
//   - restyle the captions for this clip,
//   - change the title and hashtags.
// "Save and render" makes that one clip again; the other clips are not touched.
// The server saves everything, so we only send what changed.

const MIN_LEN = 3          // seconds; the server enforces the same limits
const MAX_LEN = 90

const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi)
const round1 = (v) => Math.round(v * 10) / 10
const tagList = (s) => s.split(/[\s,]+/).filter(Boolean)
const secs = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`

// A caption is one line of text, so Enter jumps to the next caption instead of adding a line break.
function nextOnEnter(e) {
  if (e.key !== 'Enter') return
  e.preventDefault()
  e.currentTarget.closest('.ed-line')?.nextElementSibling?.querySelector('textarea')?.focus()
}
const rowsFor = (text) => Math.min(4, Math.max(1, Math.ceil(text.length / 40)))

export default function ClipEditor({ jobId, clipN, onSubmitted, onCancel, onNew }) {
  const [data, setData] = useState(null)
  const [problem, setProblem] = useState('')

  useEffect(() => {
    let stopped = false
    api(`/api/jobs/${jobId}/clips/${clipN}/editor`)
      .then((d) => { if (!stopped) setData(d) })
      .catch((e) => { if (!stopped) setProblem(e.message) })
    return () => { stopped = true }
  }, [jobId, clipN])

  if (problem) {
    return (
      <section className="panel">
        <h2>We can't open the editor</h2>
        <div className="err">{problem}</div>
        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn" type="button" onClick={onCancel}>Back to my clips</button>
          <button className="btn" type="button" onClick={onNew}>New video</button>
        </div>
      </section>
    )
  }
  if (!data) return <div className="boot" role="status">Opening the editor…</div>
  return <EditorBody jobId={jobId} data={data} onSubmitted={onSubmitted} onCancel={onCancel} />
}

function EditorBody({ jobId, data, onSubmitted, onCancel }) {
  const { clip, bounds: [lo, hi] } = data
  const lang = data.language

  const [start, setStart] = useState(clip.start)
  const [end, setEnd] = useState(clip.end)
  const [drafts, setDrafts] = useState(() => Object.fromEntries(data.lines.map((l) => [l.i, l.text])))
  const [title, setTitle] = useState(clip.title)
  const [tags, setTags] = useState((clip.hashtags || []).join(' '))
  const [caps, setCaps] = useState(data.captions)
  const [tab, setTab] = useState('text')
  const [nowI, setNowI] = useState(-1)                 // the line being spoken right now
  const [noVideo, setNoVideo] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const videoRef = useRef(null)

  // ---- what changed ----
  const tagsText = (clip.hashtags || []).join(' ')
  const trimChanged = start !== clip.start || end !== clip.end
  const styleChanged = Object.keys(caps).some((k) => caps[k] !== data.captions[k])
  const changedLines = data.lines.filter((l) => drafts[l.i] !== l.text)
  const changes = changedLines.length + (trimChanged ? 1 : 0) + (styleChanged ? 1 : 0)
    + (title !== clip.title ? 1 : 0) + (tags !== tagsText ? 1 : 0)

  // only the lines inside the current cut are shown
  const shown = data.lines.filter((l) => l.end > start && l.start < end)

  // ---- trimming ----
  function seek(t) {
    if (videoRef.current) videoRef.current.currentTime = t
  }
  function setRange(s, e, moved) {
    s = clamp(s, lo, hi)
    e = clamp(e, lo, hi)
    if (e - s < MIN_LEN) {
      if (moved === 'start') s = Math.max(lo, e - MIN_LEN)
      else e = Math.min(hi, s + MIN_LEN)
    }
    if (e - s > MAX_LEN) {
      if (moved === 'start') e = s + MAX_LEN
      else s = e - MAX_LEN
    }
    setStart(round1(s))
    setEnd(round1(e))
    seek(moved === 'start' ? s : Math.max(s, e - 1.5))
  }
  function fromPlayer(which) {
    const t = videoRef.current?.currentTime
    if (t == null) return
    if (which === 'start') setRange(t, end, 'start')
    else setRange(start, t, 'end')
  }
  const span = Math.max(0.1, hi - lo)
  const barLeft = `${((start - lo) / span) * 100}%`
  const barWidth = `${((end - start) / span) * 100}%`

  // ---- playback ----
  function onTime(e) {
    const v = e.currentTarget
    const cur = shown.find((l) => v.currentTime >= l.start && v.currentTime < l.end)
    setNowI(cur ? cur.i : -1)
    if (v.currentTime >= end) v.pause()                // stay inside the cut
  }
  function playFrom(t) {
    const v = videoRef.current
    if (!v) return
    v.currentTime = t
    v.play().catch(() => {})
  }

  // ---- saving ----
  async function submit() {
    setBusy(true); setError('')
    const body = {
      ...(title !== clip.title ? { title } : {}),
      ...(tags !== tagsText ? { hashtags: tagList(tags) } : {}),
      ...(trimChanged ? { start, end } : {}),
      ...(styleChanged ? { captions: caps } : {}),
      lines: changedLines.map((l) => ({ i: l.i, text: drafts[l.i] })),
    }
    try {
      await post(`/api/jobs/${jobId}/clips/${clip.n}/edit`, body)
      onSubmitted()
    } catch (e) {
      setBusy(false)
      setError(e.message)
    }
  }

  const setLine = (i, text) => setDrafts((d) => ({ ...d, [i]: text }))

  return (
    <section className="panel editor">
      <div className="row">
        <div>
          <h2>Edit clip {clip.n}</h2>
          <p className="muted ed-sub">
            Trim it, fix the captions or change how they look, then save. Only this clip is made again, and you can
            download it as soon as it's ready.
          </p>
        </div>
      </div>

      <div className="ed-grid">
        <div className="ed-side">
          {noVideo ? (
            <div className="note">We can't play the original video here, but trimming and text editing still work.</div>
          ) : (
            <video ref={videoRef} controls playsInline preload="metadata"
              src={`/api/jobs/${jobId}/source#t=${clip.start},${clip.end}`}
              onTimeUpdate={onTime} onError={() => setNoVideo(true)} />
          )}
          <button type="button" className="btn small" style={{ marginTop: 10, width: '100%' }}
            disabled={noVideo} onClick={() => playFrom(start)}>▶ Play this cut</button>

          <div className="trim">
            <div className="label" style={{ marginTop: 18 }}>Trim</div>
            <div className="trim-bar" aria-hidden="true"><i style={{ left: barLeft, width: barWidth }} /></div>
            <div className="trim-row">
              <label htmlFor="trim-start">Start <b>{secs(start)}</b></label>
              <button type="button" className="link-btn" disabled={noVideo} onClick={() => fromPlayer('start')}>Use current time</button>
            </div>
            <input id="trim-start" type="range" min={lo} max={hi} step="0.1" value={start}
              onChange={(e) => setRange(Number(e.target.value), end, 'start')} />
            <div className="trim-row">
              <label htmlFor="trim-end">End <b>{secs(end)}</b></label>
              <button type="button" className="link-btn" disabled={noVideo} onClick={() => fromPlayer('end')}>Use current time</button>
            </div>
            <input id="trim-end" type="range" min={lo} max={hi} step="0.1" value={end}
              onChange={(e) => setRange(start, Number(e.target.value), 'end')} />
            <div className="muted">
              Length {(end - start).toFixed(1)}s
              {trimChanged && (
                <> · <button type="button" className="link-btn" style={{ padding: 0 }}
                  onClick={() => { setStart(clip.start); setEnd(clip.end); seek(clip.start) }}>Reset trim</button></>
              )}
            </div>
          </div>

          <div className="field">
            <label htmlFor="ed-title">Title</label>
            <input id="ed-title" type="text" lang={lang} maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="ed-tags">Hashtags</label>
            <input id="ed-tags" type="text" lang={lang} value={tags} placeholder="#reels #shorts" onChange={(e) => setTags(e.target.value)} />
          </div>
        </div>

        <div className="ed-main">
          <div className="tabs" role="tablist" aria-label="What to edit">
            <button type="button" role="tab" aria-selected={tab === 'text'} className={`tab${tab === 'text' ? ' on' : ''}`}
              onClick={() => setTab('text')}>Caption text</button>
            <button type="button" role="tab" aria-selected={tab === 'style'} className={`tab${tab === 'style' ? ' on' : ''}`}
              onClick={() => setTab('style')}>Caption style{styleChanged && <span className="badge ok">edited</span>}</button>
          </div>

          {tab === 'style' ? (
            <div className="ed-style">
              <p className="muted" style={{ margin: '14px 0 4px' }}>
                This changes the look for clip {clip.n} only. Your other clips keep their style.
              </p>
              <CaptionStudio value={caps} onChange={setCaps} language={lang} />
            </div>
          ) : (
            <div className="ed-lines">
              {shown.length === 0 && <div className="muted">There are no spoken lines in this cut.</div>}
              {shown.map((l) => {
                const text = drafts[l.i] ?? ''
                const removed = text.trim() === ''
                const edited = text !== l.orig
                const unclear = l.low_conf && !edited
                const cls = ['ed-line', l.i === nowI ? 'now' : '', unclear ? 'low' : '', removed ? 'removed' : ''].join(' ').trim()
                return (
                  <div key={l.i} className={cls}>
                    <button type="button" className="ed-time" onClick={() => playFrom(Math.max(l.start, start))} disabled={noVideo}
                      aria-label={`Play line at ${fmtTime(l.start)}`}>
                      <span aria-hidden="true">▶</span> {fmtTime(l.start)}
                    </button>
                    <div>
                      <textarea lang={lang} rows={rowsFor(text)} value={text} aria-label={`Caption at ${fmtTime(l.start)}`}
                        placeholder="Removed. Type to bring it back." onKeyDown={nextOnEnter}
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
          )}
        </div>
      </div>

      <div className="ed-foot">
        <div className="ed-status" role="status">
          {error ? <span style={{ color: 'var(--bad)' }}>{error}</span>
            : changes > 0 ? `${changes} ${changes === 1 ? 'change' : 'changes'} to save` : 'No changes yet'}
        </div>
        <button className="btn" type="button" onClick={onCancel} disabled={busy}>Cancel</button>
        <button className="btn primary ed-go" type="button" onClick={submit} disabled={busy || changes === 0}>
          {busy ? 'Starting…' : `Save and render clip ${clip.n}`}
        </button>
      </div>
    </section>
  )
}