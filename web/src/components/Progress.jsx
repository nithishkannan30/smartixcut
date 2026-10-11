import { useEffect, useRef, useState } from 'react'
import { fmtTime } from '../format'

const STEPS = [
  ['uploading', 'Uploading your video'],
  ['transcribing', 'Listening and transcribing'],
  ['finding_moments', 'Finding the best moments'],
  ['rendering', 'Cutting vertical clips with captions'],
]
// How far the bar is allowed to creep inside each stage while we wait for the server.
const CEILING = { uploading: 15, uploaded: 15, transcribing: 66, finding_moments: 80, rendering: 98 }

// Shows the 4 stages, a bar and the elapsed time. `status` is the job status, or 'uploading'.
export default function Progress({ status, serverProgress = 0, startedAt, title, note }) {
  const [creep, setCreep] = useState(2)
  const [now, setNow] = useState(() => Date.now())
  const latest = useRef(serverProgress)
  useEffect(() => { latest.current = serverProgress })

  // The server only tells us a few milestones, so the bar creeps forward between them.
  useEffect(() => {
    const id = setInterval(() => {
      setNow(Date.now())
      setCreep((c) => {
        const base = Math.max(c, latest.current)
        return base < (CEILING[status] || 15) - 1 ? base + 0.35 : base
      })
    }, 500)
    return () => clearInterval(id)
  }, [status])
  const shown = Math.max(creep, serverProgress)

  const idx = status === 'uploaded' ? 1 : STEPS.findIndex((s) => s[0] === status)

  return (
    <section className="panel" aria-live="polite">
      <h2>{title || (status === 'uploaded' ? 'Waiting for a free worker…' : 'Making your clips…')}</h2>
      <div className="bar"><i style={{ width: `${Math.min(100, shown)}%` }} /></div>
      <ul className="steps">
        {STEPS.map(([id, label], i) => {
          const cls = i < idx ? 'done' : i === idx ? 'active' : ''
          return (
            <li key={id} className={cls}>
              <span className="dot">{cls === 'done' ? '✓' : cls === 'active' ? <span className="spin" /> : i + 1}</span>
              {label}
            </li>
          )
        })}
      </ul>
      <div className="muted" style={{ marginTop: 14 }}>
        {note || (startedAt ? `Elapsed ${fmtTime((now - startedAt) / 1000)}` : '')}
      </div>
    </section>
  )
}
