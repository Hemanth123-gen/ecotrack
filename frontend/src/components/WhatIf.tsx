import { useEffect, useMemo, useState } from 'react'
import { api, type Activity, type Factor, type ScenarioResult, type User } from '../api'
import { formatKg } from '../format'

/** Interactive what-if: pick something you do, switch or cut part of it, see the yearly saving. */
export function WhatIf({ user, days, activities, factors }: { user: User; days: number; activities: Activity[]; factors: Factor[] }) {
  const byKey = useMemo(() => new Map(factors.map((f) => [f.key, f])), [factors])
  // Activities actually logged in this period, biggest first
  const options = useMemo(() => {
    const totals = new Map<string, number>()
    for (const a of activities) totals.set(a.key, (totals.get(a.key) ?? 0) + a.kg_co2e)
    return [...totals.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k).filter((k) => byKey.has(k))
  }, [activities, byKey])

  const [fromKey, setFromKey] = useState('')
  const [toKey, setToKey] = useState('')
  const [fraction, setFraction] = useState(0.5)
  const [result, setResult] = useState<ScenarioResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const from = byKey.get(fromKey)
  // Alternatives must share the unit so the quantity carries over (km -> km, kWh -> kWh, kg -> kg)
  const alternatives = useMemo(
    () => factors.filter((f) => from && f.unit === from.unit && f.key !== from.key && f.value < from.value),
    [factors, from],
  )

  useEffect(() => {
    if (!fromKey && options.length) setFromKey(options[0])
    if (fromKey && !options.includes(fromKey)) setFromKey(options[0] ?? '')
  }, [options, fromKey])

  useEffect(() => {
    setToKey((current) => (alternatives.some((a) => a.key === current) ? current : ''))
  }, [alternatives])

  useEffect(() => {
    if (!fromKey) return
    let stale = false // ignore a slow response that lands after a newer request
    const t = setTimeout(() => {
      api
        .simulate(user.id, { kind: toKey ? 'switch' : 'reduce', from_key: fromKey, to_key: toKey || undefined, fraction, days })
        .then((r) => {
          if (stale) return
          setResult(r)
          setError(null)
        })
        .catch((e) => !stale && setError(e instanceof Error ? e.message : 'Simulation failed'))
    }, 200)
    return () => {
      stale = true
      clearTimeout(t)
    }
  }, [user.id, fromKey, toKey, fraction, days, activities])

  if (!options.length) return <p className="text-sm text-ink-2">Log some activities to try what-if scenarios.</p>

  const select = 'w-full rounded-lg border border-line bg-page px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent'
  return (
    <div className="space-y-3">
      <label className="block text-sm">
        <span className="text-ink-2">If I change</span>
        <select value={fromKey} onChange={(e) => setFromKey(e.target.value)} className={`${select} mt-1`}>
          {options.map((k) => (
            <option key={k} value={k}>{byKey.get(k)!.label}</option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        <span className="text-ink-2">to</span>
        <select value={toKey} onChange={(e) => setToKey(e.target.value)} className={`${select} mt-1`}>
          <option value="">Just do less of it</option>
          {alternatives.map((f) => (
            <option key={f.key} value={f.key}>{f.label}</option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        <span className="flex justify-between text-ink-2">
          <span>{toKey ? 'for this share of it' : 'cutting it by'}</span>
          <span className="font-medium text-ink tabular">{Math.round(fraction * 100)}%</span>
        </span>
        <input
          type="range"
          min="0.1"
          max="1"
          step="0.1"
          value={fraction}
          onChange={(e) => setFraction(Number(e.target.value))}
          className="mt-2 w-full accent-[var(--accent)]"
        />
      </label>

      {error ? (
        <p className="text-sm text-critical">{error}</p>
      ) : (
        result && (
          <div className="rounded-xl bg-surface-2 px-4 py-3">
            <div className="text-2xl font-semibold tracking-tight text-good tabular">−{formatKg(result.saved_kg_per_year)}</div>
            <div className="text-sm text-ink-2">
              per year · {result.saved_pct.toFixed(1)}% of your footprint over the last {result.days} days
            </div>
          </div>
        )
      )}
    </div>
  )
}
