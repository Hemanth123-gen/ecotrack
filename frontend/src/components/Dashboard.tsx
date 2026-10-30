import { useEffect, useState } from 'react'
import { api, type Activity, type DailyPoint, type Factor, type Recommendation, type Summary, type User } from '../api'
import { ActivityList, QuickLog } from './Activities'
import { Card } from './Card'
import { CategoryBreakdown } from './CategoryBreakdown'
import { GoalCard } from './GoalCard'
import { ImportDialog } from './ImportDialog'
import { InsightsCard } from './InsightsCard'
import { Recommendations } from './Recommendations'
import { TrendChart } from './TrendChart'
import { WhatIf } from './WhatIf'

const PERIODS = [7, 30, 90] as const

// The three things the agent does, shown as steps
type Step = 'analyze' | 'understand' | 'reduce'
const STEPS: { id: Step; title: string; text: string }[] = [
  { id: 'analyze', title: 'Analyze', text: 'Log what you did — by chat, bill photo, CSV or by hand.' },
  { id: 'understand', title: 'Understand', text: 'See where your CO₂ comes from and how it changes.' },
  { id: 'reduce', title: 'Reduce', text: 'Get ranked actions, test what-ifs and set a goal.' },
]

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
  const [tab, setTab] = useState<Step | null>(null)

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
          // A new user starts at step 1; someone with data starts at step 2
          setTab((t) => t ?? (summary.activities_count === 0 ? 'analyze' : 'understand'))
          setError(null)
        }
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : 'Failed to load'))
    return () => {
      cancelled = true
    }
  }, [user.id, days, refreshKey])

  const india = data?.summary.benchmarks.find((b) => b.name === 'india_average')
  const top = data?.summary.hotspots[0]
  const empty = data?.summary.activities_count === 0

  return (
    // Container queries: the chat panel takes room beside us, so viewport breakpoints would mislead
    <div className="@container mx-auto max-w-6xl space-y-5 p-4 lg:p-6">
      {/* Headline: the one number that matters */}
      <section className="rounded-2xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <div>
            <div className="text-sm text-ink-2">Your carbon footprint, estimated per year</div>
            <div className="text-4xl font-semibold tracking-tight">
              {data && !empty ? `${data.summary.annualized_t_co2e.toFixed(2)} t CO₂e` : '—'}
            </div>
          </div>
          {!empty && india && (
            <div className="pb-1 text-sm text-ink-2">
              <span className="font-semibold text-ink">{india.ratio.toFixed(1)}×</span> the India average
            </div>
          )}
          {!empty && top && (
            <div className="pb-1 text-sm text-ink-2">
              Biggest source: <span className="font-semibold text-ink">{top.label}</span>
            </div>
          )}
          <div className="ml-auto flex rounded-lg border border-line p-0.5 text-sm" role="radiogroup" aria-label="Period">
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
      </section>

      <nav className="grid gap-3 @2xl:grid-cols-3" role="tablist" aria-label="Steps">
        {STEPS.map((step, i) => {
          const active = tab === step.id
          return (
            <button
              key={step.id}
              role="tab"
              aria-selected={active}
              onClick={() => setTab(step.id)}
              className={`rounded-2xl border bg-surface p-4 text-left ${
                active ? 'border-accent ring-1 ring-accent' : 'border-line hover:bg-surface-2'
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`grid size-6 place-items-center rounded-full text-xs font-semibold ${
                    active ? 'bg-accent text-accent-ink' : 'bg-surface-2'
                  }`}
                >
                  {i + 1}
                </span>
                <span className="font-semibold">{step.title}</span>
              </div>
              <p className="mt-1 text-sm text-ink-2">{step.text}</p>
            </button>
          )
        })}
      </nav>

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

      {data && tab === 'analyze' && (
        <>
          <div className="grid gap-4 @3xl:grid-cols-2">
            <Card title="Tell the AI assistant">
              <p className="text-sm text-ink-2">
                Describe your day in plain words. The AI picks the right emission factors and logs it; the numbers come
                from a fixed calculation engine, never guessed.
              </p>
              <button
                onClick={() => onAsk('I drove 25 km to work in my petrol car and had chicken biryani for lunch')}
                className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink"
              >
                Try an example in chat
              </button>
            </Card>
            <Card title="Upload a bill or spreadsheet">
              <p className="text-sm text-ink-2">
                Snap an electricity bill, fuel receipt or ticket and the AI reads the quantities, or upload a CSV. You
                review everything before it's saved.
              </p>
              <button
                onClick={() => setImportOpen(true)}
                className="mt-3 rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-surface-2"
              >
                ⤒ Import bill or CSV
              </button>
            </Card>
          </div>
          <Card title="Or log it yourself">
            <div className="grid gap-4 @3xl:grid-cols-[18rem_1fr]">
              <QuickLog user={user} factors={factors} onLogged={onChanged} />
              <ActivityList user={user} activities={data.activities} factors={factors} onChanged={onChanged} />
            </div>
          </Card>
        </>
      )}

      {data && tab === 'understand' &&
        (empty ? (
          <EmptyHint onStart={() => setTab('analyze')} />
        ) : (
          <>
            <div className="grid gap-4 @3xl:grid-cols-2">
              <Card title="Where your emissions come from">
                <CategoryBreakdown summary={data.summary} />
              </Card>
              <InsightsCard user={user} refreshKey={refreshKey} />
            </div>
            <Card title="Day by day">
              <TrendChart points={data.series} />
            </Card>
          </>
        ))}

      {data && tab === 'reduce' &&
        (empty ? (
          <EmptyHint onStart={() => setTab('analyze')} />
        ) : (
          <>
            <Card title="Best actions for you, ranked by CO₂ saved">
              <Recommendations items={data.recs} onAsk={onAsk} />
            </Card>
            <div className="grid gap-4 @3xl:grid-cols-5">
              <Card title="Try a what-if" className="@3xl:col-span-2">
                <WhatIf user={user} days={days} activities={data.activities} factors={factors} />
              </Card>
              <div className="@3xl:col-span-3">
                <GoalCard user={user} refreshKey={refreshKey} onAsk={onAsk} />
              </div>
            </div>
          </>
        ))}
    </div>
  )
}

function EmptyHint({ onStart }: { onStart: () => void }) {
  return (
    <div className="rounded-2xl border border-dashed border-line bg-surface p-8 text-center">
      <p className="font-medium">Nothing logged yet</p>
      <p className="mt-1 text-sm text-ink-2">Add a few activities first and this step fills in automatically.</p>
      <button onClick={onStart} className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink">
        Go to step 1: Analyze
      </button>
    </div>
  )
}
