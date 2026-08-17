"""Owner-scoped internal note-link and backlink read API.

The portable structured document is the source of truth. ``note_links`` is a derived
PostgreSQL index maintained by migration-owned trigger logic and contains only same-owner
resolved targets, so relationship reads cannot cross account boundaries.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .auth import AuthContext, get_current_auth_context
from .database import get_db
from .models import Note, NoteLink

router = APIRouter(tags=["note-links"])


class LinkedNoteView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    state: str
    is_pinned: bool
    updated_at: datetime


class NoteLinksView(BaseModel):
    outgoing: list[LinkedNoteView]
    backlinks: list[LinkedNoteView]


def _require_owned_note(db: Session, *, owner_id: UUID, note_id: UUID) -> Note:
    note = db.scalar(select(Note).where(Note.id == note_id, Note.owner_id == owner_id))
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
    return note


@router.get("/notes/{note_id}/links", response_model=NoteLinksView)
def list_note_links(
    note_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> NoteLinksView:
    """Return resolved outgoing links and backlinks for one owned note.

    Only relationship rows carrying the authenticated owner ID are considered, and the
    destination/source note join repeats the owner predicate as defense in depth. Unresolved
    UUID references remain safely preserved in document content but are intentionally absent
    from this relationship view until a same-owner target exists.
    """

    _require_owned_note(db, owner_id=context.user.id, note_id=note_id)

    outgoing = list(
        db.scalars(
            select(Note)
            .join(
                NoteLink,
                and_(
                    NoteLink.target_note_id == Note.id,
                    NoteLink.owner_id == Note.owner_id,
                ),
            )
            .where(
                NoteLink.owner_id == context.user.id,
                NoteLink.source_note_id == note_id,
                Note.owner_id == context.user.id,
            )
            .order_by(Note.is_pinned.desc(), Note.updated_at.desc(), Note.id.asc())
        )
    )
    backlinks = list(
        db.scalars(
            select(Note)
            .join(
                NoteLink,
                and_(
                    NoteLink.source_note_id == Note.id,
                    NoteLink.owner_id == Note.owner_id,
                ),
            )
            .where(
                NoteLink.owner_id == context.user.id,
                NoteLink.target_note_id == note_id,
                Note.owner_id == context.user.id,
            )
            .order_by(Note.is_pinned.desc(), Note.updated_at.desc(), Note.id.asc())
        )
    )
    return NoteLinksView(
        outgoing=[LinkedNoteView.model_validate(item) for item in outgoing],
        backlinks=[LinkedNoteView.model_validate(item) for item in backlinks],
    )
