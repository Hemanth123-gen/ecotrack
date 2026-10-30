import { useEffect, useRef, useState } from 'react'
import { api, type DocumentPreview, type ImportItem, type ImportPreview, type User } from '../api'
import { formatKg, todayIso } from '../format'

type Mode = 'document' | 'csv'

interface Row extends ImportItem {
  include: boolean
  rate: number | null // kg CO2e per unit, so edits re-price without a round trip
}

const DOC_TYPE_LABEL: Record<string, string> = {
  electricity_bill: 'Electricity bill',
  lpg_receipt: 'LPG receipt',
  piped_gas_bill: 'Piped gas bill',
  fuel_receipt: 'Fuel receipt',
  travel_ticket: 'Travel ticket',
  grocery_receipt: 'Grocery receipt',
  shopping_receipt: 'Shopping receipt',
  other: 'Other document',
  unreadable: 'Unreadable',
}

const toRows = (items: ImportItem[]): Row[] =>
  items.map((i) => ({
    ...i,
    include: !i.error,
    rate: i.kg_co2e != null && i.quantity ? i.kg_co2e / i.quantity : null,
  }))

export function ImportDialog({
  user,
  open,
  onClose,
  onSaved,
  documentsEnabled,
}: {
  user: User
  open: boolean
  onClose: () => void
  onSaved: (count: number) => void
  documentsEnabled: boolean
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [mode, setMode] = useState<Mode>(documentsEnabled ? 'document' : 'csv')
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState<'reading' | 'saving' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [doc, setDoc] = useState<Omit<DocumentPreview, keyof ImportPreview> | null>(null)
  const [rows, setRows] = useState<Row[] | null>(null)

  useEffect(() => {
    const d = dialogRef.current
    if (!d) return
    if (open && !d.open) {
      // Health loads after mount, so pick the default tab on every open rather than once
      setMode(documentsEnabled ? 'document' : 'csv')
      d.showModal()
    }
    if (!open && d.open) d.close()
  }, [open, documentsEnabled])

  useEffect(() => () => void (previewUrl && URL.revokeObjectURL(previewUrl)), [previewUrl])

  function reset() {
    setFile(null)
    setPreviewUrl(null)
    setRows(null)
    setDoc(null)
    setError(null)
  }

  function close() {
    reset()
    onClose()
  }

  async function read(f: File) {
    reset()
    setFile(f)
    if (f.type.startsWith('image/')) setPreviewUrl(URL.createObjectURL(f))
    setBusy('reading')
    try {
      if (mode === 'document') {
        const res = await api.importDocument(user.id, f)
        setDoc({ document_type: res.document_type, summary: res.summary, warnings: res.warnings })
        setRows(toRows(res.items))
      } else {
        setRows(toRows((await api.importCsv(user.id, f)).items))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setBusy(null)
    }
  }

  function update(i: number, patch: Partial<Row>) {
    setRows((rs) =>
      rs!.map((r, j) => {
        if (j !== i) return r
        const next = { ...r, ...patch }
        next.kg_co2e = next.rate != null && next.quantity != null ? next.rate * next.quantity : null
        return next
      }),
    )
  }

  const selected = rows?.filter((r) => r.include && !r.error && r.quantity != null && r.quantity >= 0) ?? []
  const total = selected.reduce((s, r) => s + (r.kg_co2e ?? 0), 0)

  async function save() {
    setBusy('saving')
    setError(null)
    try {
      await api.logActivities(
        user.id,
        selected.map((r) => ({
          key: r.key,
          quantity: r.quantity!,
          unit: r.unit,
          occurred_on: r.occurred_on || undefined,
          description: r.description || undefined,
        })),
      )
      onSaved(selected.length)
      close()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(null)
    }
  }

  const input = 'rounded-md border border-line bg-page px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-accent'

  return (
    <dialog
      ref={dialogRef}
      onClose={close}
      className="m-auto w-[min(56rem,calc(100vw-2rem))] max-h-[calc(100dvh-2rem)] rounded-2xl border border-line bg-surface p-0 text-ink backdrop:bg-black/50"
    >
      <div className="flex max-h-[calc(100dvh-2rem)] flex-col">
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <h2 className="font-semibold">Import activities</h2>
          <button onClick={close} aria-label="Close" className="ml-auto rounded-lg px-2 py-1 text-ink-2 hover:bg-surface-2">
            ✕
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div className="mb-4 flex rounded-lg border border-line p-0.5 text-sm" role="tablist">
            {(
              [
                ['document', 'Scan a bill or receipt'],
                ['csv', 'Upload a CSV'],
              ] as const
            ).map(([m, label]) => (
              <button
                key={m}
                role="tab"
                aria-selected={mode === m}
                onClick={() => {
                  setMode(m)
                  reset()
                }}
                className={`flex-1 rounded-md px-3 py-1.5 ${mode === m ? 'bg-surface-2 font-medium' : 'text-ink-2'}`}
              >
                {label}
              </button>
            ))}
          </div>

          {mode === 'document' && !documentsEnabled ? (
            <p className="rounded-xl border border-line bg-surface-2 p-4 text-sm text-ink-2">
              Bill scanning uses Gemini vision. Add <code>GEMINI_API_KEY</code> to <code>backend/.env</code> and restart
              the backend to turn it on. CSV import works without it.
            </p>
          ) : (
            <>
              {!rows && (
                <DropZone
                  mode={mode}
                  busy={busy === 'reading'}
                  fileName={file?.name}
                  onFile={read}
                />
              )}

              {mode === 'csv' && !rows && (
                <p className="mt-3 text-sm text-ink-2">
                  Columns: <code>date, activity, quantity, unit, description</code>. Dates can be YYYY-MM-DD or DD/MM/YYYY.{' '}
                  <a href={api.csvTemplateUrl} className="text-accent hover:underline" download>
                    Download template
                  </a>
                </p>
              )}
            </>
          )}

          {error && <p className="mt-4 rounded-lg border border-line px-3 py-2 text-sm text-critical">{error}</p>}

          {rows && (
            <div className="space-y-4">
              <div className="flex gap-4">
                {previewUrl && (
                  <img src={previewUrl} alt="Uploaded document" className="h-24 w-20 shrink-0 rounded-lg border border-line object-cover" />
                )}
                <div className="min-w-0 text-sm">
                  {doc ? (
                    <>
                      <div className="font-medium">{DOC_TYPE_LABEL[doc.document_type] ?? doc.document_type}</div>
                      <p className="text-ink-2">{doc.summary}</p>
                    </>
                  ) : (
                    <div className="font-medium">{file?.name}</div>
                  )}
                  <p className="mt-1 text-ink-2">
                    Review before saving: untick rows you don't want and correct any amounts.
                  </p>
                  <button onClick={reset} className="mt-1 text-xs text-accent hover:underline">
                    Choose a different file
                  </button>
                </div>
              </div>

              {!!doc?.warnings.length && (
                <ul className="space-y-1 rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2">
                  {doc.warnings.map((w, i) => (
                    <li key={i}>⚠ {w}</li>
                  ))}
                </ul>
              )}

              {rows.length === 0 ? (
                <p className="text-sm text-ink-2">No activities found in this file.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[40rem] text-sm">
                    <thead className="text-left text-muted">
                      <tr>
                        <th className="w-8 py-1.5" />
                        <th className="py-1.5 font-normal">Activity</th>
                        <th className="py-1.5 font-normal">Amount</th>
                        <th className="py-1.5 font-normal">Date</th>
                        <th className="py-1.5 text-right font-normal">CO₂e</th>
                      </tr>
                    </thead>
                    <tbody className="tabular">
                      {rows.map((r, i) => (
                        <tr key={i} className={`border-t border-line align-top ${r.error ? 'opacity-70' : ''}`}>
                          <td className="py-2">
                            <input
                              type="checkbox"
                              checked={r.include}
                              disabled={!!r.error}
                              onChange={(e) => update(i, { include: e.target.checked })}
                              aria-label={`Include ${r.label ?? r.key}`}
                              className="size-4 accent-[var(--accent)]"
                            />
                          </td>
                          <td className="py-2 pr-3">
                            <span className="font-medium">{r.label ?? r.key}</span>
                            {r.confidence != null && r.confidence < 0.8 && (
                              <span className="ml-2 rounded-full border border-line px-1.5 text-xs text-ink-2">⚠ check</span>
                            )}
                            {r.description && <span className="block text-xs text-muted">{r.description}</span>}
                            {r.error && <span className="block text-xs text-critical">{r.error}</span>}
                          </td>
                          <td className="py-2 pr-3 whitespace-nowrap">
                            <input
                              type="number"
                              min="0"
                              step="any"
                              value={r.quantity ?? ''}
                              disabled={!!r.error}
                              onChange={(e) => update(i, { quantity: e.target.value === '' ? null : Number(e.target.value) })}
                              aria-label="Amount"
                              className={`${input} w-24`}
                            />
                            <span className="ml-1.5 text-ink-2">{r.unit}</span>
                          </td>
                          <td className="py-2 pr-3">
                            <input
                              type="date"
                              value={r.occurred_on ?? ''}
                              max={todayIso()}
                              disabled={!!r.error}
                              onChange={(e) => update(i, { occurred_on: e.target.value || null })}
                              aria-label="Date"
                              className={input}
                            />
                          </td>
                          <td className="py-2 text-right font-medium whitespace-nowrap">
                            {r.kg_co2e != null ? formatKg(r.kg_co2e) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>

        {rows && rows.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 border-t border-line px-5 py-4">
            <span className="text-sm text-ink-2">
              {selected.length} selected · <span className="font-medium text-ink">{formatKg(total)} CO₂e</span>
            </span>
            <button
              onClick={save}
              disabled={!selected.length || busy !== null}
              className="ml-auto rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50"
            >
              {busy === 'saving' ? 'Saving…' : `Save ${selected.length} ${selected.length === 1 ? 'activity' : 'activities'}`}
            </button>
          </div>
        )}
      </div>
    </dialog>
  )
}

function DropZone({
  mode,
  busy,
  fileName,
  onFile,
}: {
  mode: Mode
  busy: boolean
  fileName?: string
  onFile: (f: File) => void
}) {
  const [over, setOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const f = e.dataTransfer.files[0]
        if (f && !busy) onFile(f)
      }}
      className={`grid place-items-center rounded-xl border-2 border-dashed px-4 py-10 text-center ${
        over ? 'border-accent bg-surface-2' : 'border-line'
      }`}
    >
      {busy ? (
        <div className="text-sm text-ink-2">
          <div className="mx-auto mb-3 size-6 animate-spin rounded-full border-2 border-line border-t-accent" />
          {mode === 'document' ? `Reading ${fileName ?? 'your document'} with Gemini…` : 'Checking your CSV…'}
        </div>
      ) : (
        <div>
          <p className="font-medium">
            {mode === 'document' ? 'Drop a photo or PDF of a bill, receipt or ticket' : 'Drop a CSV file'}
          </p>
          <p className="mt-1 text-sm text-ink-2">
            {mode === 'document'
              ? 'Electricity, LPG, piped gas, fuel, flights, trains, groceries · JPEG, PNG, WebP, HEIC or PDF up to 10 MB'
              : 'Up to 1,000 rows'}
          </p>
          <button
            onClick={() => inputRef.current?.click()}
            className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink"
          >
            Choose file
          </button>
          <input
            ref={inputRef}
            type="file"
            hidden
            accept={mode === 'document' ? 'image/*,application/pdf' : '.csv,text/csv'}
            onChange={(e) => {
              const f = e.target.files?.[0]
              e.target.value = ''
              if (f) onFile(f)
            }}
          />
        </div>
      )}
    </div>
  )
}
