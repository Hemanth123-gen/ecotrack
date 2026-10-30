import type { Recommendation } from '../api'
import { formatKg } from '../format'

const EFFORT: Record<Recommendation['effort'], string> = { low: 'Easy', medium: 'Moderate', high: 'Big change' }

export function Recommendations({ items, onAsk }: { items: Recommendation[]; onAsk: (q: string) => void }) {
  if (!items.length) {
    return <p className="text-sm text-ink-2">Log a few activities and ranked reduction ideas will appear here.</p>
  }
  return (
    <ol className="space-y-3">
      {items.map((r, i) => (
        <li key={r.id} className="flex gap-3 rounded-xl border border-line p-3">
          <span className="grid size-6 shrink-0 place-items-center rounded-full bg-surface-2 text-xs font-semibold">{i + 1}</span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-medium">{r.title}</span>
              <span className="rounded-full border border-line px-2 text-xs text-ink-2">{EFFORT[r.effort]}</span>
            </div>
            <p className="mt-0.5 text-sm text-ink-2">{r.tip}</p>
            <button
              onClick={() => onAsk(`How can I "${r.title.toLowerCase()}"? Give me a practical plan.`)}
              className="mt-1 text-xs text-accent hover:underline"
            >
              Ask the assistant how →
            </button>
          </div>
          <div className="shrink-0 text-right">
            <div className="font-semibold text-good tabular">−{formatKg(r.saved_kg_per_year)}</div>
            <div className="text-xs text-muted">per year</div>
          </div>
        </li>
      ))}
    </ol>
  )
}
