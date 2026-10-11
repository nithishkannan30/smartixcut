export default function Switch({ checked, onChange, children }) {
  return (
    <label className="switch">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" />
      {children}
    </label>
  )
}
