// Colour dots + a custom colour picker.
export default function Swatches({ colors, value, onChange, label }) {
  const current = value.toUpperCase()
  return (
    <div className="swatches" role="group" aria-label={label}>
      {colors.map((c) => (
        <button
          key={c}
          type="button"
          className={`sw${current === c ? ' on' : ''}`}
          style={{ background: c }}
          aria-label={c}
          aria-pressed={current === c}
          onClick={() => onChange(c)}
        />
      ))}
      <input
        type="color"
        className="picker"
        value={current.toLowerCase()}
        aria-label={`Custom ${label.toLowerCase()}`}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
      />
    </div>
  )
}
