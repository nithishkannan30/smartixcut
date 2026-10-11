// Shown when something goes wrong. `detail` is the raw log tail, only visible with ?dev in the address.
export default function FailureCard({ message, detail, onRetry, onNew }) {
  const dev = new URLSearchParams(window.location.search).has('dev')
  return (
    <section className="panel" role="alert">
      <h2>That didn't work</h2>
      <div className="err">
        <div>{message || 'Something went wrong.'}</div>
        {dev && detail && <pre>{detail}</pre>}
      </div>
      <div style={{ marginTop: 16, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {onRetry && <button className="btn" type="button" onClick={onRetry}>Try again</button>}
        <button className="btn" type="button" onClick={onNew}>Start over</button>
      </div>
    </section>
  )
}
