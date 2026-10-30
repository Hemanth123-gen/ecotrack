# Deploying EcoTrack

```
Browser ──► Firebase Hosting (React app, CDN)
               │  /api/**  (same origin, no CORS)
               ▼
            Cloud Run: ecotrack-api (FastAPI, asia-south1)
               │ verifies Firebase ID tokens      ├──► Gemini API (key from Secret Manager)
               ▼                                  │
            Postgres (Cloud SQL, or Neon/Supabase) ◄┘ DATABASE_URL from Secret Manager
```

The deploy script and this guide only cover a Google Cloud project you own. Everything below runs from
the `carbon-agent` folder in PowerShell.

## 1. Prerequisites (one-time)

1. A Firebase project with billing on the **Blaze** (pay-as-you-go) plan. Cloud Run and Hosting rewrites to
   Cloud Run need it. Create it at <https://console.firebase.google.com>. The Firebase project *is* a Google
   Cloud project, with the same ID.
2. Install and log in to the CLIs:
   - Google Cloud CLI: <https://cloud.google.com/sdk/docs/install>, then `gcloud auth login`
   - Firebase CLI: `npm install -g firebase-tools`, then `firebase login`
3. **Authentication:** Firebase console → Authentication → Sign-in method → enable **Google**.
   `PROJECT_ID.web.app` and `PROJECT_ID.firebaseapp.com` are authorized domains by default; add any custom
   domain you use.
4. **Web app config:** Firebase console → Project settings → *Your apps* → add a Web app, then copy its
   config into `frontend/.env.production` (template: `frontend/.env.example`). These values are public
   identifiers, not secrets.
5. Copy `.firebaserc.example` to `.firebaserc` and put your project ID in it.

## 2. Database

Pick one. The app creates its tables on first start.

**A. Cloud SQL for PostgreSQL** (stays inside Google Cloud; a smallest shared-core instance costs a few
dollars a month, so check current pricing):
```powershell
gcloud sql instances create ecotrack --database-version=POSTGRES_16 --edition=enterprise `
  --tier=db-f1-micro --region=asia-south1
gcloud sql databases create ecotrack --instance=ecotrack
gcloud sql users create ecotrack --instance=ecotrack --prompt-for-password
```
Your `DATABASE_URL` is then (Cloud Run connects over a Unix socket, not the public internet):
```
postgresql://ecotrack:PASSWORD@/ecotrack?host=/cloudsql/PROJECT_ID:asia-south1:ecotrack
```
Pass `-CloudSqlInstance PROJECT_ID:asia-south1:ecotrack` to the deploy script.

**B. Hosted Postgres with a free tier** (Neon, Supabase). Create a database in a nearby region and use the
connection string it gives you, e.g. `postgresql://user:pass@host/db?sslmode=require`.

## 3. Secrets

Secret values go into Secret Manager, never into files or the deploy command. Run each command, paste the
value, then press **Enter, Ctrl+Z, Enter** to finish:
```powershell
gcloud secrets create gemini-api-key --replication-policy=automatic --data-file=-
gcloud secrets create database-url  --replication-policy=automatic --data-file=-
```
To rotate a secret later: `gcloud secrets versions add gemini-api-key --data-file=-`, then redeploy.

## 4. Deploy

```powershell
.\deploy\deploy.ps1 -ProjectId PROJECT_ID              # dry run: checks and prints every command
.\deploy\deploy.ps1 -ProjectId PROJECT_ID -Execute     # add -CloudSqlInstance ... for option A
```
The script will:
1. Enable Cloud Run, Cloud Build, Artifact Registry and Secret Manager (plus Cloud SQL Admin for option A).
2. Let the Cloud Run service account read the two secrets (and connect to Cloud SQL).
3. Build `backend/Dockerfile` in Cloud Build and deploy `ecotrack-api` with `AUTH_MODE=firebase`,
   max 3 instances and 512 MiB.
4. Build the frontend and deploy it to Firebase Hosting.
5. Call `https://PROJECT_ID.web.app/api/health` and check that auth is on.

If Firebase reports that the region doesn't support Hosting rewrites, deploy with `-Region us-central1`
and change `region` in `firebase.json` to match.

## 5. After deploying

- Open `https://PROJECT_ID.web.app`, sign in with Google, create your profile and log something.
- **Budget alert:** Billing → Budgets & alerts → create a monthly budget. Gemini calls are rate-limited
  per account (`CHAT_REQUESTS_PER_HOUR=60`, `DOCUMENT_REQUESTS_PER_HOUR=20`; set them as env vars on the
  service to change). The limit is per instance, so the real ceiling is up to 3× that.
- **Logs:** `gcloud run services logs read ecotrack-api --region asia-south1`

## Security model

- **Every user-scoped API call** needs a Firebase ID token. The API verifies its signature, audience,
  issuer and expiry against Google's public keys, then checks that the profile belongs to that account
  (403 otherwise). One profile per Google account.
- The API **refuses to start on Cloud Run with `AUTH_MODE=dev`**, so a misconfigured deploy can't expose
  everyone's data.
- API responses carry `Cache-Control: no-store`, so the Hosting CDN never caches one user's data for another.
- The container runs as a non-root user. Secrets come only from Secret Manager.
- Uploaded bills go to Gemini to be read and are **not stored**. Only the activities you confirm are saved.

## Not covered yet

- **Database migrations:** tables are created automatically and new columns are added by
  `Store._migrate`. Anything bigger should move to Alembic.
- **Account deletion / data export:** not built yet. Add these before collecting real users' data at scale.
- **Rate limits** are per instance and in memory; use Redis/Memorystore if you need exact global limits.
