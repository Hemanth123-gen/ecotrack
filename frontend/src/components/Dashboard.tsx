import { useEffect, useState } from 'react'
import { api, type Activity, type DailyPoint, type Factor, type Recommendation, type Summary, type User } from '../api'
import { ActivityList, QuickLog } from './Activities'
import { Card } from './Card'
import { CategoryBreakdown } from './CategoryBreakdown'
import { GoalCard } from './GoalCard'
import { ImportDialog } from './ImportDialog'
import { InsightsCard } from './InsightsCard'
import { WhatIf } from './WhatIf'
import { Recommendations } from './Recommendations'
import { StatTiles } from './StatTiles'
import { TrendChart } from './TrendChart'

const PERIODS = [7, 30, 90] as const

interface Data {
  summary: Summary
  series: DailyPoint[]
  recs: Recommendation[]
  activities: Activity[]
}

export function Dashboard({
  user,
  refreshKey,
  onChanged,
  onAsk,
}: {
  user: User
  refreshKey: number
  onChanged: () => void
  onAsk: (q: string) => void
}) {
  const [days, setDays] = useState<number>(30)
  const [data, setData] = useState<Data | null>(null)
  const [factors, setFactors] = useState<Factor[]>([])
  const [error, setError] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [documentsEnabled, setDocumentsEnabled] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    api.factors(user.region).then(setFactors).catch(() => setFactors([]))
    api.health().then((h) => setDocumentsEnabled(h.document_import_enabled)).catch(() => {})
  }, [user.region])

  useEffect(() => {
    if (!notice) return
    const t = setTimeout(() => setNotice(null), 4000)
    return () => clearTimeout(t)
  }, [notice])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      api.summary(user.id, days),
      api.timeseries(user.id, days),
      api.recommendations(user.id, days),
      api.activities(user.id, days),
    ])
      .then(([summary, series, recs, activities]) => {
        if (!cancelled) {
          setData({ summary, series, recs: recs.recommendations, activities })
          setError(null)
        }
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : 'Failed to load'))
    return () => {
      cancelled = true
    }
  }, [user.id, days, refreshKey])

  return (
    // Container queries: the chat panel takes room beside us, so viewport breakpoints would mislead
    <div className="@container mx-auto max-w-6xl space-y-4 p-4 lg:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Your footprint</h1>
        <button
          onClick={() => setImportOpen(true)}
          className="ml-auto rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-2"
        >
          ⤒ Import bill or CSV
        </button>
        <div className="flex rounded-lg border border-line bg-surface p-0.5 text-sm" role="radiogroup" aria-label="Period">
          {PERIODS.map((p) => (
            <button
              key={p}
              role="radio"
              aria-checked={days === p}
              onClick={() => setDays(p)}
              className={`rounded-md px-3 py-1 ${days === p ? 'bg-surface-2 font-medium' : 'text-ink-2'}`}
            >
              {p} days
            </button>
          ))}
        </div>
      </div>

      {notice && (
        <div role="status" className="rounded-xl border border-line bg-surface px-4 py-3 text-sm">
          <span className="text-good">✓</span> {notice}
        </div>
      )}

      <ImportDialog
        user={user}
        open={importOpen}
        documentsEnabled={documentsEnabled}
        onClose={() => setImportOpen(false)}
        onSaved={(n) => {
          setNotice(`Imported ${n} ${n === 1 ? 'activity' : 'activities'}.`)
          onChanged()
        }}
      />

      {error && (
        <div className="rounded-xl border border-line bg-surface p-4 text-sm text-critical">
          Couldn't load your data: {error}. Is the backend running on port 8000?
        </div>
      )}

      {data && (
        <>
          {data.summary.activities_count === 0 && (
            <div className="rounded-2xl border border-dashed border-line bg-surface p-5 text-sm text-ink-2">
              <span className="font-medium text-ink">Nothing logged in the last {days} days.</span> Tell the assistant
              what you did (“I drove 25 km to work and my electricity bill was 240 units”) or use the quick log below.
            </div>
          )}

          <StatTiles summary={data.summary} days={days} />

          <div className="grid gap-4 @3xl:grid-cols-5">
            <div className="@3xl:col-span-3">
              <GoalCard user={user} refreshKey={refreshKey} onAsk={onAsk} />
            </div>
            <div className="@3xl:col-span-2">
              <InsightsCard user={user} refreshKey={refreshKey} />
            </div>
          </div>

          <div className="grid gap-4 @3xl:grid-cols-5">
            <Card title="Daily emissions" className="@3xl:col-span-3">
              <TrendChart points={data.series} />
            </Card>
            <Card title="By category" className="@3xl:col-span-2">
              <CategoryBreakdown summary={data.summary} />
            </Card>
          </div>

          <div className="grid gap-4 @3xl:grid-cols-5">
            <Card title="Top ways to reduce" className="@3xl:col-span-3">
              <Recommendations items={data.recs} onAsk={onAsk} />
            </Card>
            <Card title="What if…" className="@3xl:col-span-2">
              <WhatIf user={user} days={days} activities={data.activities} factors={factors} />
            </Card>
          </div>

          <Card title="Activities">
            <div className="grid gap-4 @3xl:grid-cols-[18rem_1fr]">
              <QuickLog user={user} factors={factors} onLogged={onChanged} />
              <ActivityList user={user} activities={data.activities} factors={factors} onChanged={onChanged} />
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
