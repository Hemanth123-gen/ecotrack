<#
.SYNOPSIS
  Deploy EcoTrack: API to Cloud Run, web app to Firebase Hosting. See DEPLOY.md first.

.DESCRIPTION
  Without -Execute this only checks prerequisites and prints the commands it would run.
  Secrets (GEMINI_API_KEY, DATABASE_URL) must already exist in Secret Manager; this script never
  handles their values.

.EXAMPLE
  .\deploy\deploy.ps1 -ProjectId my-ecotrack                 # dry run
  .\deploy\deploy.ps1 -ProjectId my-ecotrack -Execute        # deploy
  .\deploy\deploy.ps1 -ProjectId my-ecotrack -CloudSqlInstance my-ecotrack:asia-south1:ecotrack -Execute
#>
param(
    [Parameter(Mandatory)] [string] $ProjectId,
    [string] $Region = "asia-south1",
    [string] $Service = "ecotrack-api",
    [string] $GeminiModel = "gemini-2.5-flash",
    [string] $CloudSqlInstance = "",   # PROJECT:REGION:INSTANCE when using Cloud SQL
    [int] $MaxInstances = 3,
    [switch] $Execute
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Run([string] $cmd) {
    Write-Host "  $cmd" -ForegroundColor DarkGray
    if ($Execute) {
        Invoke-Expression $cmd
        if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $cmd" }
    }
}

Step "Checking tools"
foreach ($tool in "gcloud", "firebase", "npm") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is not installed. See DEPLOY.md > Prerequisites." }
}
if (-not (Test-Path "$root\frontend\.env.production")) {
    throw "frontend\.env.production is missing. Copy frontend\.env.example and fill in your Firebase web config."
}
if ((Get-Content "$root\frontend\.env.production" -Raw) -notmatch "VITE_FIREBASE_PROJECT_ID=$ProjectId\b") {
    Write-Warning "frontend\.env.production has a different VITE_FIREBASE_PROJECT_ID than -ProjectId $ProjectId"
}

Step "Project and APIs"
Run "gcloud config set project $ProjectId"
$apis = "run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com"
if ($CloudSqlInstance) { $apis += " sqladmin.googleapis.com" }
Run "gcloud services enable $apis"

Step "Secrets"
foreach ($secret in "gemini-api-key", "database-url") {
    if ($Execute) {
        gcloud secrets describe $secret --project $ProjectId *> $null
        if ($LASTEXITCODE -ne 0) { throw "Secret '$secret' not found. Create it as shown in DEPLOY.md > Secrets." }
    }
    Write-Host "  secret $secret" -ForegroundColor DarkGray
}
$projectNumber = if ($Execute) { gcloud projects describe $ProjectId --format "value(projectNumber)" } else { "PROJECT_NUMBER" }
$runSa = "$projectNumber-compute@developer.gserviceaccount.com"
foreach ($secret in "gemini-api-key", "database-url") {
    Run "gcloud secrets add-iam-policy-binding $secret --member serviceAccount:$runSa --role roles/secretmanager.secretAccessor --quiet"
}
if ($CloudSqlInstance) {
    Run "gcloud projects add-iam-policy-binding $ProjectId --member serviceAccount:$runSa --role roles/cloudsql.client --quiet"
}

Step "API -> Cloud Run ($Service, $Region)"
$deploy = @(
    "gcloud run deploy $Service",
    "--source `"$root\backend`"",
    "--region $Region",
    "--allow-unauthenticated",   # the app checks Firebase ID tokens itself
    "--max-instances $MaxInstances",
    "--memory 512Mi",
    "--timeout 120",
    "--set-env-vars `"AUTH_MODE=firebase,FIREBASE_PROJECT_ID=$ProjectId,GEMINI_MODEL=$GeminiModel,CORS_ORIGINS=`"",
    "--set-secrets `"GEMINI_API_KEY=gemini-api-key:latest,DATABASE_URL=database-url:latest`""
)
if ($CloudSqlInstance) { $deploy += "--add-cloudsql-instances $CloudSqlInstance" }
Run ($deploy -join " ")

Step "Web app -> Firebase Hosting"
Push-Location "$root\frontend"
try {
    Run "npm ci"
    Run "npm run build -- --mode production"
} finally { Pop-Location }
Push-Location $root
try { Run "firebase deploy --only hosting --project $ProjectId" } finally { Pop-Location }

Step "Smoke test"
$url = "https://$ProjectId.web.app/api/health"
if ($Execute) {
    $health = Invoke-RestMethod $url
    $health | Format-List
    if ($health.auth_mode -ne "firebase") { throw "API is not in firebase auth mode!" }
    if (-not $health.agent_enabled) { Write-Warning "Gemini is not enabled; check the gemini-api-key secret." }
    Write-Host "`nDeployed: https://$ProjectId.web.app" -ForegroundColor Green
} else {
    Write-Host "  GET $url" -ForegroundColor DarkGray
    Write-Host "`nDry run only. Re-run with -Execute to deploy." -ForegroundColor Yellow
}
