import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { DailyPoint } from '../api'
import { formatDate, formatKg } from '../format'
import { CATEGORIES, useChartColors } from '../theme'

export function TrendChart({ points }: { points: DailyPoint[] }) {
  const colors = useChartColors()
  const [showTable, setShowTable] = useState(false)
  const data = points.map((p) => ({ date: p.date, total: p.total_kg_co2e, ...p.by_category }))
  const present = CATEGORIES.filter((c) => points.some((p) => (p.by_category[c.key] ?? 0) > 0))
  const series = present.length ? present : CATEGORIES

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
        {series.map((c) => (
          <span key={c.key} className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ background: colors.category[c.key] }} />
            {c.label}
          </span>
        ))}
        <button onClick={() => setShowTable((s) => !s)} className="ml-auto text-ink-2 underline-offset-2 hover:underline">
          {showTable ? 'Show chart' : 'Show table'}
        </button>
      </div>

      {showTable ? (
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-sm tabular">
            <thead className="text-left text-muted">
              <tr>
                <th className="py-1 font-normal">Date</th>
                {series.map((c) => (
                  <th key={c.key} className="py-1 text-right font-normal">{c.label}</th>
                ))}
                <th className="py-1 text-right font-normal">Total</th>
              </tr>
            </thead>
            <tbody>
              {[...points].reverse().filter((p) => p.total_kg_co2e > 0).map((p) => (
                <tr key={p.date} className="border-t border-line">
                  <td className="py-1">{formatDate(p.date)}</td>
                  {series.map((c) => (
                    <td key={c.key} className="py-1 text-right">{formatKg(p.by_category[c.key] ?? 0)}</td>
                  ))}
                  <td className="py-1 text-right font-medium">{formatKg(p.total_kg_co2e)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
              <CartesianGrid vertical={false} stroke={colors.grid} />
              <XAxis
                dataKey="date"
                tickFormatter={(d) => formatDate(d)}
                tick={{ fill: colors.muted, fontSize: 11 }}
                axisLine={{ stroke: colors.axis }}
                tickLine={false}
                minTickGap={24}
              />
              <YAxis
                tick={{ fill: colors.muted, fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={48}
                tickFormatter={(v: number) => `${v}`}
                label={{ value: 'kg CO₂e', angle: -90, position: 'insideLeft', offset: 20, fill: colors.muted, fontSize: 11 }}
              />
              <Tooltip
                cursor={{ fill: colors.grid, opacity: 0.5 }}
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null
                  const row = payload[0].payload as { total: number }
                  return (
                    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-md">
                      <div className="mb-1 text-muted">{formatDate(String(label), { weekday: 'short', day: 'numeric', month: 'short' })}</div>
                      <div className="mb-1 text-sm font-semibold">{formatKg(row.total)}</div>
                      {series.map((c) => {
                        const v = (payload[0].payload as Record<string, number>)[c.key] ?? 0
                        return (
                          <div key={c.key} className="flex items-center gap-2">
                            <span className="h-0.5 w-3" style={{ background: colors.category[c.key] }} />
                            <span className="font-medium tabular">{formatKg(v)}</span>
                            <span className="text-ink-2">{c.label}</span>
                          </div>
                        )
                      })}
                    </div>
                  )
                }}
              />
              {series.map((c, i) => (
                <Bar
                  key={c.key}
                  dataKey={c.key}
                  stackId="day"
                  fill={colors.category[c.key]}
                  stroke={colors.surface}
                  strokeWidth={1}
                  maxBarSize={28}
                  radius={i === series.length - 1 ? [4, 4, 0, 0] : 0}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
