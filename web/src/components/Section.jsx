// One numbered block of the builder.
export default function Section({ num, title, aside, children }) {
  return (
    <div className="section">
      <div className="sec-head">
        <span className="num">{num}</span>
        <h2>{title}</h2>
        {aside}
      </div>
      {children}
    </div>
  )
}
