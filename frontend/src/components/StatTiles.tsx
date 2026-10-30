import type { Summary } from '../api'
import { formatKg, formatPct } from '../format'

function Tile({ label, value, sub, small = false }: { label: string; value: string; sub?: string; small?: boolean }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-5">
      <div className="text-sm text-ink-2">{label}</div>
      <div className={`mt-1 font-semibold tracking-tight ${small ? 'text-xl leading-9' : 'text-3xl'}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  )
}

const BENCHMARK_LABEL: Record<string, string> = {
  india_average: 'India avg',
  world_average: 'World avg',
  paris_1_5c_target_2030: '1.5 °C target',
}

export function StatTiles({ summary, days }: { summary: Summary; days: number }) {
  const india = summary.benchmarks.find((b) => b.name === 'india_average')
  const top = summary.hotspots[0]
  const limited = summary.days_with_data > 0 && summary.days_with_data < Math.min(7, days)
  const scope = (n: number) => summary.by_scope[String(n)] ?? 0

  return (
    <div className="grid grid-cols-1 gap-4 @md:grid-cols-2 @4xl:grid-cols-4">
      <Tile
        label={`Last ${days} days`}
        value={`${formatKg(summary.total_kg_co2e)} CO₂e`}
        sub={`${summary.activities_count} activities on ${summary.days_with_data} days`}
      />
      <Tile
        label="Annual estimate"
        value={`${summary.annualized_t_co2e.toFixed(2)} t`}
        sub={limited ? 'Based on limited data — keep logging' : `CO₂e/yr, extrapolated from ${summary.annualized_over_days} days`}
      />
      {summary.user_kind === 'individual' && india ? (
        <Tile
          label="Compared with India average"
          value={`${india.ratio.toFixed(1)}×`}
          sub={summary.benchmarks.map((b) => `${BENCHMARK_LABEL[b.name] ?? b.name} ${b.benchmark_t_per_year} t`).join(' · ')}
        />
      ) : (
        <Tile
          label="By GHG scope"
          value={`${formatPct(summary.total_kg_co2e ? scope(1) / summary.total_kg_co2e : 0)} direct`}
          sub={`Scope 1 ${formatKg(scope(1))} · Scope 2 ${formatKg(scope(2))} · Scope 3 ${formatKg(scope(3))}`}
        />
      )}
      <Tile
        label="Biggest hotspot"
        value={top ? top.label : '—'}
        small
        sub={top ? `${formatKg(top.kg_co2e)} · ${formatPct(top.share)} of total` : 'Nothing logged yet'}
      />
    </div>
  )
}
