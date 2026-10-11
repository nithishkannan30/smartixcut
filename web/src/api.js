// Every call to the Python server goes through here, so errors and "you were logged out"
// are handled in one place.

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

function errorText(data, status) {
  if (data && typeof data.detail === 'string') return data.detail
  if (data && Array.isArray(data.detail) && data.detail[0]) {
    const d = data.detail[0]
    const field = (d.loc || []).join('.')
    if (field.includes('password')) return 'Password must be at least 8 characters.'
    if (field.includes('email')) return 'Enter a valid email address.'
    if (field.includes('name')) return 'Enter your name.'
    return d.msg || 'Invalid request.'
  }
  return `Something went wrong (${status}). Please try again.`
}

function handle(status, path, data) {
  if (status >= 200 && status < 300) return data
  if (status === 401 && !path.startsWith('/api/auth/')) {
    window.dispatchEvent(new Event('smartix:unauthorized'))   // AuthContext sends the user to /login
  }
  throw new ApiError(errorText(data, status), status)
}

export async function api(path, options = {}) {
  let res
  try {
    res = await fetch(path, { credentials: 'same-origin', ...options })
  } catch {
    throw new ApiError("Couldn't reach the server. Is it running?", 0)
  }
  const data = await res.json().catch(() => null)
  return handle(res.status, path, data)
}

export function post(path, body) {
  return api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// fetch can't report upload progress, so uploads use XMLHttpRequest.
export function uploadVideo(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/uploads')
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total)
    }
    xhr.onload = () => {
      let data = null
      try { data = JSON.parse(xhr.responseText) } catch { /* not json */ }
      try { resolve(handle(xhr.status, '/api/uploads', data)) } catch (e) { reject(e) }
    }
    xhr.onerror = () => reject(new ApiError("Couldn't reach the server. Is it running?", 0))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}
