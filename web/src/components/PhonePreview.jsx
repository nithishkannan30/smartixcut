import { useEffect, useState } from 'react'
import { POSITION_OFFSET, SAMPLE_TEXT, SIZE_PX } from '../captionConfig'
import useReducedMotion from './useReducedMotion'

// A little phone that shows what the captions will look like.
// In "Word highlight" mode the words light up one by one, like the real clip.
export default function PhonePreview({ cap, language = 'en', note }) {
  const reduced = useReducedMotion()
  const [tick, setTick] = useState(0)
  const karaoke = cap.enabled && cap.style === 'karaoke'

  useEffect(() => {
    if (!karaoke || reduced) return undefined
    const id = setInterval(() => setTick((t) => t + 1), 420)
    return () => clearInterval(id)
  }, [karaoke, reduced])

  let text = SAMPLE_TEXT[language] || SAMPLE_TEXT.en
  if (cap.uppercase) text = text.toUpperCase()
  const words = text.split(' ')
  const lit = karaoke ? (reduced ? 2 : tick % (words.length + 2)) : -1

  const box = {
    fontSize: `calc(${SIZE_PX[cap.size]} / 1080 * 100cqw)`,
    color: cap.color,
    ...(cap.position === 'middle'
      ? { top: '50%', transform: 'translateY(-50%)' }
      : cap.position === 'top'
        ? { top: POSITION_OFFSET.top }
        : { bottom: POSITION_OFFSET.bottom }),
  }

  return (
    <div className="phone-col">
      <div className="phone">
        {cap.enabled && (
          <div className={`cap ${cap.style}`} style={box}>
            {words.map((w, i) => (
              <span key={i}>
                <span className="w" style={i < lit ? { color: cap.highlight } : undefined}>{w}</span>
                {i < words.length - 1 ? ' ' : ''}
              </span>
            ))}
          </div>
        )}
      </div>
      {note && <div className="phone-note">{note}</div>}
    </div>
  )
}
