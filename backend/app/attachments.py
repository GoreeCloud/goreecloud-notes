"""Private attachment storage and authorization for GoreeCloud Notes."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .auth import AuthContext, get_current_auth_context, require_csrf
from .config import get_settings
from .database import get_db
from .models import Attachment, Note

router = APIRouter(tags=["attachments"])
settings = get_settings()

# Milestone 0 previews intentionally allow only common raster image formats. Active
# document formats such as SVG/HTML and generic browser-renderable files stay on the
# ordinary download path until content-sanitization and production scanning policy are
# separately approved.
SAFE_IMAGE_PREVIEW_MEDIA_TYPES = frozenset(
    {
        "image/avif",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)


class AttachmentView(BaseModel):
    """Non-sensitive attachment metadata exposed to an authorized owner."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    note_id: UUID
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    updated_at: datetime


def _require_owned_note(db: Session, *, owner_id: UUID, note_id: UUID) -> Note:
    note = db.scalar(select(Note).where(Note.id == note_id, Note.owner_id == owner_id))
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
    return note


def _require_owned_attachment(
    db: Session,
    *,
    owner_id: UUID,
    attachment_id: UUID,
) -> Attachment:
    attachment = db.scalar(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.owner_id == owner_id,
        )
    )
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="attachment not found")
    return attachment


def _clean_filename(value: str) -> str:
    """Reject path-bearing names while preserving the user's basename."""

    cleaned = value.strip()
    if not cleaned or len(cleaned) > 512:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid filename")
    if Path(cleaned).name != cleaned or "/" in cleaned or "\\" in cleaned or cleaned in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid filename")
    if "\x00" in cleaned:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid filename")
    return cleaned


def _storage_path(storage_key: str) -> Path:
    """Resolve an internally generated key beneath the configured attachment root."""

    root = Path(settings.attachment_root).expanduser().resolve()
    candidate = (root / storage_key).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="invalid attachment storage key") from exc
    return candidate


def _require_attachment_path(attachment: Attachment) -> Path:
    """Resolve persisted attachment bytes or report storage unavailability."""

    path = _storage_path(attachment.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="attachment bytes unavailable")
    return path


@router.get("/notes/{note_id}/attachments", response_model=list[AttachmentView])
def list_attachments(
    note_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> list[Attachment]:
    """List attachment metadata only for a note owned by the current user."""

    _require_owned_note(db, owner_id=context.user.id, note_id=note_id)
    return list(
        db.scalars(
            select(Attachment)
            .where(Attachment.owner_id == context.user.id, Attachment.note_id == note_id)
            .order_by(Attachment.created_at.asc(), Attachment.id.asc())
        )
    )


@router.post(
    "/notes/{note_id}/attachments",
    response_model=AttachmentView,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    note_id: UUID,
    request: Request,
    filename: str = Query(min_length=1, max_length=512),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> Attachment:
    """Stream one attachment into owner-scoped private filesystem storage.

    The client-supplied filename is metadata only. Filesystem locations are generated
    exclusively by the server and never derive from the filename.
    """

    _require_owned_note(db, owner_id=context.user.id, note_id=note_id)
    clean_filename = _clean_filename(filename)
    media_type = (request.headers.get("content-type") or "application/octet-stream").split(";", 1)[0].strip()
    if not media_type or len(media_type) > 255:
        media_type = "application/octet-stream"

    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > settings.attachment_max_bytes:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="attachment exceeds size limit")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid content length") from None

    attachment_id = uuid4()
    storage_key = f"{context.user.id}/{note_id}/{attachment_id}"
    final_path = _storage_path(storage_key)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = final_path.with_name(f".{final_path.name}.{uuid4().hex}.part")

    size_bytes = 0
    digest = hashlib.sha256()
    try:
        with temporary_path.open("xb") as target:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size_bytes += len(chunk)
                if size_bytes > settings.attachment_max_bytes:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="attachment exceeds size limit")
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())

        if size_bytes == 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="empty attachments are not accepted")

        os.replace(temporary_path, final_path)
        attachment = Attachment(
            id=attachment_id,
            owner_id=context.user.id,
            note_id=note_id,
            filename=clean_filename,
            media_type=media_type,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
            storage_key=storage_key,
            extra_metadata={},
        )
        db.add(attachment)
        db.commit()
        db.refresh(attachment)
        return attachment
    except HTTPException:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    except (OSError, SQLAlchemyError) as exc:
        db.rollback()
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="attachment storage unavailable") from exc


@router.get("/attachments/{attachment_id}")
def download_attachment(
    attachment_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> FileResponse:
    """Return attachment bytes only to their owner using the download path."""

    attachment = _require_owned_attachment(db, owner_id=context.user.id, attachment_id=attachment_id)
    path = _require_attachment_path(attachment)

    return FileResponse(
        path,
        media_type=attachment.media_type,
        filename=attachment.filename,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/attachments/{attachment_id}/preview")
def preview_attachment(
    attachment_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> FileResponse:
    """Return an inline-safe raster-image preview only to the attachment owner.

    Preview authorization is identical to ordinary attachment download authorization.
    The initial preview allowlist deliberately excludes SVG and non-image document types
    so adding previews does not silently create an active-content rendering surface.
    """

    attachment = _require_owned_attachment(db, owner_id=context.user.id, attachment_id=attachment_id)
    if attachment.media_type.casefold() not in SAFE_IMAGE_PREVIEW_MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="attachment type is not eligible for inline preview",
        )
    path = _require_attachment_path(attachment)

    return FileResponse(
        path,
        media_type=attachment.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Cross-Origin-Resource-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> Response:
    """Delete owner-authorized attachment bytes and metadata."""

    attachment = _require_owned_attachment(db, owner_id=context.user.id, attachment_id=attachment_id)
    path = _storage_path(attachment.storage_key)
    try:
        path.unlink(missing_ok=True)
        db.delete(attachment)
        db.commit()
    except (OSError, SQLAlchemyError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="attachment deletion unavailable") from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
