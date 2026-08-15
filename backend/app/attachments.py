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
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .auth import AuthContext, get_current_auth_context, require_csrf
from .config import get_settings
from .database import get_db
from .documents import SAFE_INLINE_IMAGE_MEDIA_TYPES, attachment_image_ids
from .models import Attachment, Note, NoteRevision, User

router = APIRouter(tags=["attachments"])
settings = get_settings()

# Preview and inline-image rendering intentionally share one passive-raster allowlist.
# Active document formats such as SVG/HTML and generic browser-renderable files stay on
# the ordinary download path until content sanitization and production scanning policy are
# separately approved.
SAFE_IMAGE_PREVIEW_MEDIA_TYPES = SAFE_INLINE_IMAGE_MEDIA_TYPES


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


def _attachment_is_referenced(db: Session, *, attachment: Attachment) -> bool:
    """Fail closed when current content or retained immutable history still uses bytes."""

    note = db.scalar(
        select(Note).where(
            Note.id == attachment.note_id,
            Note.owner_id == attachment.owner_id,
        )
    )
    if note is not None and attachment.id in attachment_image_ids(note.document):
        return True

    revision_documents = db.scalars(
        select(NoteRevision.document).where(
            NoteRevision.note_id == attachment.note_id,
            NoteRevision.owner_id == attachment.owner_id,
        )
    )
    return any(attachment.id in attachment_image_ids(document) for document in revision_documents)


def _enforce_owner_storage_quota(db: Session, *, owner_id: UUID, incoming_size: int) -> None:
    """Serialize per-owner quota decisions before attachment metadata is committed.

    The user identity row is the stable lock target. Concurrent uploads may stream to
    separate temporary files, but only one upload for an owner can make the final quota
    decision at a time. This prevents two requests from both observing the same stale
    usage total and committing past the configured owner quota.
    """

    quota_bytes = settings.attachment_user_quota_bytes
    if quota_bytes <= 0:
        return

    owner = db.scalar(select(User.id).where(User.id == owner_id).with_for_update())
    if owner is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")

    used_bytes = db.scalar(
        select(func.coalesce(func.sum(Attachment.size_bytes), 0)).where(Attachment.owner_id == owner_id)
    )
    if int(used_bytes or 0) + incoming_size > quota_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="attachment storage quota exceeded",
        )


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
    exclusively by the server and never derive from the filename. A configured owner
    quota is enforced after streaming and before the temporary file becomes durable.
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

        _enforce_owner_storage_quota(db, owner_id=context.user.id, incoming_size=size_bytes)
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
        db.rollback()
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
    """Delete unreferenced owner-authorized attachment bytes and metadata.

    Inline image references are durable document data. Milestone 0 therefore refuses to
    remove bytes while the current note or retained immutable revision history still points
    at them; revision-retention policy must be resolved before those bytes can be reclaimed.
    """

    attachment = _require_owned_attachment(db, owner_id=context.user.id, attachment_id=attachment_id)
    if _attachment_is_referenced(db, attachment=attachment):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="attachment is referenced by note content or retained revision history",
        )

    path = _storage_path(attachment.storage_key)
    try:
        path.unlink(missing_ok=True)
        db.delete(attachment)
        db.commit()
    except (OSError, SQLAlchemyError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="attachment deletion unavailable") from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)