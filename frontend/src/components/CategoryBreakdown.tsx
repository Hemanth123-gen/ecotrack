import type { Summary } from '../api'
import { formatKg, formatPct } from '../format'
import { CATEGORIES } from '../theme'

/** Horizontal bars in plain HTML: every value is direct-labeled, so no tooltip is needed. */
export function CategoryBreakdown({ summary }: { summary: Summary }) {
  const byCat = new Map(summary.by_category.map((c) => [c.category, c]))
  const rows = CATEGORIES.map((c) => ({ ...c, kg: byCat.get(c.key)?.kg_co2e ?? 0, share: byCat.get(c.key)?.share ?? 0 }))
    .sort((a, b) => b.kg - a.kg)
  const max = Math.max(...rows.map((r) => r.kg), 1)

  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.key}>
          <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
            <span className="text-ink-2">{r.label}</span>
            <span className="tabular">
              <span className="font-medium">{formatKg(r.kg)}</span>
              <span className="ml-2 text-muted">{formatPct(r.share)}</span>
            </span>
          </div>
          <div className="h-2.5 rounded-full bg-surface-2">
            <div
              className="h-full rounded-full"
              style={{ width: `${(r.kg / max) * 100}%`, background: `var(--cat-${r.key})`, minWidth: r.kg ? 4 : 0 }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}
