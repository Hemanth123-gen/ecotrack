import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, type User } from './api'
import { authEnabled, onAuthChange, signOut, type AuthUser } from './auth'
import { ChatPanel, type AskRequest } from './components/ChatPanel'
import { Dashboard } from './components/Dashboard'
import { Leaf, Onboarding } from './components/Onboarding'
import { SignIn } from './components/SignIn'
import { load, save } from './storage'

const USER_KEY = 'ecotrack.userId'

/** Who is using the app: a Firebase account + its profile, or (dev mode) a profile id kept in localStorage. */
function useSession() {
  const [user, setUser] = useState<User | null>(null)
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(() => authEnabled || load<string | null>(USER_KEY, null) !== null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (authEnabled) return
    const id = load<string | null>(USER_KEY, null)
    if (!id) return
    api
      .getUser(id)
      .then(setUser)
      .catch((e) => {
        // Forget a user the backend no longer knows (e.g. the database was reset)
        if (e instanceof ApiError && e.status === 404) save(USER_KEY, null)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!authEnabled) return
    let unsubscribe: (() => void) | undefined
    let active = true
    onAuthChange(async (u) => {
      setAuthUser(u)
      setUser(null)
      setError(null)
      if (u) {
        setLoading(true)
        try {
          setUser(await api.me())
        } catch (e) {
          // 404 just means this account has no profile yet: show onboarding
          if (!(e instanceof ApiError && e.status === 404)) setError(e instanceof Error ? e.message : 'Sign-in failed')
        }
      }
      setLoading(false)
    }).then((unsub) => (active ? (unsubscribe = unsub) : unsub()))
    return () => {
      active = false
      unsubscribe?.()
    }
  }, [])

  const onCreated = (u: User) => {
    if (!authEnabled) save(USER_KEY, u.id)
    setUser(u)
  }

  const leave = async () => {
    if (authEnabled) await signOut()
    else save(USER_KEY, null)
    setUser(null)
  }

  return { user, authUser, loading, error, onCreated, leave }
}

export default function App() {
  const { user, authUser, loading, error, onCreated, leave } = useSession()
  const [refreshKey, setRefreshKey] = useState(0)
  const [mobileView, setMobileView] = useState<'dashboard' | 'chat'>('dashboard')

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), [])

  const [ask, setAsk] = useState<AskRequest | null>(null)
  const askAssistant = useCallback((text: string) => {
    setAsk((prev) => ({ id: (prev?.id ?? 0) + 1, text }))
    setMobileView('chat')
  }, [])

  if (loading) return <div className="min-h-screen grid place-items-center text-muted">Loading…</div>
  if (authEnabled && (!authUser || error)) return <SignIn error={error} onRetry={leave} />
  if (!user) return <Onboarding onCreated={onCreated} defaultName={authUser?.name ?? ''} />

  return (
    <div className="min-h-screen lg:h-screen lg:flex lg:flex-col">
      <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3 lg:px-6">
        <span className="flex items-center gap-2 text-accent">
          <Leaf />
          <span className="font-semibold tracking-tight text-ink">EcoTrack</span>
        </span>
        <span className="hidden text-sm text-muted sm:inline">
          {user.name} · {user.kind === 'organization' ? 'Organization' : 'Personal'} · {user.region}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <div className="flex rounded-lg border border-line p-0.5 text-sm lg:hidden" role="tablist">
            {(['dashboard', 'chat'] as const).map((v) => (
              <button
                key={v}
                role="tab"
                aria-selected={mobileView === v}
                onClick={() => setMobileView(v)}
                className={`rounded-md px-3 py-1 capitalize ${mobileView === v ? 'bg-surface-2 font-medium' : 'text-ink-2'}`}
              >
                {v}
              </button>
            ))}
          </div>
          <button onClick={leave} className="whitespace-nowrap rounded-lg px-2 py-1 text-sm text-ink-2 hover:bg-surface-2">
            {authEnabled ? 'Sign out' : 'Switch user'}
          </button>
        </div>
      </header>

      <div className="lg:flex lg:min-h-0 lg:flex-1">
        <main className={`${mobileView === 'dashboard' ? 'block' : 'hidden'} lg:block lg:flex-1 lg:overflow-y-auto`}>
          <Dashboard user={user} refreshKey={refreshKey} onChanged={refresh} onAsk={askAssistant} />
        </main>
        <aside
          className={`${mobileView === 'chat' ? 'flex' : 'hidden'} h-[calc(100dvh-57px)] lg:flex lg:h-auto lg:w-[420px] lg:shrink-0 lg:border-l lg:border-line`}
        >
          <ChatPanel key={user.id} user={user} onDataChanged={refresh} ask={ask} />
        </aside>
      </div>
    </div>
  )
}
