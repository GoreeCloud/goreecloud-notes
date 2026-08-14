"""FastAPI entry point for native GoreeCloud Notes."""

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings
from .database import engine

settings = get_settings()

app = FastAPI(
    title="GoreeCloud Notes API",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)

api = APIRouter(prefix=settings.api_prefix)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Return a dependency-free, non-sensitive process liveness response."""

    return {"status": "ok", "service": "goreecloud-notes-api"}


@app.get("/ready", tags=["system"])
def readiness() -> dict[str, str]:
    """Report readiness only when PostgreSQL accepts a real query.

    The response intentionally exposes no database host, credential, schema, or
    exception detail. Liveness remains available separately at ``/health`` so
    dependency failure can be distinguished from process failure.
    """

    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="service unavailable") from None

    if result != 1:
        raise HTTPException(status_code=503, detail="service unavailable")

    return {"status": "ready", "service": "goreecloud-notes-api"}


@api.get("/meta", tags=["system"])
def api_metadata() -> dict[str, str]:
    """Expose the stable API identity without sensitive environment data."""

    return {
        "product": "GoreeCloud Notes",
        "api_version": "v1",
        "status": "native-foundation",
    }


app.include_router(api)
