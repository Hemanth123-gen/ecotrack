import { useEffect, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type GoalProgress, type GoalStatus, type SetGoal, type User } from '../api'
import { formatDate } from '../format'
import { useChartColors } from '../theme'
import { Card } from './Card'

// Status is never color-alone: each carries an icon and a label
const STATUS: Record<GoalStatus, { icon: string; label: string; color: string }> = {
  achieved: { icon: '✓', label: 'Target reached', color: 'var(--good)' },
  on_track: { icon: '✓', label: 'On track', color: 'var(--good)' },
  behind: { icon: '▲', label: 'Behind plan', color: 'var(--serious)' },
  not_enough_data: { icon: 'ⓘ', label: 'Need more data', color: 'var(--muted)' },
}

const PRESETS = [
  { label: '−10%', reduction_pct: 10 },
  { label: '−20%', reduction_pct: 20 },
  { label: '−30%', reduction_pct: 30 },
  { label: '1.5 °C (2.3 t)', target_t_per_year: 2.3 },
] as const

const isoMonthsAhead = (m: number) => {
  const d = new Date()
  d.setMonth(d.getMonth() + m)
  return d.toISOString().slice(0, 10)
}

const t = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(2)} t`)

export function GoalCard({ user, refreshKey, onAsk }: { user: User; refreshKey: number; onAsk: (q: string) => void }) {
  const [progress, setProgress] = useState<GoalProgress | null | undefined>(undefined)

  useEffect(() => {
    api.goal(user.id).then((g) => setProgress(g.goal ? (g as GoalProgress) : null)).catch(() => setProgress(null))
  }, [user.id, refreshKey])

  async function remove() {
    await api.deleteGoal(user.id)
    setProgress(null)
  }

  if (progress === undefined) return <Card title="Your goal"><div className="h-24" /></Card>
  if (progress === null) return <GoalForm user={user} onSet={setProgress} />

  const s = STATUS[progress.status]
  const g = progress.goal
  const achieved = Math.min(Math.max(progress.reduction_achieved_pct ?? 0, 0), 100)

  return (
    <Card
      title="Your goal"
      action={
        <button onClick={remove} className="text-xs text-ink-2 hover:underline">
          Change goal
        </button>
      }
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <span style={{ color: s.color }} aria-hidden>{s.icon}</span>
          {s.label}
        </span>
        <span className="text-sm text-ink-2">
          {t(g.baseline_t_per_year)} → {t(g.target_t_per_year)} per year by{' '}
          {formatDate(g.target_date, { day: 'numeric', month: 'short', year: 'numeric' })}
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
        {[
          ['Baseline', t(g.baseline_t_per_year)],
          ['Current pace', t(progress.current_t_per_year)],
          ['Target', t(g.target_t_per_year)],
        ].map(([k, v]) => (
          <div key={k}>
            <dt className="text-muted">{k}</dt>
            <dd className="text-lg font-semibold tracking-tight">{v}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-4">
        <div className="mb-1 flex justify-between text-xs text-ink-2">
          <span>{progress.reduction_achieved_pct == null ? 'Reduction achieved: —' : `${Math.round(achieved)}% of the planned cut achieved`}</span>
          <span>{progress.days_left} days left</span>
        </div>
        <div className="relative h-2.5 rounded-full bg-surface-2">
          <div className="h-full rounded-full bg-accent" style={{ width: `${achieved}%` }} />
          {/* where the plan says you should be today */}
          <div
            className="absolute -top-1 h-4.5 w-0.5 rounded bg-ink-2"
            style={{ left: `${progress.elapsed_pct}%` }}
            title="Where the plan expects you today"
          />
        </div>
      </div>

      {progress.status === 'not_enough_data' ? (
        <p className="mt-4 text-sm text-ink-2">
          Log at least 7 days in a 30-day window to measure your pace ({progress.days_with_data} so far).
        </p>
      ) : (
        <PaceChart progress={progress} />
      )}

      {progress.status === 'behind' && (
        <button
          onClick={() => onAsk("I'm behind on my carbon goal. What are the one or two changes that would get me back on track?")}
          className="mt-2 text-xs text-accent hover:underline"
        >
          Ask the assistant how to catch up →
        </button>
      )}
    </Card>
  )
}

function PaceChart({ progress }: { progress: GoalProgress }) {
  const colors = useChartColors()
  const data = progress.series.map((p) => ({ date: p.date, actual: p.actual_t_per_year, planned: p.planned_t_per_year }))
  return (
    <div className="mt-4 h-44">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid vertical={false} stroke={colors.grid} />
          <XAxis dataKey="date" tickFormatter={(d) => formatDate(d)} tick={{ fill: colors.muted, fontSize: 11 }} axisLine={{ stroke: colors.axis }} tickLine={false} minTickGap={24} />
          <YAxis tick={{ fill: colors.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={44} domain={[0, 'auto']} tickFormatter={(v: number) => `${v}t`} />
          <Legend verticalAlign="top" height={24} iconType="plainline" wrapperStyle={{ fontSize: 12, color: colors.ink2 }} />
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null
              const row = payload[0].payload as { actual: number | null; planned: number }
              return (
                <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-md">
                  <div className="mb-1 text-muted">Week to {formatDate(String(label))}</div>
                  <div className="flex items-center gap-2">
                    <span className="h-0.5 w-3" style={{ background: colors.category.transport }} />
                    <span className="font-medium">{row.actual == null ? '—' : `${row.actual.toFixed(2)} t/yr`}</span>
                    <span className="text-ink-2">Your pace</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-0.5 w-3 border-t border-dashed" style={{ borderColor: colors.ink2 }} />
                    <span className="font-medium">{row.planned.toFixed(2)} t/yr</span>
                    <span className="text-ink-2">Plan</span>
                  </div>
                </div>
              )
            }}
          />
          <Line name="Plan" dataKey="planned" stroke={colors.ink2} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          <Line name="Your pace" dataKey="actual" stroke={colors.category.transport} strokeWidth={2} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function GoalForm({ user, onSet }: { user: User; onSet: (p: GoalProgress) => void }) {
  const [preset, setPreset] = useState(1)
  const [targetDate, setTargetDate] = useState(() => isoMonthsAhead(6))
  const [baseline, setBaseline] = useState('')
  const [needsBaseline, setNeedsBaseline] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const presets = user.kind === 'individual' ? PRESETS : PRESETS.slice(0, 3)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const { label: _label, ...target } = presets[preset]
    const body: SetGoal = { target_date: targetDate, ...target }
    if (baseline) body.baseline_t_per_year = Number(baseline)
    try {
      onSet(await api.setGoal(user.id, body))
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not set goal'
      if (msg.includes('baseline')) setNeedsBaseline(true)
      setError(msg)
    } finally {
      setBusy(false)
    }
  }

  const field = 'rounded-lg border border-line bg-page px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent'
  return (
    <Card title="Set a reduction goal">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-sm text-ink-2">
          Your baseline is measured from the last 30 days of logging. Progress is tracked against a steady glide path to
          the target.
        </p>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Target">
          {presets.map((p, i) => (
            <button
              type="button"
              key={p.label}
              role="radio"
              aria-checked={preset === i}
              onClick={() => setPreset(i)}
              className={`rounded-lg border px-3 py-1.5 text-sm ${preset === i ? 'border-accent font-medium ring-1 ring-accent' : 'border-line text-ink-2'}`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm text-ink-2" htmlFor="goal-date">by</label>
          <input id="goal-date" type="date" required value={targetDate} min={isoMonthsAhead(0)} onChange={(e) => setTargetDate(e.target.value)} className={field} />
          {needsBaseline && (
            <input
              type="number"
              min="0.1"
              step="any"
              value={baseline}
              onChange={(e) => setBaseline(e.target.value)}
              placeholder="Known footprint, t/yr"
              aria-label="Known annual footprint in tonnes"
              className={`${field} w-48`}
            />
          )}
          <button disabled={busy} className="ml-auto rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50">
            {busy ? 'Setting…' : 'Set goal'}
          </button>
        </div>
        {error && <p className="text-sm text-critical">{error}</p>}
      </form>
    </Card>
  )
}
