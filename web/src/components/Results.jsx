import ClipCard from './ClipCard'

export default function Results({ job, onNew }) {
  const n = job.clips.length
  const dev = new URLSearchParams(window.location.search).has('dev')
  const stages = job.stage_seconds || {}
  return (
    <section className="panel">
      <div className="row">
        <div>
          <h2>{n} {n === 1 ? 'clip' : 'clips'} ready</h2>
          <div className="muted">
            {job.video_name}{job.total_seconds ? ` · made in ${Math.round(job.total_seconds)}s` : ''}
          </div>
        </div>
        <button className="btn" type="button" onClick={onNew}>New video</button>
      </div>
      <div className="clips">
        {job.clips.map((c) => <ClipCard key={c.n} clip={c} />)}
      </div>
      {dev && (
        <div className="dev">
          stages: {Object.keys(stages).map((k) => `${k} ${stages[k]}s`).join(' · ')}
          {job.cost_usd != null ? ` · API cost ≈ $${job.cost_usd.toFixed(4)} (₹${job.cost_inr})` : ''}
        </div>
      )}
    </section>
  )
}
