import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_context import request_id_var
from app.api.v1.routes import documents, health, query

configure_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
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
