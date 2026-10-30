import { useState } from 'react'
import { api, type User, type UserKind } from '../api'

export function Onboarding({ onCreated, defaultName = '' }: { onCreated: (u: User) => void; defaultName?: string }) {
  const [name, setName] = useState(defaultName)
  const [kind, setKind] = useState<UserKind>('individual')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onCreated(await api.createUser(name.trim(), kind, 'IN'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reach the server')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen grid place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl border border-line bg-surface p-8 shadow-sm">
        <div className="flex items-center gap-2 text-accent">
          <Leaf />
          <span className="font-semibold tracking-tight">EcoTrack</span>
        </div>
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">Understand and shrink your carbon footprint</h1>
        <p className="mt-2 text-sm text-ink-2">
          Tell the AI assistant what you did — trips, bills, meals — and it measures the CO₂e, finds your hotspots
          and ranks what to change first.
        </p>

        <label className="mt-6 block text-sm font-medium" htmlFor="name">
          Name
        </label>
        <input
          id="name"
          required
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your name or organization"
          className="mt-1 w-full rounded-lg border border-line bg-page px-3 py-2 outline-none focus:ring-2 focus:ring-accent"
        />

        <fieldset className="mt-4">
          <legend className="text-sm font-medium">Tracking for</legend>
          <div className="mt-1 grid grid-cols-2 gap-2">
            {(['individual', 'organization'] as const).map((k) => (
              <label
                key={k}
                className={`cursor-pointer rounded-lg border px-3 py-2 text-sm ${
                  kind === k ? 'border-accent ring-1 ring-accent' : 'border-line'
                }`}
              >
                <input type="radio" name="kind" value={k} checked={kind === k} onChange={() => setKind(k)} className="sr-only" />
                <span className="font-medium">{k === 'individual' ? 'Myself' : 'An organization'}</span>
                <span className="block text-xs text-muted">{k === 'individual' ? 'Personal footprint' : 'Scope 1 / 2 / 3'}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {error && <p className="mt-4 text-sm text-critical">{error}</p>}
        <button
          disabled={busy || !name.trim()}
          className="mt-6 w-full rounded-lg bg-accent px-4 py-2.5 font-medium text-accent-ink disabled:opacity-50"
        >
          {busy ? 'Setting up…' : 'Get started'}
        </button>
        <p className="mt-3 text-center text-xs text-muted">Region: India (emission factors from CEA, DEFRA, IPCC)</p>
      </form>
    </div>
  )
}

export function Leaf({ className = 'size-5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" />
      <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" />
    </svg>
  )
}
