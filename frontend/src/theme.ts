import { useEffect, useState } from 'react'
import type { Category } from './api'

// Fixed entity -> slot order, so a category keeps its color whatever is filtered.
export const CATEGORIES: { key: Category; label: string }[] = [
  { key: 'transport', label: 'Transport' },
  { key: 'energy', label: 'Energy' },
  { key: 'food', label: 'Food' },
  { key: 'goods', label: 'Goods' },
  { key: 'waste', label: 'Waste' },
]

export const categoryLabel = (c: string) => CATEGORIES.find((x) => x.key === c)?.label ?? c

export interface ChartColors {
  category: Record<Category, string>
  surface: string
  grid: string
  axis: string
  muted: string
  ink: string
  ink2: string
}

function readColors(): ChartColors {
  const s = getComputedStyle(document.documentElement)
  const v = (name: string) => s.getPropertyValue(name).trim()
  return {
    category: Object.fromEntries(CATEGORIES.map((c) => [c.key, v(`--cat-${c.key}`)])) as Record<Category, string>,
    surface: v('--surface'),
    grid: v('--grid'),
    axis: v('--axis'),
    muted: v('--muted'),
    ink: v('--ink'),
    ink2: v('--ink-2'),
  }
}

/** SVG chart colors resolved from CSS tokens; re-reads when the OS theme flips. */
export function useChartColors(): ChartColors {
  const [colors, setColors] = useState(readColors)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => setColors(readColors())
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  }, [])
  return colors
}
