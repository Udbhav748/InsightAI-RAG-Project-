"""Registers global FastAPI exception handlers.

Domain errors (AppError and subclasses) are translated into their mapped
HTTP status code. Anything else is logged and returned as a generic 500,
so unexpected exceptions never leak internals to the client.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "request_failed",
            extra={
                "extra_fields": {
                    "path": request.url.path,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                    "taxonomy_category": exc.taxonomy_category,
                }
            },
        )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            exc_info=exc,
            extra={"extra_fields": {"path": request.url.path}},
        )
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error."}
        )
