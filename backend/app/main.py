import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_context import request_id_var
from app.api.v1.routes import documents, health, query
from app.services.demo_seed_service import seed_if_empty

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # No-op whenever the vector store already has vectors (local dev with
    # a persisted docker-compose volume, or any platform with real
    # persistent storage) — only fires on a genuinely empty store, e.g.
    # Render's free tier, which wipes local disk on every spin-down. See
    # demo_seed_service.py.
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


register_exception_handlers(app)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(query.router)
