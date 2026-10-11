export function fmtSize(bytes) {
  return bytes > 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : `${(bytes / 1e6).toFixed(1)} MB`
}

export function fmtTime(seconds) {
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

// Cloudinary links open in the browser instead of downloading unless they carry the attachment flag.
export function attachmentUrl(url, n) {
  const m = /^(https?:\/\/res\.cloudinary\.com\/.+?\/video\/upload\/)(.+)$/.exec(url || '')
  return m ? `${m[1]}fl_attachment:smartixcut_clip_${n}/${m[2]}` : url
}
