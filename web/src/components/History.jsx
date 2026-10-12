import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

const LABEL = { done: (j) => `${j.clips.length} clips`, failed: () => 'failed' }

export default function History({ paused }) {
  const [jobs, setJobs] = useState(null)
  const navigate = useNavigate()

  const load = useCallback(() => {
    api('/api/jobs?limit=12').then((d) => setJobs(d.jobs)).catch(() => {})
  }, [])

  useEffect(() => {
    load()
    if (paused) return undefined
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [load, paused])

  async function remove(e, job) {
    e.stopPropagation()
    if (!window.confirm('Delete these clips?')) return
    try { await api(`/api/jobs/${job.id}`, { method: 'DELETE' }); load() } catch (err) { window.alert(err.message) }
  }

  return (
    <section className="panel" id="history">
      <h2>Your recent clips</h2>
      <div className="jobs">
        {jobs === null && <div className="muted">Loading…</div>}
        {jobs && jobs.length === 0 && <div className="muted">Nothing yet. Your finished clips will show up here.</div>}
        {jobs && jobs.map((j) => {
          const cls = j.status === 'done' ? 'done' : j.status === 'failed' ? 'failed' : 'run'
          const label = (LABEL[j.status] || (() => 'working'))(j)
          const when = new Date(j.created_at * 1000).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
          const finished = j.status === 'done' || j.status === 'failed'
          return (
            <div key={j.id} style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
              <button className="job" type="button" style={{ flex: 1 }} onClick={() => navigate(`/jobs/${j.id}`)}>
                <div className="t">
                  <b>{j.video_name || 'Video'}</b>
                  <span className="muted">{when}{j.prompt ? ` · ${j.prompt}` : ''}</span>
                </div>
                <span className={`st ${cls}`}>{label}</span>
              </button>
              {finished && (
                <button className="btn small danger" type="button" aria-label="Delete this job" onClick={(e) => remove(e, j)}>Delete</button>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}