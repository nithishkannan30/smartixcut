import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './useAuth'

// Wrap a page in this and only logged-in people can see it.
export default function RequireAuth({ children }) {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <div className="boot" role="status">Loading…</div>
  if (status === 'out') return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}
