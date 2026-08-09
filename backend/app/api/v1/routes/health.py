from fastapi import APIRouter

from app.core.database import db_enabled

router = APIRouter()


@router.get("/health", tags=["Health"])
def health_check():
    body = {"status": "ok"}
    if db_enabled():
        body["database"] = "connected"
    return body
