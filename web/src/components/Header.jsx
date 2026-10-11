import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import Logo from './Logo'

export default function Header() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function onLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <header className="top">
      <Link to="/" className="logo"><Logo /> SmartixCut</Link>
      <div className="spacer" />
      <Link to="/#history" className="link-btn" onClick={() => document.getElementById('history')?.scrollIntoView({ behavior: 'smooth' })}>
        My clips
      </Link>
      <span className="who" title={user?.email}>{user?.name}</span>
      <button className="link-btn" type="button" onClick={onLogout}>Log out</button>
    </header>
  )
}
