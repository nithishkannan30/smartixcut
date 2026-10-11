import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// While you work, `npm run dev` serves the app on :5173 and forwards every /api call to
// the Python server on :8000. The browser thinks it is all one site, so the login cookie just works.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
})
