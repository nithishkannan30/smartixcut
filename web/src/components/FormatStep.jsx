import { PLATFORMS, QUALITIES } from '../captionConfig'
import Choice from './Choice'

// Step 4: which app the clip is for, and how sharp it should be.
export default function FormatStep({ platform, onPlatform, quality, onQuality }) {
  return (
    <>
      <Choice label="Platform" items={PLATFORMS} value={platform} onChange={onPlatform} />
      <div className="label">Video quality</div>
      <Choice label="Video quality" items={QUALITIES} value={quality} onChange={onQuality} style={{ maxWidth: 420 }} />
    </>
  )
}
