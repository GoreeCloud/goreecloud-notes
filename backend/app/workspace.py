"""Authenticated GoreeCloud Notes workspace API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from unicodedata import normalize
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import AuthContext, get_current_auth_context, require_csrf
from .config import get_settings
from .database import get_db
from .models import Note, Notebook, NoteRevision, NoteTag, Tag

router = APIRouter(tags=["workspace"])
settings = get_settings()

NoteState = Literal["normal", "archived", "trashed"]


def empty_document() -> dict[str, object]:
    """Return the editor-independent Milestone 0 document envelope."""

    return {
        "format": "goreecloud.blocks",
        "version": 1,
        "blocks": [],
    }


def _clean_display_name(value: str) -> str:
    """Normalize Unicode and collapse whitespace without changing display case."""

    return " ".join(normalize("NFKC", value).strip().split())


def _normalized_name(value: str) -> str:
    return _clean_display_name(value).casefold()


class NotebookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: UUID | None = None


class NotebookPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: UUID | None = None
    sort_order: int | None = None


class NotebookView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parent_id: UUID | None
    name: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)


class TagPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)


class TagView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    normalized_name: str
    color: str | None
    created_at: datetime
    updated_at: datetime


class NoteCreate(BaseModel):
    title: str = Field(default="", max_length=512)
    document: dict[str, object] = Field(default_factory=empty_document)
    document_schema: int = Field(default=1, ge=1)
    notebook_id: UUID | None = None
    is_pinned: bool = False
    color: str | None = Field(default=None, max_length=32)


class NotePatch(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    document: dict[str, object] | None = None
    document_schema: int | None = Field(default=None, ge=1)
    expected_content_version: int | None = Field(default=None, ge=1)
    notebook_id: UUID | None = None
    state: NoteState | None = None
    is_pinned: bool | None = None
    color: str | None = Field(default=None, max_length=32)


class NoteView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    notebook_id: UUID | None
    title: str
    document: dict[str, object]
    document_schema: int
    content_version: int
    state: NoteState
    is_pinned: bool
    color: str | None
    created_at: datetime
    updated_at: datetime


class NoteRevisionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    revision_number: int
    content_version: int
    title: str
    document: dict[str, object]
    document_schema: int
    created_at: datetime
    change_summary: str | None


class RevisionRestoreRequest(BaseModel):
    expected_content_version: int = Field(ge=1)


def _owned_notebook(db: Session, *, owner_id: UUID, notebook_id: UUID) -> Notebook | None:
    return db.scalar(
        select(Notebook).where(
            Notebook.id == notebook_id,
            Notebook.owner_id == owner_id,
        )
    )


def _require_owned_notebook(db: Session, *, owner_id: UUID, notebook_id: UUID) -> Notebook:
    notebook = _owned_notebook(db, owner_id=owner_id, notebook_id=notebook_id)
    if notebook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notebook not found")
    return notebook


def _owned_tag(db: Session, *, owner_id: UUID, tag_id: UUID) -> Tag | None:
    return db.scalar(
        select(Tag).where(
            Tag.id == tag_id,
            Tag.owner_id == owner_id,
        )
    )


def _require_owned_tag(db: Session, *, owner_id: UUID, tag_id: UUID) -> Tag:
    tag = _owned_tag(db, owner_id=owner_id, tag_id=tag_id)
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tag not found")
    return tag


def _owned_note(db: Session, *, owner_id: UUID, note_id: UUID) -> Note | None:
    return db.scalar(
        select(Note).where(
            Note.id == note_id,
            Note.owner_id == owner_id,
        )
    )


def _require_owned_note(db: Session, *, owner_id: UUID, note_id: UUID) -> Note:
    note = _owned_note(db, owner_id=owner_id, note_id=note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
    return note


def _require_owned_revision(
    db: Session,
    *,
    owner_id: UUID,
    note_id: UUID,
    revision_id: UUID,
) -> NoteRevision:
    revision = db.scalar(
        select(NoteRevision).where(
            NoteRevision.id == revision_id,
            NoteRevision.note_id == note_id,
            NoteRevision.owner_id == owner_id,
        )
    )
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="revision not found")
    return revision


def _validate_notebook_owner(
    db: Session,
    *,
    owner_id: UUID,
    notebook_id: UUID | None,
) -> None:
    if notebook_id is None:
        return
    _require_owned_notebook(db, owner_id=owner_id, notebook_id=notebook_id)


def _validate_notebook_parent(
    db: Session,
    *,
    owner_id: UUID,
    notebook_id: UUID | None,
    parent_id: UUID | None,
) -> None:
    """Validate ownership and reject self/descendant notebook cycles."""

    if parent_id is None:
        return

    current = _require_owned_notebook(db, owner_id=owner_id, notebook_id=parent_id)
    visited: set[UUID] = set()
    while current is not None:
        if current.id in visited:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="notebook hierarchy contains a cycle",
            )
        visited.add(current.id)
        if notebook_id is not None and current.id == notebook_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="notebook cannot be its own descendant",
            )
        if current.parent_id is None:
            break
        current = _require_owned_notebook(
            db,
            owner_id=owner_id,
            notebook_id=current.parent_id,
        )


def _latest_revision(db: Session, *, note_id: UUID) -> NoteRevision | None:
    return db.scalar(
        select(NoteRevision)
        .where(NoteRevision.note_id == note_id)
        .order_by(NoteRevision.created_at.desc(), NoteRevision.revision_number.desc())
        .limit(1)
    )


def _should_snapshot(db: Session, *, note: Note) -> bool:
    latest = _latest_revision(db, note_id=note.id)
    if latest is None:
        return True
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.revision_min_interval_seconds)
    return latest.created_at <= cutoff


def _create_revision(
    db: Session,
    *,
    note: Note,
    change_summary: str | None = None,
) -> None:
    latest_number = db.scalar(
        select(func.max(NoteRevision.revision_number)).where(NoteRevision.note_id == note.id)
    )
    db.add(
        NoteRevision(
            owner_id=note.owner_id,
            note_id=note.id,
            revision_number=(latest_number or 0) + 1,
            content_version=note.content_version,
            title=note.title,
            document=note.document,
            document_schema=note.document_schema,
            change_summary=change_summary,
        )
    )


def _content_changed(note: Note, payload: NotePatch, fields: set[str]) -> bool:
    if "title" in fields and (payload.title or "") != note.title:
        return True
    if "document" in fields and (payload.document or empty_document()) != note.document:
        return True
    if (
        "document_schema" in fields
        and payload.document_schema is not None
        and payload.document_schema != note.document_schema
    ):
        return True
    return False


@router.get("/notebooks", response_model=list[NotebookView])
def list_notebooks(
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> list[Notebook]:
    return list(
        db.scalars(
            select(Notebook)
            .where(Notebook.owner_id == context.user.id)
            .order_by(Notebook.sort_order.asc(), Notebook.name.asc())
        )
    )


@router.post("/notebooks", response_model=NotebookView, status_code=status.HTTP_201_CREATED)
def create_notebook(
    payload: NotebookCreate,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> Notebook:
    name = _clean_display_name(payload.name)
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="notebook name is required")
    _validate_notebook_parent(
        db,
        owner_id=context.user.id,
        notebook_id=None,
        parent_id=payload.parent_id,
    )
    notebook = Notebook(owner_id=context.user.id, parent_id=payload.parent_id, name=name)
    db.add(notebook)
    db.commit()
    db.refresh(notebook)
    return notebook


@router.patch("/notebooks/{notebook_id}", response_model=NotebookView)
def update_notebook(
    notebook_id: UUID,
    payload: NotebookPatch,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> Notebook:
    notebook = _require_owned_notebook(db, owner_id=context.user.id, notebook_id=notebook_id)
    fields = payload.model_fields_set
    if "name" in fields:
        clean_name = _clean_display_name(payload.name or "")
        if not clean_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="notebook name is required")
        notebook.name = clean_name
    if "parent_id" in fields:
        _validate_notebook_parent(
            db,
            owner_id=context.user.id,
            notebook_id=notebook.id,
            parent_id=payload.parent_id,
        )
        notebook.parent_id = payload.parent_id
    if "sort_order" in fields and payload.sort_order is not None:
        notebook.sort_order = payload.sort_order
    db.commit()
    db.refresh(notebook)
    return notebook


@router.delete("/notebooks/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notebook(
    notebook_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> None:
    notebook = _require_owned_notebook(db, owner_id=context.user.id, notebook_id=notebook_id)
    db.delete(notebook)
    db.commit()


@router.get("/tags", response_model=list[TagView])
def list_tags(
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> list[Tag]:
    return list(db.scalars(select(Tag).where(Tag.owner_id == context.user.id).order_by(Tag.name.asc())))


@router.post("/tags", response_model=TagView, status_code=status.HTTP_201_CREATED)
def create_tag(
    payload: TagCreate,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> Tag:
    name = _clean_display_name(payload.name)
    normalized_name = _normalized_name(payload.name)
    if not name or not normalized_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="tag name is required")
    tag = Tag(owner_id=context.user.id, name=name, normalized_name=normalized_name, color=payload.color)
    db.add(tag)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="tag already exists") from None
    db.refresh(tag)
    return tag


@router.patch("/tags/{tag_id}", response_model=TagView)
def update_tag(
    tag_id: UUID,
    payload: TagPatch,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> Tag:
    tag = _require_owned_tag(db, owner_id=context.user.id, tag_id=tag_id)
    fields = payload.model_fields_set
    if "name" in fields:
        name = _clean_display_name(payload.name or "")
        normalized_name = _normalized_name(payload.name or "")
        if not name or not normalized_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="tag name is required")
        tag.name = name
        tag.normalized_name = normalized_name
    if "color" in fields:
        tag.color = payload.color
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="tag already exists") from None
    db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> None:
    tag = _require_owned_tag(db, owner_id=context.user.id, tag_id=tag_id)
    db.delete(tag)
    db.commit()


@router.get("/notes", response_model=list[NoteView])
def list_notes(
    note_state: NoteState = Query(default="normal", alias="state"),
    notebook_id: UUID | None = None,
    tag_id: UUID | None = None,
    query: str | None = Query(default=None, alias="q", max_length=200),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> list[Note]:
    statement = select(Note).where(Note.owner_id == context.user.id, Note.state == note_state)
    if notebook_id is not None:
        _validate_notebook_owner(db, owner_id=context.user.id, notebook_id=notebook_id)
        statement = statement.where(Note.notebook_id == notebook_id)
    if tag_id is not None:
        _require_owned_tag(db, owner_id=context.user.id, tag_id=tag_id)
        statement = statement.join(
            NoteTag,
            (NoteTag.note_id == Note.id) & (NoteTag.owner_id == context.user.id),
        ).where(NoteTag.tag_id == tag_id)
    if query and query.strip():
        statement = statement.where(Note.title.ilike(f"%{query.strip()}%"))
    statement = statement.order_by(Note.is_pinned.desc(), Note.updated_at.desc())
    return list(db.scalars(statement))


@router.post("/notes", response_model=NoteView, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreate,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> Note:
    _validate_notebook_owner(db, owner_id=context.user.id, notebook_id=payload.notebook_id)
    note = Note(
        owner_id=context.user.id,
        notebook_id=payload.notebook_id,
        title=payload.title,
        document=payload.document,
        document_schema=payload.document_schema,
        is_pinned=payload.is_pinned,
        color=payload.color,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.get("/notes/{note_id}", response_model=NoteView)
def get_note(
    note_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> Note:
    return _require_owned_note(db, owner_id=context.user.id, note_id=note_id)


@router.get("/notes/{note_id}/tags", response_model=list[TagView])
def list_note_tags(
    note_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> list[Tag]:
    _require_owned_note(db, owner_id=context.user.id, note_id=note_id)
    return list(
        db.scalars(
            select(Tag)
            .join(NoteTag, (NoteTag.tag_id == Tag.id) & (NoteTag.owner_id == context.user.id))
            .where(NoteTag.note_id == note_id, Tag.owner_id == context.user.id)
            .order_by(Tag.name.asc())
        )
    )


@router.put("/notes/{note_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def assign_note_tag(
    note_id: UUID,
    tag_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> None:
    _require_owned_note(db, owner_id=context.user.id, note_id=note_id)
    _require_owned_tag(db, owner_id=context.user.id, tag_id=tag_id)
    existing = db.get(NoteTag, {"owner_id": context.user.id, "note_id": note_id, "tag_id": tag_id})
    if existing is None:
        db.add(NoteTag(owner_id=context.user.id, note_id=note_id, tag_id=tag_id))
        db.commit()


@router.delete("/notes/{note_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_note_tag(
    note_id: UUID,
    tag_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> None:
    _require_owned_note(db, owner_id=context.user.id, note_id=note_id)
    _require_owned_tag(db, owner_id=context.user.id, tag_id=tag_id)
    db.execute(
        delete(NoteTag).where(
            NoteTag.owner_id == context.user.id,
            NoteTag.note_id == note_id,
            NoteTag.tag_id == tag_id,
        )
    )
    db.commit()


@router.get("/notes/{note_id}/revisions", response_model=list[NoteRevisionView])
def list_note_revisions(
    note_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_current_auth_context),
) -> list[NoteRevision]:
    _require_owned_note(db, owner_id=context.user.id, note_id=note_id)
    return list(
        db.scalars(
            select(NoteRevision)
            .where(NoteRevision.owner_id == context.user.id, NoteRevision.note_id == note_id)
            .order_by(NoteRevision.revision_number.desc())
        )
    )


@router.post(
    "/notes/{note_id}/revisions/{revision_id}/restore",
    response_model=NoteView,
)
def restore_note_revision(
    note_id: UUID,
    revision_id: UUID,
    payload: RevisionRestoreRequest,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> Note:
    """Restore historical note content without rewriting immutable history.

    A restore is a new content write. The caller must provide the content version
    it read, stale restores fail with 409, and the current content is always
    snapshotted before a historical revision replaces it. Metadata such as
    notebook, tags, state, pinning, and color is intentionally not changed.
    """

    note = _require_owned_note(db, owner_id=context.user.id, note_id=note_id)
    revision = _require_owned_revision(
        db,
        owner_id=context.user.id,
        note_id=note.id,
        revision_id=revision_id,
    )

    if payload.expected_content_version != note.content_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="note changed in another session; reload before restoring",
        )

    if (
        revision.title == note.title
        and revision.document == note.document
        and revision.document_schema == note.document_schema
    ):
        return note

    _create_revision(
        db,
        note=note,
        change_summary=f"Pre-restore snapshot before restoring revision {revision.revision_number}",
    )
    note.title = revision.title
    note.document = revision.document
    note.document_schema = revision.document_schema
    note.content_version += 1

    db.commit()
    db.refresh(note)
    return note


@router.patch("/notes/{note_id}", response_model=NoteView)
def update_note(
    note_id: UUID,
    payload: NotePatch,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> Note:
    """Update one owned note with optimistic content concurrency.

    Content edits require the version read by the client. A stale version returns
    409 instead of silently overwriting a newer editor state. Revisions are
    immutable snapshots and are coalesced by time so autosave does not create a
    snapshot for every keystroke.
    """

    note = _require_owned_note(db, owner_id=context.user.id, note_id=note_id)
    fields = payload.model_fields_set

    if "notebook_id" in fields:
        _validate_notebook_owner(db, owner_id=context.user.id, notebook_id=payload.notebook_id)

    content_changed = _content_changed(note, payload, fields)
    if content_changed:
        if payload.expected_content_version is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="content version is required for note edits",
            )
        if payload.expected_content_version != note.content_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="note changed in another session; reload before saving",
            )
        if _should_snapshot(db, note=note):
            _create_revision(db, note=note)
        note.content_version += 1

    if "title" in fields:
        note.title = payload.title or ""
    if "document" in fields:
        note.document = payload.document or empty_document()
    if "document_schema" in fields and payload.document_schema is not None:
        note.document_schema = payload.document_schema
    if "notebook_id" in fields:
        note.notebook_id = payload.notebook_id
    if "state" in fields and payload.state is not None:
        note.state = payload.state
    if "is_pinned" in fields and payload.is_pinned is not None:
        note.is_pinned = payload.is_pinned
    if "color" in fields:
        note.color = payload.color

    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def trash_note(
    note_id: UUID,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(require_csrf),
) -> None:
    note = _require_owned_note(db, owner_id=context.user.id, note_id=note_id)
    note.state = "trashed"
    db.commit()
