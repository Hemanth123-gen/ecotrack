// Static demo build: run the real Python backend in the browser with Pyodide and answer /api fetches
// from it. Data lives in this browser (IndexedDB). Used only when VITE_LOCAL_BACKEND=1.
import bridge from './localApi.py?raw'

const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.27.2/full/'

export const localBackendEnabled = import.meta.env.VITE_LOCAL_BACKEND === '1'

/* eslint-disable @typescript-eslint/no-explicit-any */
export async function startLocalBackend(onStatus: (s: string) => void): Promise<void> {
  onStatus('Loading Python runtime…')
  const { loadPyodide } = await import(/* @vite-ignore */ `${PYODIDE_URL}pyodide.mjs`)
  const py: any = await loadPyodide({ indexURL: PYODIDE_URL })

  onStatus('Installing packages…')
  await py.loadPackage(['micropip', 'pydantic', 'sqlalchemy', 'sqlite3', 'ssl'])
  // Pinned pure-Python wheels served from this site (see scripts/bundle-backend.mjs)
  const wheels: string[] = await (await fetch('/demo/wheels.json')).json()
  await py.pyimport('micropip').install(
    wheels.map((w) => `${location.origin}/demo/wheels/${w}`),
    { deps: false },
  )

  onStatus('Loading the EcoTrack engine…')
  const files: Record<string, string> = await (await fetch('/demo/backend.json')).json()
  for (const [path, content] of Object.entries(files)) {
    py.FS.mkdirTree(`/srv/${path.split('/').slice(0, -1).join('/')}`)
    py.FS.writeFile(`/srv/${path}`, content)
  }

  // Persist the SQLite database across visits in IndexedDB
  py.FS.mkdirTree('/data')
  py.FS.mount(py.FS.filesystems.IDBFS, {}, '/data')
  const sync = (populate: boolean) =>
    new Promise<void>((resolve) => py.FS.syncfs(populate, () => resolve()))
  await sync(true)

  await py.runPythonAsync(bridge)
  const handle = py.globals.get('handle')

  const nativeFetch = window.fetch.bind(window)
  let queue: Promise<unknown> = Promise.resolve() // one request at a time, like the SQLite store expects

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(input instanceof Request ? input.url : String(input), location.href)
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return nativeFetch(input, init)

    const method = (init?.method ?? 'GET').toUpperCase()
    const headers: Record<string, string> = { ...(init?.headers as Record<string, string> | undefined) }
    let body = new Uint8Array()
    if (init?.body != null) {
      // Let the browser encode the body (incl. multipart boundaries for FormData)
      const req = new Request(url, { method, body: init.body as BodyInit })
      body = new Uint8Array(await req.arrayBuffer())
      const type = req.headers.get('content-type')
      if (type) headers['content-type'] = type
    }

    const run = async () => {
      // The bridge returns [status, headers, body] already converted to JS (to_js)
      const [status, respHeaders, respBody] = await handle(
        method, url.pathname, url.search.slice(1), JSON.stringify(headers), body,
      )
      if (method !== 'GET') await sync(false)
      return new Response(status === 204 ? null : respBody, { status, headers: respHeaders })
    }
    const next = queue.then(run, run)
    queue = next.catch(() => undefined)
    return next
  }
}
