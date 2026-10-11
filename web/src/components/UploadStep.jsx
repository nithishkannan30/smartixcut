import { useEffect, useMemo, useRef, useState } from 'react'
import { fmtSize, fmtTime } from '../format'

// Step 1: drop a video or browse. Shows a small preview once chosen.
export default function UploadStep({ file, onFile, onClear, limits, onReject }) {
  const input = useRef(null)
  const [over, setOver] = useState(false)
  const [meta, setMeta] = useState({ file: null, duration: null })
  const duration = meta.file === file ? meta.duration : null
  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file])

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])

  function accept(f) {
    if (!f) return
    const ext = (f.name.split('.').pop() || '').toLowerCase()
    if (!['mp4', 'mov', 'm4v'].includes(ext)) return onReject('Please choose an MP4 or MOV video.')
    if (f.size > limits.maxBytes) return onReject(`That file is larger than ${limits.maxGb} GB.`)
    onFile(f)
  }

  return (
    <>
      {!file && (
        <label
          className={`drop${over ? ' over' : ''}`}
          htmlFor="fileInput"
          onDragEnter={(e) => { e.preventDefault(); setOver(true) }}
          onDragOver={(e) => { e.preventDefault(); setOver(true) }}
          onDragLeave={(e) => { e.preventDefault(); setOver(false) }}
          onDrop={(e) => { e.preventDefault(); setOver(false); accept(e.dataTransfer.files[0]) }}
        >
          <div className="ico">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="3" y="5" width="18" height="14" rx="3" /><path d="M10 9.5v5l4.2-2.5z" fill="currentColor" />
            </svg>
          </div>
          <div><b>Drop a video here, or <a>browse files</a></b></div>
          <div className="hint">MP4 or MOV, up to {limits.maxGb} GB and {limits.maxMin} minutes</div>
        </label>
      )}
      <input
        ref={input}
        id="fileInput"
        type="file"
        className="hidden"
        accept=".mp4,.mov,.m4v,video/mp4,video/quicktime"
        onChange={(e) => { accept(e.target.files[0]); e.target.value = '' }}
      />

      {file && (
        <div className="file">
          <video src={previewUrl} muted playsInline preload="metadata"
            onLoadedMetadata={(e) => setMeta({ file, duration: e.currentTarget.duration })} />
          <div>
            <div className="name">{file.name}</div>
            <div className="meta">{fmtSize(file.size)}{duration ? ` · ${fmtTime(duration)}` : ''}</div>
          </div>
          <button className="btn small" type="button" onClick={onClear}>Change</button>
        </div>
      )}

      <div className="note">Your video is used only to make your clips. Originals are deleted after a few days.</div>
    </>
  )
}
