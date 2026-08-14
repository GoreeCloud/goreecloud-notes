"""FastAPI entry point for native GoreeCloud Notes."""

from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .attachments import router as attachments_router
from .auth import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    AuthContext,
    authenticate_user,
    clear_session_cookies,
    get_current_auth_context,
    issue_session,
    replace_user_password,
    require_csrf,
    revoke_session,
    set_session_cookies,
    verify_user_password,
)
from .config import get_settings
from .database import engine, get_db
from .search import router as search_router
from .workspace import router as workspace_router

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


class LoginRequest(BaseModel):
    """Credentials accepted by the private login endpoint."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class PasswordChangeRequest(BaseModel):
    """Authenticated credential rotation request."""

    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class CurrentUser(BaseModel):
    """Non-sensitive account identity returned to the authenticated client."""

    id: UUID
    username: str
    display_name: str


def _current_user(context: AuthContext) -> CurrentUser:
    return CurrentUser(
        id=context.user.id,
        username=context.user.username,
        display_name=context.user.display_name,
    )


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


@api.post("/auth/login", response_model=CurrentUser, tags=["authentication"])
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Create an opaque browser session for an existing private account."""

    user = authenticate_user(db, username=payload.username, password=payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid username or password",
        )

    issued = issue_session(db, user=user, settings=settings)
    db.commit()
    set_session_cookies(response, issued, settings)
    response.headers["Cache-Control"] = "no-store"
    return CurrentUser(id=user.id, username=user.username, display_name=user.display_name)


@api.get("/auth/me", response_model=CurrentUser, tags=["authentication"])
def me(
    response: Response,
    context: AuthContext = Depends(get_current_auth_context),
) -> CurrentUser:
    """Return the identity bound to the current opaque session."""

    response.headers["Cache-Control"] = "no-store"
    return _current_user(context)


@api.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT, tags=["authentication"])
def change_password(
    payload: PasswordChangeRequest,
    response: Response,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> Response:
    """Rotate the current user's password and revoke every browser session."""

    if not verify_user_password(db, user=context.user, password=payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="current password is incorrect",
        )
    if verify_user_password(db, user=context.user, password=payload.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="new password must differ from the current password",
        )

    try:
        replace_user_password(db, user=context.user, new_password=payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    db.commit()
    clear_session_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    response.headers["Cache-Control"] = "no-store"
    return response


@api.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["authentication"])
def logout(
    response: Response,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> Response:
    """Revoke the current server-side session and expire both browser cookies."""

    revoke_session(db, context)
    db.commit()
    clear_session_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    response.headers["Cache-Control"] = "no-store"
    return response


api.include_router(workspace_router)
api.include_router(search_router)
api.include_router(attachments_router)
app.include_router(api)
