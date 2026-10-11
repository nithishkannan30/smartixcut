import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, post } from '../api'
import { AuthContext } from './context'

// Holds "who is logged in" for the whole app.
// status: 'loading' (asking the server), 'in', or 'out'.

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [status, setStatus] = useState('loading')
  const [notice, setNotice] = useState('')

  // On first load, ask the server if the cookie is still good.
  useEffect(() => {
    api('/api/auth/me')
      .then((u) => { setUser(u); setStatus('in') })
      .catch(() => { setUser(null); setStatus('out') })
  }, [])

  // api.js shouts this when any call comes back 401 (session expired).
  useEffect(() => {
    const onExpired = () => {
      setUser(null)
      setStatus('out')
      setNotice('Your session expired. Log in again to continue.')
    }
    window.addEventListener('smartix:unauthorized', onExpired)
    return () => window.removeEventListener('smartix:unauthorized', onExpired)
  }, [])

  const login = useCallback(async (email, password) => {
    const u = await post('/api/auth/login', { email, password })
    setUser(u); setStatus('in'); setNotice('')
    return u
  }, [])

  const signup = useCallback(async (name, email, password) => {
    const u = await post('/api/auth/signup', { name, email, password })
    setUser(u); setStatus('in'); setNotice('')
    return u
  }, [])

  const logout = useCallback(async () => {
    try { await post('/api/auth/logout', {}) } catch { /* cookie may already be gone */ }
    setUser(null); setStatus('out'); setNotice('')
  }, [])

  const value = useMemo(
    () => ({ user, status, notice, login, signup, logout }),
    [user, status, notice, login, signup, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
