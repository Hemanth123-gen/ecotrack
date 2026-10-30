export function formatKg(kg: number): string {
  if (kg >= 1000) return `${(kg / 1000).toFixed(2)} t`
  if (kg >= 100) return `${Math.round(kg)} kg`
  return `${kg.toFixed(1)} kg`
}

export const formatPct = (share: number) => `${Math.round(share * 100)}%`

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' }) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, opts)
}

export const todayIso = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
