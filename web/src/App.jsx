import { Navigate, Route, Routes } from 'react-router-dom'
import RequireAuth from './auth/RequireAuth'
import Aurora from './components/Aurora'
import Header from './components/Header'
import Studio from './pages/Studio'
import JobPage from './pages/JobPage'
import AuthPage from './pages/AuthPage'

// Pages:
//   /login, /signup   open to everyone
//   /                 the builder (upload, brief, captions, format) + your history
//   /jobs/:id         one job: progress, then the finished clips. Survives a refresh.
export default function App() {
  return (
    <>
      <Aurora />
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/signup" element={<AuthPage mode="signup" />} />
        <Route
          path="/*"
          element={
            <RequireAuth>
              <Header />
              <main className="wrap">
                <Routes>
                  <Route index element={<Studio />} />
                  <Route path="jobs/:jobId" element={<JobPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </main>
              <footer>SmartixCut · AI clips for Indian creators</footer>
            </RequireAuth>
          }
        />
      </Routes>
    </>
  )
}
