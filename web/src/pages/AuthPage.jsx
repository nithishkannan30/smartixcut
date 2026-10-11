import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import Logo from '../components/Logo'
import PhonePreview from '../components/PhonePreview'

const SHOWCASE = { enabled: true, style: 'karaoke', size: 'large', position: 'bottom',
                   color: '#FFFFFF', highlight: '#FFE600', uppercase: false }
const EMAIL_OK = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/

// One component for both screens: <AuthPage mode="login" /> and <AuthPage mode="signup" />.
export default function AuthPage({ mode }) {
  const signingUp = mode === 'signup'
  const { status, notice, login, signup } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (status === 'in') return <Navigate to="/" replace />

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (signingUp && !name.trim()) return setError('Enter your name.')
    if (!EMAIL_OK.test(email.trim())) return setError('Enter a valid email address.')
    if (signingUp && password.length < 8) return setError('Password must be at least 8 characters.')
    if (!password) return setError('Enter your password.')

    setBusy(true)
    try {
      if (signingUp) await signup(name.trim(), email.trim(), password)
      else await login(email.trim(), password)
      navigate(location.state?.from || '/', { replace: true })
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <div className="auth-pitch">
        <div className="logo"><Logo /> SmartixCut</div>
        <h1>Smart AI video clips in 60&nbsp;seconds</h1>
        <p className="sub">Upload a long video and get captioned vertical clips for Reels, Shorts and TikTok in Tamil, Hindi, Marathi or English.</p>
        <div className="auth-phone"><PhonePreview cap={SHOWCASE} language="ta" /></div>
      </div>

      <form className="panel auth-card" onSubmit={submit} noValidate>
        <h2>{signingUp ? 'Create your account' : 'Welcome back'}</h2>
        <p className="muted" style={{ margin: '6px 0 0' }}>
          {signingUp ? 'Make your first clips in about a minute.' : 'Log in to see your clips.'}
        </p>

        {notice && !error && <div className="banner" role="status">{notice}</div>}

        {signingUp && (
          <div className="field">
            <label htmlFor="name">Your name</label>
            <input id="name" value={name} autoComplete="name" autoFocus maxLength={60}
              onChange={(e) => setName(e.target.value)} />
          </div>
        )}
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" value={email} autoComplete="email" inputMode="email" autoFocus={!signingUp}
            onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <div className="pw">
            <input id="password" type={showPw ? 'text' : 'password'} value={password}
              autoComplete={signingUp ? 'new-password' : 'current-password'} maxLength={128}
              aria-describedby={signingUp ? 'pw-hint' : undefined}
              onChange={(e) => setPassword(e.target.value)} />
            <button type="button" className="link-btn" onClick={() => setShowPw((s) => !s)} aria-pressed={showPw}>
              {showPw ? 'Hide' : 'Show'}
            </button>
          </div>
          {signingUp && <div id="pw-hint" className="hint">At least 8 characters.</div>}
        </div>

        <div className="form-error" role="alert" aria-live="polite">{error}</div>

        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? (signingUp ? 'Creating account…' : 'Logging in…') : (signingUp ? 'Create account' : 'Log in')}
        </button>

        <p className="switch-auth">
          {signingUp
            ? <>Already have an account? <Link to="/login" state={location.state}>Log in</Link></>
            : <>New here? <Link to="/signup" state={location.state}>Create an account</Link></>}
        </p>
      </form>
    </div>
  )
}
