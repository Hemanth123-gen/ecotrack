// Typed client for the FastAPI backend (proxied at /api in dev).
import { getIdToken } from './auth'

export type Category = 'transport' | 'energy' | 'food' | 'goods' | 'waste'
export type UserKind = 'individual' | 'organization'

export interface User {
  id: string
  name: string
  kind: UserKind
  region: string
}

export interface Factor {
  key: string
  label: string
  category: Category
  scope: 1 | 2 | 3
  unit: string
  value: number
  region: string
  source: string
}

export interface Activity {
  id: number
  key: string
  quantity: number
  unit: string
  region: string
  occurred_on: string
  description: string | null
  kg_co2e: number
}

export interface Summary {
  total_kg_co2e: number
  period_days: number
  annualized_t_co2e: number
  by_category: { category: Category; kg_co2e: number; share: number }[]
  by_scope: Record<string, number>
  hotspots: { key: string; label: string; kg_co2e: number; share: number }[]
  benchmarks: { name: string; benchmark_t_per_year: number; ratio: number }[]
  activities_count: number
  days_with_data: number
  annualized_over_days: number
  user_kind: UserKind
}

export interface DailyPoint {
  date: string
  total_kg_co2e: number
  by_category: Partial<Record<Category, number>>
}

export interface Recommendation {
  id: string
  title: string
  effort: 'low' | 'medium' | 'high'
  tip: string
  saved_kg_period: number
  saved_kg_per_year: number
  saved_pct: number
}

export interface ToolCall {
  name: string
  args: Record<string, unknown>
  result: Record<string, unknown>
}

export interface ChatReply {
  conversation_id: string
  reply: string
  tool_calls: ToolCall[]
}

export interface Health {
  status: string
  auth_mode: 'dev' | 'firebase'
  agent_enabled: boolean
  document_import_enabled: boolean
  factors_version: string
}

export interface ImportItem {
  key: string
  quantity: number | null
  unit: string
  occurred_on: string | null
  description: string | null
  label: string | null
  category: Category | null
  kg_co2e: number | null
  confidence: number | null
  error: string | null
}

export interface ImportPreview {
  items: ImportItem[]
  valid_count: number
  total_kg_co2e: number
}

export interface DocumentPreview extends ImportPreview {
  document_type: string
  summary: string
  warnings: string[]
}

export interface NewActivity {
  key: string
  quantity: number
  unit: string
  occurred_on?: string
  description?: string
}

export type GoalStatus = 'achieved' | 'on_track' | 'behind' | 'not_enough_data'

export interface Goal {
  baseline_t_per_year: number
  target_t_per_year: number
  start_date: string
  target_date: string
}

export interface GoalProgress {
  goal: Goal
  status: GoalStatus
  current_t_per_year: number | null
  planned_t_per_year_today: number
  reduction_achieved_pct: number | null
  elapsed_pct: number
  days_left: number
  days_with_data: number
  series: { date: string; actual_t_per_year: number | null; planned_t_per_year: number }[]
}

export interface SetGoal {
  target_date: string
  reduction_pct?: number
  target_t_per_year?: number
  baseline_t_per_year?: number
}

export interface WeeklyInsights {
  week_start: string
  week_end: string
  this_week_kg: number
  last_week_kg: number
  change_kg: number
  change_pct: number | null
  days_logged_this_week: number
  by_category: { category: Category; this_week_kg: number; last_week_kg: number; change_kg: number }[]
  top_activity: { key: string; label: string; kg_co2e: number; share: number } | null
  highlights: string[]
}

export interface Scenario {
  kind: 'switch' | 'reduce'
  from_key: string
  to_key?: string
  fraction: number
  days?: number
}

export interface ScenarioResult {
  description: string
  baseline_kg: number
  scenario_kg: number
  saved_kg: number
  saved_pct: number
  saved_kg_per_year: number
  days: number
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}
  // FormData sets its own multipart boundary header
  if (typeof init?.body === 'string') headers['Content-Type'] = 'application/json'
  const token = await getIdToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`/api${path}`, { ...init, headers })
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = await res.json()
      const d = body.detail
      message = typeof d === 'string' ? d : (d?.message ?? JSON.stringify(d))
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) })

const upload = <T>(path: string, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return request<T>(path, { method: 'POST', body: form })
}

export const api = {
  health: () => request<Health>('/health'),
  factors: (region: string) => request<Factor[]>(`/factors?region=${encodeURIComponent(region)}`),
  createUser: (name: string, kind: UserKind, region: string) => post<User>('/users', { name, kind, region }),
  getUser: (id: string) => request<User>(`/users/${id}`),
  me: () => request<User>('/me'),
  activities: (id: string, days: number) => request<Activity[]>(`/users/${id}/activities?days=${days}`),
  logActivity: (id: string, a: NewActivity) => post<Activity>(`/users/${id}/activities`, a),
  logActivities: (id: string, activities: NewActivity[]) =>
    post<Activity[]>(`/users/${id}/activities/batch`, { activities }),
  importCsv: (id: string, file: File) => upload<ImportPreview>(`/users/${id}/import/csv`, file),
  importDocument: (id: string, file: File) => upload<DocumentPreview>(`/users/${id}/import/document`, file),
  csvTemplateUrl: '/api/import/csv-template',
  deleteActivity: (id: string, activityId: number) =>
    request<void>(`/users/${id}/activities/${activityId}`, { method: 'DELETE' }),
  summary: (id: string, days: number) => request<Summary>(`/users/${id}/summary?days=${days}`),
  timeseries: (id: string, days: number) => request<DailyPoint[]>(`/users/${id}/timeseries?days=${days}`),
  recommendations: (id: string, days: number) =>
    request<{ recommendations: Recommendation[] }>(`/users/${id}/recommendations?days=${days}&top_n=5`),
  goal: (id: string) => request<GoalProgress | { goal: null }>(`/users/${id}/goal`),
  setGoal: (id: string, g: SetGoal) => request<GoalProgress>(`/users/${id}/goal`, { method: 'PUT', body: JSON.stringify(g) }),
  deleteGoal: (id: string) => request<void>(`/users/${id}/goal`, { method: 'DELETE' }),
  weeklyInsights: (id: string) => request<WeeklyInsights>(`/users/${id}/insights/weekly`),
  simulate: (id: string, s: Scenario) => post<ScenarioResult>(`/users/${id}/simulate`, s),
  chat: (userId: string, message: string, conversationId?: string) =>
    post<ChatReply>('/chat', { user_id: userId, message, conversation_id: conversationId }),
}
