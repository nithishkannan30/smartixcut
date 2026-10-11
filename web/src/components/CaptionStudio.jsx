import { CAPTION_STYLES, COLORS, HIGHLIGHT_COLORS } from '../captionConfig'
import Choice from './Choice'
import PhonePreview from './PhonePreview'
import Swatches from './Swatches'
import Switch from './Switch'

function StyleTile({ style, on, onClick }) {
  const sample = style.id === 'karaoke'
    ? (<><span>Go</span><span>now</span></>)
    : <span>Go now</span>
  return (
    <button type="button" className={`tile${on ? ' on' : ''}`} aria-pressed={on} onClick={onClick}>
      <div className={`sample ${style.id}`}>{sample}</div>
      <b>{style.label}</b>
      <small>{style.hint}</small>
    </button>
  )
}

// Step 3: the controls on the left, the live phone on the right.
export default function CaptionStudio({ value: cap, onChange, language }) {
  const set = (key) => (v) => onChange({ ...cap, [key]: v })

  return (
    <div className="studio">
      <div className={`controls${cap.enabled ? '' : ' off'}`}>
        <Switch checked={cap.enabled} onChange={set('enabled')}>Burn captions into the video</Switch>

        <div className="when-on">
          <div className="label">Look</div>
          <div className="style-tiles">
            {CAPTION_STYLES.map((s) => (
              <StyleTile key={s.id} style={s} on={cap.style === s.id} onClick={() => set('style')(s.id)} />
            ))}
          </div>

          <div className="label">Size</div>
          <Choice tight label="Size" value={cap.size} onChange={set('size')}
            items={[['small', 'Small'], ['medium', 'Medium'], ['large', 'Large']]} />

          <div className="label">Position</div>
          <Choice tight label="Position" value={cap.position} onChange={set('position')}
            items={[['top', 'Top'], ['middle', 'Middle'], ['bottom', 'Bottom']]} />

          <div className="label">Text colour</div>
          <Swatches label="Text colour" colors={COLORS} value={cap.color} onChange={set('color')} />

          {cap.style === 'karaoke' && (
            <>
              <div className="label">Highlight colour</div>
              <Swatches label="Highlight colour" colors={HIGHLIGHT_COLORS} value={cap.highlight} onChange={set('highlight')} />
            </>
          )}

          <div className="switches">
            <Switch checked={cap.uppercase} onChange={set('uppercase')}>UPPERCASE English</Switch>
          </div>
        </div>
      </div>

      <PhonePreview cap={cap} language={language} note="Preview. Your clips use this style." />
    </div>
  )
}
