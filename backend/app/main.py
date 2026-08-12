import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import db_enabled, init_db
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.metrics import RequestTimer, get_metrics
from app.core.request_context import request_id_var
from app.api.v1.routes import admin, auth, documents, health, metrics as metrics_routes, query
from app.services import s3_sync_service
from app.services.demo_seed_service import seed_if_empty
from app.services.tenant_service import seed_keys_from_settings
from app.services.usage_service import record_usage

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On the Lambda deployment (Settings.s3_sync_enabled), restore whatever
    # was last synced before anything else touches local disk — a no-op
    # everywhere else. Must run before query.get_vector_store() below,
    # which triggers a synchronous FAISSVectorStore().load() off whatever
    # is on disk at that point.
    s3_sync_service.download_all()

    # Bring the PostgreSQL schema up-to-date and mirror env API keys into
    # the DB (both no-ops when DATABASE_URL is unset). Then seed the vector
    # store — no-op whenever the store already has vectors (local dev with
    # a persisted docker-compose volume, restored from S3 sync above, or
    # any platform with real persistent storage) — only fires on a
    # genuinely empty store, e.g. Render's free tier or a fresh Lambda
    # environment with nothing synced yet. See demo_seed_service.py.
    init_db()
    seed_keys_from_settings()
    await seed_if_empty(query.get_vector_store())
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Generate (or propagate) an X-Request-ID for every request.

    Stored in request_id_var for the duration of the request so every log
    line emitted while handling it — including from error handlers —
    carries the same id automatically (see JSONFormatter in core/logging.py).
    Also echoed back as a response header so callers can correlate their
    own logs against the server's.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def usage_log_middleware(request: Request, call_next):
    """Record one usage_log row per request when PostgreSQL is configured.

    Registered after request_id_middleware, so it wraps it: when the
    finally block runs, request_id_var is set and the auth dependency has
    populated request.state.client_name/tenant_id for authenticated routes
    (absent for unauthenticated/failed requests — tenant_id stays null).
    Best-effort: a DB failure drops the log line, never the response.
    """
    if not db_enabled():
        return await call_next(request)

    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        record_usage(
            request_id=request_id_var.get() or request.headers.get("X-Request-ID") or "",
            tenant_id=getattr(request.state, "tenant_id", None),
            client_name=getattr(request.state, "client_name", None),
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            latency_ms=round(latency_ms, 2),
        )
    return response


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Record one http_requests_total + latency histogram per request.

    Lives in-app so a Prometheus-style scraper can pull live metrics from
    GET /metrics with nothing but this process running — the online
    counterpart to the offline log rollups (monitoring/log_aggregate.py).
    The error-taxonomy breakdown is recorded separately by
    error_handlers.py's record_error(); this middleware covers every
    response, healthy or not.

    Exceptions from call_next (e.g. a client disconnecting mid-stream) are
    recorded as a 500 so the request is never invisible to the scraper —
    the exception still propagates, as it would without this middleware.
    """
    timer = RequestTimer(get_metrics(), request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        timer.finish(500)
        raise
    timer.finish(response.status_code)
    return response


register_exception_handlers(app)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(admin.router)
app.include_router(metrics_routes.router)
