import { localBackendEnabled } from '../localApi'
import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import { api, type ToolCall, type User } from '../api'
import { formatKg } from '../format'
import { load, save } from '../storage'

interface Message {
  role: 'user' | 'assistant' | 'error'
  text: string
  toolCalls?: ToolCall[]
}

interface ChatState {
  conversationId?: string
  messages: Message[]
}

export interface AskRequest {
  id: number
  text: string
}

const MUTATING_TOOLS = new Set(['log_activities', 'delete_activity', 'set_goal'])

const SUGGESTIONS = [
  'I drove 25 km to work in my petrol car and had chicken biryani for lunch',
  'My electricity bill this month was 240 units and we used one LPG cylinder',
  'How much CO₂ is a return flight from Mumbai to Delhi?',
  'Where does most of my footprint come from, and what should I change first?',
  'Help me set a realistic goal to cut my footprint',
]

function describe(call: ToolCall): string {
  const r = call.result as Record<string, any>
  if (r.error) return `${call.name.replaceAll('_', ' ')} failed`
  switch (call.name) {
    case 'log_activities':
      return `Logged ${r.saved?.length ?? 0} · ${formatKg(r.total_kg_co2e ?? 0)}`
    case 'estimate_emissions':
      return `Estimated ${formatKg(r.total_kg_co2e ?? 0)}`
    case 'simulate_scenario':
      return `Simulated −${formatKg(r.saved_kg_per_year ?? 0)}/yr`
    case 'get_footprint_summary':
      return 'Read your summary'
    case 'get_recommendations':
      return 'Ranked actions'
    case 'list_recent_activities':
      return 'Checked your log'
    case 'delete_activity':
      return 'Deleted an entry'
    case 'set_goal':
      return `Goal set: ${(r.goal?.target_t_per_year ?? 0).toFixed(2)} t/yr`
    case 'get_goal_progress':
      return 'Checked your goal'
    case 'get_weekly_insights':
      return 'Compared weeks'
    default:
      return call.name
  }
}

export function ChatPanel({ user, onDataChanged, ask }: { user: User; onDataChanged: () => void; ask: AskRequest | null }) {
  const storageKey = `ecotrack.chat.${user.id}`
  const [state, setState] = useState<ChatState>(() => load(storageKey, { messages: [] }))
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const [agentEnabled, setAgentEnabled] = useState<boolean | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stateRef = useRef(state)
  stateRef.current = state

  useEffect(() => {
    api.health().then((h) => setAgentEnabled(h.agent_enabled)).catch(() => setAgentEnabled(false))
  }, [])

  useEffect(() => save(storageKey, state), [storageKey, state])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [state.messages.length, pending])

  async function send(text: string) {
    const message = text.trim()
    if (!message || pending) return
    setInput('')
    setPending(true)
    setState((s) => ({ ...s, messages: [...s.messages, { role: 'user', text: message }] }))
    try {
      const reply = await api.chat(user.id, message, stateRef.current.conversationId)
      setState((s) => ({
        conversationId: reply.conversation_id,
        messages: [...s.messages, { role: 'assistant', text: reply.reply, toolCalls: reply.tool_calls }],
      }))
      if (reply.tool_calls.some((c) => MUTATING_TOOLS.has(c.name) && !('error' in c.result))) onDataChanged()
    } catch (e) {
      setState((s) => ({ ...s, messages: [...s.messages, { role: 'error', text: e instanceof Error ? e.message : 'Request failed' }] }))
    } finally {
      setPending(false)
    }
  }

  // Questions sent from elsewhere in the app (e.g. "Ask the assistant how")
  useEffect(() => {
    if (ask) void send(ask.text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ask?.id])

  return (
    <div className="flex min-h-0 w-full flex-col bg-surface">
      <div className="flex items-center border-b border-line px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">Carbon assistant</h2>
          <p className="text-xs text-muted">Powered by Gemini · numbers from a vetted factor database</p>
        </div>
        {state.messages.length > 0 && (
          <button onClick={() => setState({ messages: [] })} className="ml-auto rounded-lg px-2 py-1 text-xs text-ink-2 hover:bg-surface-2">
            New chat
          </button>
        )}
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4" aria-live="polite">
        {agentEnabled === false && (
          <div className="rounded-xl border border-line bg-surface-2 p-3 text-sm text-ink-2">
            <span className="font-medium text-ink">Chat is off.</span>{' '}
            {localBackendEnabled ? (
              <>
                This in-browser demo has no Gemini API key, which the AI assistant needs. Everything else (logging,
                imports, goals, insights, what-if) works fully.
              </>
            ) : (
              <>
                Add <code>GEMINI_API_KEY</code> to <code>backend/.env</code> and restart the backend. The dashboard
                and quick log still work.
              </>
            )}
          </div>
        )}

        {state.messages.length === 0 && (
          <div>
            <p className="text-sm text-ink-2">
              Hi {user.name.split(' ')[0]}! Tell me what you did and I'll measure it, or ask how to cut your footprint.
            </p>
            <div className="mt-3 space-y-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  disabled={!agentEnabled || pending}
                  className="block w-full rounded-xl border border-line px-3 py-2 text-left text-sm hover:bg-surface-2 disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {state.messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="ml-8 rounded-2xl rounded-br-sm bg-accent px-3 py-2 text-sm text-accent-ink">
              {m.text}
            </div>
          ) : m.role === 'error' ? (
            <div key={i} className="rounded-xl border border-line px-3 py-2 text-sm text-critical">
              {m.text}
            </div>
          ) : (
            <div key={i} className="mr-4">
              {!!m.toolCalls?.length && (
                <div className="mb-1.5 flex flex-wrap gap-1.5">
                  {m.toolCalls.map((c, j) => (
                    <span
                      key={j}
                      title={JSON.stringify(c.args)}
                      className={`rounded-full border border-line px-2 py-0.5 text-xs ${'error' in c.result ? 'text-critical' : 'text-ink-2'}`}
                    >
                      {describe(c)}
                    </span>
                  ))}
                </div>
              )}
              <div className="prose-chat rounded-2xl rounded-bl-sm bg-surface-2 px-3 py-2 text-sm">
                <Markdown>{m.text}</Markdown>
              </div>
            </div>
          ),
        )}

        {pending && (
          <div className="mr-4 inline-flex gap-1 rounded-2xl bg-surface-2 px-3 py-3" aria-label="Assistant is thinking">
            {[0, 1, 2].map((d) => (
              <span key={d} className="size-1.5 animate-bounce rounded-full bg-muted" style={{ animationDelay: `${d * 150}ms` }} />
            ))}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          void send(input)
        }}
        className="flex items-end gap-2 border-t border-line p-3"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void send(input)
            }
          }}
          rows={2}
          maxLength={4000}
          disabled={!agentEnabled}
          placeholder={agentEnabled ? 'e.g. Took the metro 12 km and had dal rice' : 'Chat unavailable'}
          className="min-h-0 flex-1 resize-none rounded-xl border border-line bg-page px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent disabled:opacity-50"
        />
        <button
          disabled={!agentEnabled || pending || !input.trim()}
          className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  )
}
