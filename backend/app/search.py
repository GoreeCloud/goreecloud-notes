"""Owner-scoped PostgreSQL full-text search for GoreeCloud Notes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from .auth import AuthContext, get_current_auth_context
from .database import get_db
from .models import Note, Notebook, NoteTag, Tag
from .workspace import NoteState, NoteView

router = APIRouter(tags=["search"])


def _require_owned_filter(
    db: Session,
    *,
    owner_id: UUID,
    notebook_id: UUID | None,
    tag_id: UUID | None,
) -> None:
    """Reject foreign or nonexistent organization identifiers opaquely."""

    if notebook_id is not None:
        notebook = db.scalar(
            select(Notebook.id).where(
                Notebook.id == notebook_id,
                Notebook.owner_id == owner_id,
            )
        )
        if notebook is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notebook not found")

    if tag_id is not None:
        tag = db.scalar(
            select(Tag.id).where(
                Tag.id == tag_id,
                Tag.owner_id == owner_id,
            )
        )
        if tag is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tag not found")


@router.get("/search/notes", response_model=list[NoteView])
def search_notes(
    query: str = Query(alias="q", min_length=1, max_length=200),
    note_state: NoteState = Query(default="normal", alias="state"),
    notebook_id: UUID | None = None,
    tag_id: UUID | None = None,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> list[Note]:
    """Search one user's notes with PostgreSQL's indexed text-search engine.

    The ``simple`` text-search configuration is intentionally language-neutral at
    this foundation stage. Titles receive weight A and all string values in the
    application-owned structured document receive weight B. ``websearch_to_tsquery``
    accepts forgiving web-style user input without exposing raw tsquery syntax.
    """

    search_query = query.strip()
    if not search_query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="search query is required",
        )

    _require_owned_filter(
        db,
        owner_id=context.user.id,
        notebook_id=notebook_id,
        tag_id=tag_id,
    )

    ts_query = func.websearch_to_tsquery(
        literal_column("'simple'::regconfig"),
        search_query,
    )
    rank = func.ts_rank(Note.search_vector, ts_query)

    statement = select(Note).where(
        Note.owner_id == context.user.id,
        Note.state == note_state,
        Note.search_vector.op("@@")(ts_query),
    )

    if notebook_id is not None:
        statement = statement.where(Note.notebook_id == notebook_id)

    if tag_id is not None:
        statement = statement.join(
            NoteTag,
            (NoteTag.note_id == Note.id) & (NoteTag.owner_id == context.user.id),
        ).where(NoteTag.tag_id == tag_id)

    statement = statement.order_by(
        Note.is_pinned.desc(),
        rank.desc(),
        Note.updated_at.desc(),
    )
    return list(db.scalars(statement))
