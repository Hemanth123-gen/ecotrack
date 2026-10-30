import { useState } from 'react'
import { signInWithGoogle } from '../auth'
import { Leaf } from './Onboarding'

export function SignIn({ error, onRetry }: { error: string | null; onRetry: () => void }) {
  const [busy, setBusy] = useState(false)
  const [popupError, setPopupError] = useState<string | null>(null)

  async function signIn() {
    setBusy(true)
    setPopupError(null)
    try {
      await signInWithGoogle()
    } catch (e) {
      const code = (e as { code?: string }).code
      if (code !== 'auth/popup-closed-by-user' && code !== 'auth/cancelled-popup-request') {
        setPopupError(e instanceof Error ? e.message : 'Sign-in failed')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen grid place-items-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-8 shadow-sm">
        <div className="flex items-center gap-2 text-accent">
          <Leaf />
          <span className="font-semibold tracking-tight">EcoTrack</span>
        </div>
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">Understand and shrink your carbon footprint</h1>
        <p className="mt-2 text-sm text-ink-2">
          Sign in to keep your footprint, goals and chat history private to your account.
        </p>

        {error ? (
          <>
            <p className="mt-6 text-sm text-critical">Couldn't load your profile: {error}</p>
            <button onClick={onRetry} className="mt-3 w-full rounded-lg border border-line px-4 py-2.5 font-medium hover:bg-surface-2">
              Sign out and try again
            </button>
          </>
        ) : (
          <button
            onClick={signIn}
            disabled={busy}
            className="mt-6 flex w-full items-center justify-center gap-3 rounded-lg border border-line bg-page px-4 py-2.5 font-medium hover:bg-surface-2 disabled:opacity-50"
          >
            <GoogleMark />
            {busy ? 'Signing in…' : 'Continue with Google'}
          </button>
        )}
        {popupError && <p className="mt-3 text-sm text-critical">{popupError}</p>}
      </div>
    </div>
  )
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.1A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.44.34-2.1V7.07H2.18A11 11 0 0 0 1 12c0 1.77.42 3.45 1.18 4.93l3.66-2.83z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A10.5 10.5 0 0 0 12 1 11 11 0 0 0 2.18 7.07l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z" />
    </svg>
  )
}
