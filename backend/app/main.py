"""FastAPI entry point for native GoreeCloud Notes."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings

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
    """Return a non-sensitive process health response."""

    return {"status": "ok", "service": "goreecloud-notes-api"}


@api.get("/meta", tags=["system"])
def api_metadata() -> dict[str, str]:
    """Expose the stable API identity without sensitive environment data."""

    return {
        "product": "GoreeCloud Notes",
        "api_version": "v1",
        "status": "native-foundation",
    }


app.include_router(api)
