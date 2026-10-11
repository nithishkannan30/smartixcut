import { BRIEF_CHIPS, COUNTS, LANGUAGES } from '../captionConfig'
import Choice from './Choice'

// Step 2: what the clips should be about, plus language and how many.
export default function BriefStep({ prompt, onPrompt, language, onLanguage, count, onCount }) {
  function toggleChip(chip) {
    const low = prompt.toLowerCase()
    const i = low.indexOf(chip.toLowerCase())
    if (i !== -1) {
      onPrompt((prompt.slice(0, i) + prompt.slice(i + chip.length))
        .replace(/^[,\s]+|[,\s]+$/g, '').replace(/\s*,\s*,/g, ','))
    } else {
      onPrompt(prompt.trim() ? `${prompt.trim().replace(/[,.\s]+$/, '')}, ${chip.toLowerCase()}` : chip)
    }
  }

  return (
    <>
      <textarea
        value={prompt}
        maxLength={600}
        placeholder="e.g. Best hooks and motivating moments for Reels. Skip the intro."
        aria-label="What clips do you want?"
        onChange={(e) => onPrompt(e.target.value)}
      />
      <div className="chips">
        {BRIEF_CHIPS.map((chip) => {
          const on = prompt.toLowerCase().includes(chip.toLowerCase())
          return (
            <button key={chip} type="button" className={`chip${on ? ' on' : ''}`} aria-pressed={on} onClick={() => toggleChip(chip)}>
              {chip}
            </button>
          )
        })}
      </div>
      <div className="label">Language spoken in the video</div>
      <Choice label="Language" items={LANGUAGES} value={language} onChange={onLanguage} />
      <div className="label">Number of clips</div>
      <Choice label="Number of clips" items={COUNTS} value={count} onChange={onCount} style={{ maxWidth: 260 }} />
    </>
  )
}
