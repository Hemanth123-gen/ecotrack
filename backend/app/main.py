"""HTTP API. Run with: uvicorn app.main:app --reload"""

import mimetypes
import os
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field

from .agent import AgentReply, CarbonAgent, Toolbox
from .auth import AuthError, FirebaseVerifier, RateLimiter, bearer_token
from .config import Settings, get_settings
from .engine import Activity, DailyPoint, FactorNotFound, UnitError, daily_series
from .ingest import (
    CSV_TEMPLATE,
    CsvImportError,
    DocumentError,
    DocumentExtractor,
    ImportItem,
    parse_csv,
    preview_item,
)
from .ingest.documents import MAX_BYTES as MAX_DOCUMENT_BYTES
from .store import NotFound, StoredActivity, Store, User, UserKind


class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: UserKind = "individual"
    region: str = "IN"


class ChatRequest(BaseModel):
    user_id: str
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


class LogActivityRequest(BaseModel):
    key: str
    quantity: float = Field(ge=0)
    unit: str
    occurred_on: str | None = None
    description: str | None = None


class BatchActivitiesRequest(BaseModel):
    activities: list[LogActivityRequest] = Field(min_length=1, max_length=1000)


class SetGoalRequest(BaseModel):
    target_date: str
    reduction_pct: float | None = Field(None, gt=0, lt=100)
    target_t_per_year: float | None = Field(None, gt=0)
    baseline_t_per_year: float | None = Field(None, gt=0)


class SimulateRequest(BaseModel):
    kind: Literal["switch", "reduce"]
    from_key: str
    to_key: str | None = None
    fraction: float = Field(ge=0, le=1)
    days: int = Field(30, ge=1, le=366)


MAX_CSV_BYTES = 1024 * 1024


def _gemini_client():
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):  # Excel on Windows often saves CSV as cp1252
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(400, "Couldn't decode the file; save it as UTF-8 CSV")


PUBLIC_PATHS = {"/api/health", "/api/factors", "/api/import/csv-template"}
CACHEABLE_PATHS = {"/api/factors", "/api/import/csv-template"}


def create_app(
    store: Store | None = None,
    agent: CarbonAgent | None = None,
    extractor: DocumentExtractor | None = None,
    verifier: FirebaseVerifier | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    hosted = os.getenv("K_SERVICE") or os.getenv("RENDER")  # set by Cloud Run / Render
    if settings.auth_mode == "dev" and hosted and not os.getenv("ALLOW_INSECURE_DEV_AUTH"):
        # Never serve everyone's data without sign-in by accident
        raise RuntimeError("Refusing to start on a hosting platform with AUTH_MODE=dev; set AUTH_MODE=firebase")
    store = store or Store(settings.database_url)
    if agent is None or extractor is None:
        client = _gemini_client()
        if client is not None:
            agent = agent or CarbonAgent(client, store, settings.gemini_model)
            extractor = extractor or DocumentExtractor(client, settings.gemini_model, store.factors)
    if settings.auth_mode == "firebase" and verifier is None:
        verifier = FirebaseVerifier(settings.firebase_project_id)
    chat_limiter = RateLimiter(settings.chat_requests_per_hour)
    document_limiter = RateLimiter(settings.document_requests_per_hour)

    def ensure_owner(request: Request, user_id: str) -> None:
        principal = request.state.principal
        if principal is None:  # dev mode
            return
        try:
            owner = store.owner_of(user_id)
        except NotFound as e:
            raise HTTPException(404, str(e))
        if owner != principal.uid:
            raise HTTPException(403, "This data belongs to another account")

    def authenticate(request: Request) -> None:
        """Runs for every route: verifies the caller and that /api/users/{user_id}/... is theirs."""
        request.state.principal = None
        path = request.url.path
        if verifier is None or path in PUBLIC_PATHS or not path.startswith("/api/"):
            return  # the web app's static files are public; its data comes from /api
        token = bearer_token(request.headers.get("authorization"))
        if not token:
            raise HTTPException(401, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
        try:
            request.state.principal = verifier.verify(token)
        except AuthError as e:
            raise HTTPException(401, str(e), headers={"WWW-Authenticate": "Bearer"})
        if user_id := request.path_params.get("user_id"):
            ensure_owner(request, user_id)

    def rate_limit(limiter: RateLimiter, request: Request, user_id: str, what: str) -> None:
        key = request.state.principal.uid if request.state.principal else user_id
        if (retry_after := limiter.check(key)) is not None:
            raise HTTPException(
                429, f"Too many {what} requests; try again in {int(retry_after // 60) + 1} min",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

    app = FastAPI(title="EcoTrack Carbon Agent API", version="0.4.0", dependencies=[Depends(authenticate)])
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"],
        )

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        # Per-user API responses must never be cached by the Firebase Hosting CDN or the browser
        response = await call_next(request)
        if request.url.path.startswith("/api/") and request.url.path not in CACHEABLE_PATHS:
            response.headers["Cache-Control"] = "no-store"
        return response

    def toolbox(user_id: str) -> Toolbox:
        try:
            return Toolbox(store, user_id)
        except NotFound as e:
            raise HTTPException(404, str(e))

    def unwrap(result: dict) -> dict:
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "agent_enabled": agent is not None,
            "document_import_enabled": extractor is not None,
            "auth_mode": settings.auth_mode,
            "factors_version": store.factors.version,
        }

    @app.get("/api/factors")
    def factors(region: str = "IN"):
        return [f.model_dump() for f in store.factors.list(region)]

    @app.post("/api/users", response_model=User, status_code=201)
    def create_user(req: CreateUserRequest, request: Request):
        principal = request.state.principal
        if principal is None:
            return store.create_user(req.name, req.kind, req.region)
        # One profile per account: creating twice returns the existing profile
        return store.get_user_by_auth_uid(principal.uid) or store.create_user(
            req.name, req.kind, req.region, auth_uid=principal.uid,
        )

    @app.get("/api/me", response_model=User)
    def me(request: Request):
        principal = request.state.principal
        if principal is None:
            raise HTTPException(404, "No signed-in user in dev mode")
        user = store.get_user_by_auth_uid(principal.uid)
        if user is None:
            raise HTTPException(404, "No profile yet")
        return user

    @app.get("/api/users/{user_id}", response_model=User)
    def get_user(user_id: str):
        return toolbox(user_id).user

    @app.get("/api/users/{user_id}/activities", response_model=list[StoredActivity])
    def list_activities(user_id: str, days: int = Query(30, ge=1, le=366)):
        return store.list_activities(toolbox(user_id).user.id, days)

    @app.post("/api/users/{user_id}/activities", response_model=StoredActivity, status_code=201)
    def log_activity(user_id: str, req: LogActivityRequest):
        user = toolbox(user_id).user
        try:
            return store.add_activity(user.id, Activity(**req.model_dump(exclude_none=True), region=user.region))
        except (FactorNotFound, UnitError, ValueError) as e:
            raise HTTPException(400, str(e))

    @app.post("/api/users/{user_id}/activities/batch", response_model=list[StoredActivity], status_code=201)
    def log_activities_batch(user_id: str, req: BatchActivitiesRequest):
        """All-or-nothing: validate every row first so a bad row never leaves a half-saved import."""
        user = toolbox(user_id).user
        activities, errors = [], []
        for i, a in enumerate(req.activities):
            item = preview_item(a.model_dump(), user.region, store.factors)
            if item.error:
                errors.append({"index": i, "error": item.error})
            else:
                activities.append(Activity(**a.model_dump(exclude_none=True), region=user.region))
        if errors:
            raise HTTPException(400, {"message": f"{len(errors)} row(s) are invalid", "errors": errors})
        return [store.add_activity(user.id, a) for a in activities]

    @app.get("/api/import/csv-template")
    def csv_template():
        return PlainTextResponse(
            CSV_TEMPLATE,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="ecotrack-template.csv"'},
        )

    @app.post("/api/users/{user_id}/import/csv")
    def import_csv(user_id: str, file: UploadFile):
        """Parse and validate a CSV into a preview. Save with /activities/batch after review."""
        user = toolbox(user_id).user
        data = file.file.read(MAX_CSV_BYTES + 1)
        if len(data) > MAX_CSV_BYTES:
            raise HTTPException(400, "CSV is too large (max 1 MB)")
        try:
            items = parse_csv(_decode_text(data), user.region, store.factors)
        except CsvImportError as e:
            raise HTTPException(400, str(e))
        return _preview_response(items)

    @app.post("/api/users/{user_id}/import/document")
    def import_document(user_id: str, file: UploadFile, request: Request):
        """Read a bill/receipt/ticket with Gemini vision into a preview. Save with /activities/batch."""
        user = toolbox(user_id).user
        if extractor is None:
            raise HTTPException(503, "Bill scanning is disabled: set GEMINI_API_KEY in backend/.env and restart.")
        rate_limit(document_limiter, request, user_id, "bill scanning")
        mime = file.content_type or ""
        if mime in ("", "application/octet-stream"):
            mime = mimetypes.guess_type(file.filename or "")[0] or mime
        data = file.file.read(MAX_DOCUMENT_BYTES + 1)
        try:
            result = extractor.extract(data, mime, user.region)
        except DocumentError as e:
            raise HTTPException(400, str(e))
        except genai_errors.APIError as e:
            raise HTTPException(502, f"Gemini API error: {e.message or e}")
        return {**result.model_dump(mode="json"), **_preview_response(result.items)}

    @app.delete("/api/users/{user_id}/activities/{activity_id}", status_code=204)
    def delete_activity(user_id: str, activity_id: int):
        unwrap(toolbox(user_id).execute("delete_activity", {"activity_id": activity_id}))

    @app.get("/api/users/{user_id}/summary")
    def summary(user_id: str, days: int = Query(30, ge=1, le=366)):
        return unwrap(toolbox(user_id).execute("get_footprint_summary", {"days": days}))

    @app.get("/api/users/{user_id}/timeseries", response_model=list[DailyPoint])
    def timeseries(user_id: str, days: int = Query(30, ge=1, le=366)):
        return daily_series(store.emission_results(toolbox(user_id).user.id, days), days)

    @app.get("/api/users/{user_id}/recommendations")
    def recommendations(user_id: str, days: int = Query(30, ge=1, le=366), top_n: int = Query(5, ge=1, le=10)):
        return unwrap(toolbox(user_id).execute("get_recommendations", {"days": days, "top_n": top_n}))

    @app.get("/api/users/{user_id}/goal")
    def get_goal(user_id: str):
        """Goal with progress, or {"goal": null} when none is set."""
        return toolbox(user_id).execute("get_goal_progress", {})

    @app.put("/api/users/{user_id}/goal")
    def set_goal(user_id: str, req: SetGoalRequest):
        return unwrap(toolbox(user_id).execute("set_goal", req.model_dump(exclude_none=True)))

    @app.delete("/api/users/{user_id}/goal", status_code=204)
    def delete_goal(user_id: str):
        store.delete_goal(toolbox(user_id).user.id)

    @app.get("/api/users/{user_id}/insights/weekly")
    def insights(user_id: str):
        return toolbox(user_id).execute("get_weekly_insights", {})

    @app.post("/api/users/{user_id}/simulate")
    def simulate(user_id: str, req: SimulateRequest):
        return unwrap(toolbox(user_id).execute("simulate_scenario", req.model_dump(exclude_none=True)))

    @app.post("/api/chat", response_model=AgentReply)
    def chat(req: ChatRequest, request: Request):
        ensure_owner(request, req.user_id)
        if agent is None:
            raise HTTPException(503, "Chat is disabled: set GEMINI_API_KEY in backend/.env and restart.")
        rate_limit(chat_limiter, request, req.user_id, "chat")
        try:
            return agent.chat(req.user_id, req.message, req.conversation_id)
        except NotFound as e:
            raise HTTPException(404, str(e))
        except genai_errors.APIError as e:  # quota, bad key, model not found, outage
            raise HTTPException(502, f"Gemini API error: {e.message or e}")

    if (static_dir := os.getenv("STATIC_DIR")) and Path(static_dir, "index.html").is_file():
        _serve_frontend(app, Path(static_dir))
    return app


def _serve_frontend(app: FastAPI, root: Path) -> None:
    """Serve the built React app from this service (single-service deploys such as Render).

    Registered last so /api routes win; any other unknown path falls back to index.html for the SPA.
    """
    root = root.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = (root / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(file, headers={"Cache-Control": cache})
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})


def _preview_response(items: list[ImportItem]) -> dict:
    valid = [i for i in items if not i.error]
    return {
        "items": [i.model_dump(mode="json") for i in items],
        "valid_count": len(valid),
        "total_kg_co2e": sum(i.kg_co2e or 0 for i in valid),
    }


app = create_app()
