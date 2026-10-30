import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { localBackendEnabled, startLocalBackend } from './localApi'

/** Demo build only: start the in-browser Python backend before the app makes its first API call. */
function Boot() {
  const [status, setStatus] = useState('Starting…')
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    startLocalBackend(setStatus)
      .then(() => setReady(true))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  if (ready) return <App />
  return (
    <div className="grid min-h-screen place-items-center px-4 text-center">
      <div>
        <div className="mx-auto mb-4 size-8 animate-spin rounded-full border-2 border-line border-t-accent" />
        <p className="font-medium">{error ? 'Couldn’t start EcoTrack' : status}</p>
        <p className="mt-1 text-sm text-ink-2">
          {error ?? 'First visit downloads the engine (about 15 MB); later visits are faster.'}
        </p>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>{localBackendEnabled ? <Boot /> : <App />}</StrictMode>,
)
