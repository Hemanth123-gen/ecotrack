# EcoTrack — Carbon Footprint AI Agent

An AI agent that **analyzes**, **understands** and **reduces** carbon footprints for individuals and
organizations. Gemini handles the conversation and decides which tools to call; a deterministic Python
engine does every calculation, so the agent never makes up numbers.

## Status
- [x] Phase 1: emissions engine (factors, units, analysis, what-if, recommendations)
- [x] Phase 2: Gemini agent, tools, SQLite store, FastAPI
- [x] Phase 3: React + Vite dashboard (chat, charts, quick log)
- [x] Phase 4: bill/receipt scanning (Gemini vision) and CSV import, both with a review step
- [x] Phase 5: reduction goals with a glide path, weekly insights, what-if simulator
- [x] Phase 6: deployment-ready: Firebase Auth, Postgres, Docker, Cloud Run + Firebase Hosting (see [DEPLOY.md](DEPLOY.md))

## Backend setup
```bash
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env        # then put your GEMINI_API_KEY in .env
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```
Interactive API docs: http://localhost:8000/docs

Optional demo data: `.venv\Scripts\python.exe -m scripts.seed_demo` (prints the user id to load in the app).

## Frontend setup
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. Vite proxies `/api` to the backend on port 8000, so start the backend first.
Stack: React 19, TypeScript, Tailwind v4, Recharts. Chart colors follow a colorblind-validated categorical
palette with separate light and dark steps; layout uses container queries so it adapts when the chat panel
is open.

## How the agent works
```
user message ─► Gemini (system prompt + factor catalog + 7 tool declarations)
                  │ function_call(s)
                  ▼
               Toolbox ─► engine (calculate / summarize / simulate / recommend) ─► SQLite
                  │ function_response(s)
                  ▼
               Gemini ─► final answer (numbers taken only from tool results)
```
Tools: `log_activities`, `estimate_emissions`, `get_footprint_summary`, `list_recent_activities`,
`delete_activity`, `simulate_scenario`, `get_recommendations`.

## API
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Status, and whether the agent is enabled |
| GET | `/api/factors?region=IN` | Emission factor catalog |
| POST | `/api/users` | Create a user `{name, kind: individual\|organization, region}` |
| GET/POST | `/api/users/{id}/activities` | List or log activities manually |
| DELETE | `/api/users/{id}/activities/{aid}` | Remove an activity |
| GET | `/api/users/{id}/timeseries?days=30` | Zero-filled daily totals by category |
| GET | `/api/users/{id}/summary?days=30` | Breakdown, hotspots, scopes, benchmarks |
| GET | `/api/users/{id}/recommendations` | Ranked reduction actions |
| POST | `/api/users/{id}/activities/batch` | Save many activities, all-or-nothing |
| POST | `/api/users/{id}/import/csv` | CSV file → validated preview (saves nothing) |
| POST | `/api/users/{id}/import/document` | Bill/receipt/ticket photo or PDF → preview via Gemini vision |
| GET | `/api/import/csv-template` | Downloadable CSV template |
| GET/PUT/DELETE | `/api/users/{id}/goal` | Goal with progress, set `{target_date, reduction_pct \| target_t_per_year}`, or remove |
| GET | `/api/users/{id}/insights/weekly` | Last 7 days vs the 7 before, with highlights |
| POST | `/api/users/{id}/simulate` | What-if: `{kind: switch\|reduce, from_key, to_key?, fraction}` |
| POST | `/api/chat` | `{user_id, message, conversation_id?}` → reply plus a trace of tool calls |

## Goals and annual estimates
- **Annual estimates** are extrapolated from the days you've actually been logging (from your first logged
  day in the window, minimum one week), so new users aren't credited with empty days.
- **Goals:** the baseline is your pace over the last 30 days (needs 7+ logged days, or enter a known annual
  footprint). Progress is checked against a straight-line glide path from baseline to target. The status
  is achieved, on track, behind, or not enough data.
- **Weekly insights** compare the last 7 days with the previous 7, computed deterministically. The agent's
  `get_weekly_insights` tool narrates them in chat.

## Importing data
Both import paths produce a **preview** that the user reviews, edits and ticks before anything is saved.
- **Bill scanning:** Gemini reads quantities only (kWh units, litres, cylinders, route distances) into a JSON
  schema restricted to known factor keys. It's told to ignore rupee amounts and never to copy personal
  details. Low-confidence values are flagged, and the engine still does all the emissions math.
- **CSV:** headers like `date, activity, quantity, unit, description`; accepts factor keys or labels
  ("Petrol car"), YYYY-MM-DD or DD/MM/YYYY dates, and UTF-8 or Excel cp1252 encoding.

## Configuration (backend env vars)
| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | none | Enables chat and bill scanning |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model id |
| `DATABASE_URL` | none | Postgres URL; if unset, SQLite at `DATABASE_PATH` (default `backend/carbon.db`) |
| `AUTH_MODE` | `dev` | `dev` (no sign-in, local only) or `firebase` (Google sign-in required) |
| `FIREBASE_PROJECT_ID` | none | Required for `AUTH_MODE=firebase` |
| `CHAT_REQUESTS_PER_HOUR` / `DOCUMENT_REQUESTS_PER_HOUR` | 60 / 20 | Per-account Gemini rate limits |

The frontend turns on Google sign-in when `VITE_FIREBASE_*` are set (see `frontend/.env.example`).

## Notes
- The emission factors in `backend/data/emission_factors.json` are approximate. Verify them against the
  latest CEA / DEFRA / IPCC editions before production use.
- Deployment, the security model and known gaps are in [DEPLOY.md](DEPLOY.md).
