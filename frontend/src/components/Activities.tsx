import { useMemo, useState } from 'react'
import { api, type Activity, type Factor, type User } from '../api'
import { formatDate, formatKg, todayIso } from '../format'
import { CATEGORIES } from '../theme'

export function QuickLog({ user, factors, onLogged }: { user: User; factors: Factor[]; onLogged: () => void }) {
  const [key, setKey] = useState('')
  const [quantity, setQuantity] = useState('')
  const [date, setDate] = useState(todayIso)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const factor = factors.find((f) => f.key === key)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!factor) return
    setBusy(true)
    setError(null)
    try {
      await api.logActivity(user.id, { key, quantity: Number(quantity), unit: factor.unit, occurred_on: date })
      setQuantity('')
      onLogged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to log')
    } finally {
      setBusy(false)
    }
  }

  const field = 'rounded-lg border border-line bg-page px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent'
  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-2">
      <select required value={key} onChange={(e) => setKey(e.target.value)} className={`${field} col-span-2`} aria-label="Activity">
        <option value="">Choose an activity…</option>
        {CATEGORIES.map((c) => (
          <optgroup key={c.key} label={c.label}>
            {factors.filter((f) => f.category === c.key).map((f) => (
              <option key={f.key} value={f.key}>{f.label}</option>
            ))}
          </optgroup>
        ))}
      </select>
      <div className="relative">
        <input
          required
          type="number"
          min="0"
          step="any"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          placeholder="Amount"
          aria-label="Amount"
          className={`${field} w-full pr-12`}
        />
        <span className="pointer-events-none absolute right-3 top-2 text-sm text-muted">{factor?.unit ?? ''}</span>
      </div>
      <input type="date" value={date} max={todayIso()} onChange={(e) => setDate(e.target.value)} className={field} aria-label="Date" />
      <button disabled={busy || !factor} className="col-span-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50">
        Log
      </button>
      {error && <p className="col-span-full text-sm text-critical">{error}</p>}
    </form>
  )
}

export function ActivityList({
  user,
  activities,
  factors,
  onChanged,
}: {
  user: User
  activities: Activity[]
  factors: Factor[]
  onChanged: () => void
}) {
  const byKey = useMemo(() => new Map(factors.map((f) => [f.key, f])), [factors])
  if (!activities.length) return <p className="text-sm text-ink-2">No activities in this period yet.</p>

  async function remove(id: number) {
    await api.deleteActivity(user.id, id)
    onChanged()
  }

  return (
    <div className="max-h-80 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface text-left text-muted">
          <tr>
            <th className="py-1.5 font-normal">Date</th>
            <th className="py-1.5 font-normal">Activity</th>
            <th className="py-1.5 text-right font-normal">Amount</th>
            <th className="py-1.5 text-right font-normal">CO₂e</th>
            <th className="w-8" />
          </tr>
        </thead>
        <tbody className="tabular">
          {activities.map((a) => {
            const f = byKey.get(a.key)
            return (
              <tr key={a.id} className="group border-t border-line">
                <td className="py-2 whitespace-nowrap text-ink-2">{formatDate(a.occurred_on)}</td>
                <td className="py-2">
                  <span className="mr-2 inline-block size-2 rounded-full align-middle" style={{ background: f ? `var(--cat-${f.category})` : 'var(--muted)' }} />
                  {f?.label ?? a.key}
                  {a.description && <span className="block pl-4 text-xs text-muted">{a.description}</span>}
                </td>
                <td className="py-2 text-right whitespace-nowrap text-ink-2">
                  {+a.quantity.toFixed(2)} {a.unit}
                </td>
                <td className="py-2 text-right font-medium whitespace-nowrap">{formatKg(a.kg_co2e)}</td>
                <td className="py-2 text-right">
                  <button
                    onClick={() => remove(a.id)}
                    aria-label={`Delete ${f?.label ?? a.key}`}
                    className="rounded px-1 text-muted opacity-60 hover:text-critical hover:opacity-100 group-hover:opacity-100"
                  >
                    ×
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
