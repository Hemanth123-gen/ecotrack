import { useEffect, useState } from 'react'
import { api, type User, type WeeklyInsights } from '../api'
import { formatDate, formatKg } from '../format'
import { categoryLabel } from '../theme'
import { Card } from './Card'

export function InsightsCard({ user, refreshKey }: { user: User; refreshKey: number }) {
  const [w, setW] = useState<WeeklyInsights | null>(null)

  useEffect(() => {
    api.weeklyInsights(user.id).then(setW).catch(() => setW(null))
  }, [user.id, refreshKey])

  if (!w) return <Card title="This week"><div className="h-24" /></Card>

  const down = w.change_kg < 0
  return (
    <Card title="This week" action={<span className="text-xs text-muted">{formatDate(w.week_start)} – {formatDate(w.week_end)}</span>}>
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="text-3xl font-semibold tracking-tight">{formatKg(w.this_week_kg)}</span>
        {w.change_pct != null && Math.abs(w.change_pct) >= 1 && (
          <span className="text-sm font-medium">
            <span style={{ color: down ? 'var(--good)' : 'var(--critical)' }} aria-hidden>{down ? '▼' : '▲'}</span>{' '}
            {Math.abs(w.change_pct).toFixed(0)}% {down ? 'lower' : 'higher'} than last week
          </span>
        )}
      </div>

      <ul className="mt-3 space-y-1.5 text-sm text-ink-2">
        {w.highlights.map((h, i) => (
          <li key={i} className="flex gap-2">
            <span aria-hidden className="text-muted">•</span>
            {h}
          </li>
        ))}
      </ul>

      {w.last_week_kg > 0 && w.by_category.length > 0 && (
        <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-ink-2 hover:text-ink">Compare by category</summary>
        <table className="mt-2 w-full text-sm tabular">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="py-1 font-normal">Category</th>
              <th className="py-1 text-right font-normal">Last week</th>
              <th className="py-1 text-right font-normal">This week</th>
              <th className="py-1 text-right font-normal">Change</th>
            </tr>
          </thead>
          <tbody>
            {w.by_category.map((c) => (
              <tr key={c.category} className="border-t border-line">
                <td className="py-1.5">
                  <span className="mr-2 inline-block size-2 rounded-full" style={{ background: `var(--cat-${c.category})` }} />
                  {categoryLabel(c.category)}
                </td>
                <td className="py-1.5 text-right text-ink-2">{formatKg(c.last_week_kg)}</td>
                <td className="py-1.5 text-right">{formatKg(c.this_week_kg)}</td>
                <td className="py-1.5 text-right font-medium">
                  {Math.abs(c.change_kg) < 0.05 ? '—' : `${c.change_kg < 0 ? '−' : '+'}${formatKg(Math.abs(c.change_kg))}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </details>
      )}
    </Card>
  )
}
