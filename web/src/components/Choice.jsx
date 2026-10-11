// A row of buttons where exactly one is selected (language, platform, size...).
// items: [[id, label, smallText?], ...]  or plain values like [3, 5]
export default function Choice({ items, value, onChange, label, tight = false, style }) {
  return (
    <div className={`opts${tight ? ' tight' : ''}`} role="group" aria-label={label} style={style}>
      {items.map((item) => {
        const [id, text, small] = Array.isArray(item) ? item : [item, `${item} clips`]
        const on = value === id
        return (
          <button
            key={id}
            type="button"
            className={`opt${on ? ' on' : ''}`}
            aria-pressed={on}
            onClick={() => onChange(id)}
          >
            <span>{text}</span>
            {small && <small>{small}</small>}
          </button>
        )
      })}
    </div>
  )
}
