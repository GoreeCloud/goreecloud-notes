"""Authenticated browser delivery for verified native library exports.

The administrative CLI remains the offline/operator export path. This router exposes the same
verified owner-scoped bundle to an authenticated browser session without persisting a second
server-side export copy after delivery completes.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from .auth import AuthContext, require_csrf
from .config import get_settings
from .database import get_db
from .portability import ExportError
from .portability_migration import export_user_library_with_provenance

router = APIRouter(tags=["portability"])


def _cleanup_export_directory(path: Path) -> None:
    """Best-effort removal after a download finishes or export generation fails."""

    shutil.rmtree(path, ignore_errors=True)


def _download_filename(now: datetime | None = None) -> str:
    """Return a deterministic, user-input-free attachment filename for browser downloads."""

    timestamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"goreecloud-notes-library-{timestamp}.zip"


@router.post("/exports/library", response_class=FileResponse)
def download_library_export(
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> FileResponse:
    """Build, verify, deliver, and then remove one owner-scoped portable ZIP bundle.

    POST plus the existing double-submit CSRF boundary is intentional. The application does
    not retain the generated archive as durable server state: it is created in a private temporary
    directory, independently verified by the shared portability layer, streamed to the client,
    and deleted by a response background task.
    """

    settings = get_settings()
    temporary_directory = Path(tempfile.mkdtemp(prefix="goreecloud-notes-export-"))
    output_path = temporary_directory / "library.zip"

    try:
        result = export_user_library_with_provenance(
            db,
            owner=context.user,
            attachment_root=Path(settings.attachment_root),
            output_path=output_path,
            overwrite=False,
        )
    except ExportError:
        _cleanup_export_directory(temporary_directory)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="library export could not be completed because stored data failed export validation",
            headers={"Cache-Control": "no-store"},
        ) from None
    except Exception:
        _cleanup_export_directory(temporary_directory)
        raise

    if result.output_path != output_path or not output_path.is_file():
        _cleanup_export_directory(temporary_directory)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="library export could not be completed",
            headers={"Cache-Control": "no-store"},
        )

    return FileResponse(
        path=output_path,
        media_type="application/zip",
        filename=_download_filename(),
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "X-GoreeCloud-Export-SHA256": result.sha256,
        },
        background=BackgroundTask(_cleanup_export_directory, temporary_directory),
    )
