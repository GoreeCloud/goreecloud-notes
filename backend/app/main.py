"""FastAPI entry point for native GoreeCloud Notes."""

import os
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
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
    list_active_user_sessions,
    replace_user_password,
    require_csrf,
    revoke_other_user_sessions,
    revoke_session,
    set_session_cookies,
    verify_user_password,
)
from .config import get_settings
from .database import engine, get_db
from .login_security import (
    check_login_rate_limit,
    record_login_failure,
    record_login_success,
    request_source,
)
from .note_links import router as note_links_router
from .portability_api import router as portability_router
from .search import router as search_router
from .security_headers import PrivateResponseHeadersMiddleware
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
app.add_middleware(PrivateResponseHeadersMiddleware, api_prefix=settings.api_prefix)

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


class BrowserSession(BaseModel):
    """Non-secret browser-session metadata safe for the owning account to review."""

    id: UUID
    created_at: datetime
    expires_at: datetime
    current: bool


class SessionRevocationResult(BaseModel):
    """Result of an account-scoped selective session revocation."""

    revoked: int


def _current_user(context: AuthContext) -> CurrentUser:
    return CurrentUser(
        id=context.user.id,
        username=context.user.username,
        display_name=context.user.display_name,
    )


def _login_error(status_code: int, detail: str, *, retry_after: int | None = None) -> HTTPException:
    headers = {"Cache-Control": "no-store"}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return HTTPException(status_code=status_code, detail=detail, headers=headers)


def _attachment_storage_ready() -> bool:
    """Check the configured attachment root without exposing its path or creating data."""

    root = Path(settings.attachment_root).expanduser()
    try:
        if root.is_symlink():
            return False
        resolved = root.resolve(strict=True)
    except (OSError, RuntimeError):
        return False

    if not resolved.is_dir():
        return False
    return os.access(resolved, os.R_OK | os.W_OK | os.X_OK)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Return a dependency-free, non-sensitive process liveness response."""

    return {"status": "ok", "service": "goreecloud-notes-api"}


@app.get("/ready", tags=["system"])
def readiness() -> dict[str, str]:
    """Report readiness only when required persistence dependencies are usable.

    The response intentionally exposes no database host, credential, attachment
    path, schema, or exception detail. Liveness remains available separately at
    ``/health`` so dependency failure can be distinguished from process failure.
    """

    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="service unavailable") from None

    if result != 1 or not _attachment_storage_ready():
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
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Create an opaque browser session with bounded abuse controls."""

    source = request_source(request, settings)
    preflight = check_login_rate_limit(
        db,
        source=source,
        username=payload.username,
        settings=settings,
    )
    if preflight.blocked:
        db.commit()
        raise _login_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "login temporarily unavailable",
            retry_after=preflight.retry_after_seconds,
        )

    user = authenticate_user(db, username=payload.username, password=payload.password)
    if user is None:
        failure = record_login_failure(
            db,
            source=source,
            username=payload.username,
            settings=settings,
        )
        db.commit()
        if failure.blocked:
            raise _login_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "login temporarily unavailable",
                retry_after=failure.retry_after_seconds,
            )
        raise _login_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid username or password",
        )

    record_login_success(db, source=source, username=payload.username)
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


@api.get("/auth/sessions", response_model=list[BrowserSession], tags=["authentication"])
def browser_sessions(
    response: Response,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> list[BrowserSession]:
    """List the owning account's active browser sessions without secret or device data."""

    response.headers["Cache-Control"] = "no-store"
    return [
        BrowserSession(
            id=session.id,
            created_at=session.created_at,
            expires_at=session.expires_at,
            current=session.id == context.session.id,
        )
        for session in list_active_user_sessions(db, context)
    ]


@api.post(
    "/auth/sessions/revoke-others",
    response_model=SessionRevocationResult,
    tags=["authentication"],
)
def revoke_other_sessions(
    response: Response,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> SessionRevocationResult:
    """Sign out every other browser session while preserving the current one."""

    revoked = revoke_other_user_sessions(db, context)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return SessionRevocationResult(revoked=revoked)


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
api.include_router(note_links_router)
api.include_router(portability_router)
app.include_router(api)
