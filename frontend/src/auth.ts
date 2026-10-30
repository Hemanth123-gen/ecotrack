// Firebase Authentication (Google sign-in). Enabled only when the VITE_FIREBASE_* env vars are set;
// otherwise the app runs in dev mode with no sign-in. The SDK is loaded lazily so dev builds stay small.
import type { Auth } from 'firebase/auth'

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string | undefined,
}

export const authEnabled = Boolean(config.apiKey && config.projectId)

export interface AuthUser {
  uid: string
  name: string | null
  email: string | null
}

let authPromise: Promise<Auth> | null = null

function getAuthInstance(): Promise<Auth> {
  authPromise ??= (async () => {
    const [{ initializeApp }, { getAuth }] = await Promise.all([import('firebase/app'), import('firebase/auth')])
    return getAuth(initializeApp(config))
  })()
  return authPromise
}

/** Fresh ID token for API calls (the SDK refreshes it before expiry), or null when signed out. */
export async function getIdToken(): Promise<string | null> {
  if (!authEnabled) return null
  const auth = await getAuthInstance()
  return auth.currentUser ? auth.currentUser.getIdToken() : null
}

export async function signInWithGoogle(): Promise<void> {
  const auth = await getAuthInstance()
  const { GoogleAuthProvider, signInWithPopup } = await import('firebase/auth')
  await signInWithPopup(auth, new GoogleAuthProvider())
}

export async function signOut(): Promise<void> {
  if (!authEnabled) return
  await (await getAuthInstance()).signOut()
}

export async function onAuthChange(cb: (user: AuthUser | null) => void): Promise<() => void> {
  const auth = await getAuthInstance()
  const { onAuthStateChanged } = await import('firebase/auth')
  return onAuthStateChanged(auth, (u) => cb(u ? { uid: u.uid, name: u.displayName, email: u.email } : null))
}
