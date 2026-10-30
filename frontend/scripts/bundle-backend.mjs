// Demo build step: pack the backend's Python package and data into dist/demo/backend.json for Pyodide,
// and write the CSV template as a static file (it's opened as a link, not fetched).
import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const backend = join(here, '..', '..', 'backend')
const dist = join(here, '..', 'dist')

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (name === '__pycache__') return []
    return statSync(path).isDirectory() ? walk(path) : [path]
  })
}

const files = {}
for (const path of [...walk(join(backend, 'app')), ...walk(join(backend, 'data'))]) {
  if (path.endsWith('.py') || path.endsWith('.json')) {
    files[relative(backend, path).replaceAll('\\', '/')] = readFileSync(path, 'utf8')
  }
}
mkdirSync(join(dist, 'demo'), { recursive: true })
writeFileSync(join(dist, 'demo', 'backend.json'), JSON.stringify(files))

const csvSource = readFileSync(join(backend, 'app', 'ingest', 'csv_import.py'), 'utf8')
const template = csvSource.match(/TEMPLATE = """([\s\S]*?)"""/)[1]
mkdirSync(join(dist, 'api', 'import'), { recursive: true })
writeFileSync(join(dist, 'api', 'import', 'csv-template'), template)

// Pure-Python wheels the backend needs beyond Pyodide's built-ins, pinned to versions compatible with
// Pyodide 0.27's typing-extensions and served from this site (no PyPI dependency at runtime).
const WHEELS = [
  'fastapi==0.115.6', 'starlette==0.41.3', 'anyio==4.8.0', 'sniffio==1.3.1', 'idna==3.10',
  'python-multipart==0.0.20', 'python-dotenv==1.0.1',
]
const wheelDir = join(dist, 'demo', 'wheels')
mkdirSync(wheelDir, { recursive: true })
execFileSync('python', ['-m', 'pip', 'download', '--quiet', '--no-deps', '--only-binary=:all:',
  '--python-version', '3.12', '--dest', wheelDir, ...WHEELS], { stdio: 'inherit' })
const wheels = readdirSync(wheelDir).filter((f) => f.endsWith('.whl'))
writeFileSync(join(dist, 'demo', 'wheels.json'), JSON.stringify(wheels))

console.log(`bundled ${Object.keys(files).length} backend files and ${wheels.length} wheels`)
