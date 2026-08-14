"""Native GoreeCloud Notes relational persistence model.

The schema represents GoreeCloud product concepts directly rather than mirroring
transitional Memos storage. Authentication uses separate credential and opaque
session tables so account identity remains independent from credential/session
material.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class TimestampMixin:
    """Shared creation/update timestamps for mutable records."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class User(TimestampMixin, Base):
    """A private GoreeCloud Notes account identity."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("char_length(username_normalized) > 0", name="ck_users_username_normalized_nonempty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    username_normalized: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))


class UserCredential(Base):
    """Password credential material isolated from the user identity record."""

    __tablename__ = "user_credentials"
    __table_args__ = (
        CheckConstraint("char_length(password_hash) > 0", name="ck_user_credentials_password_hash_nonempty"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthSession(Base):
    """Server-managed opaque browser session.

    Raw session and CSRF secrets are never persisted. Only SHA-256 digests are
    stored so a database disclosure does not immediately expose active browser
    credentials.
    """

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("char_length(token_hash) = 64", name="ck_auth_sessions_token_hash_length"),
        CheckConstraint("char_length(csrf_token_hash) = 64", name="ck_auth_sessions_csrf_hash_length"),
        Index("ix_auth_sessions_user_expires", "user_id", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class Notebook(TimestampMixin, Base):
    """A user-owned notebook with optional hierarchy."""

    __tablename__ = "notebooks"
    __table_args__ = (
        CheckConstraint("char_length(name) > 0", name="ck_notebooks_name_nonempty"),
        Index("ix_notebooks_owner_parent", "owner_id", "parent_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("notebooks.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


class Note(TimestampMixin, Base):
    """A user-owned native note.

    ``document`` is an application-owned structured document envelope. The
    envelope schema is intentionally not tied to a rich-text editor library.
    ``document_schema`` versions that contract independently, while
    ``content_version`` provides optimistic concurrency for editor autosave.
    """

    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(
            "state IN ('normal', 'archived', 'trashed')",
            name="ck_notes_state",
        ),
        CheckConstraint("document_schema > 0", name="ck_notes_document_schema_positive"),
        CheckConstraint("content_version > 0", name="ck_notes_content_version_positive"),
        Index("ix_notes_owner_state_updated", "owner_id", "state", "updated_at"),
        Index("ix_notes_owner_notebook", "owner_id", "notebook_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notebook_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("notebooks.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="", server_default=text("''"))
    document: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    document_schema: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="normal", server_default=text("'normal'")
    )
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Tag(TimestampMixin, Base):
    """A normalized, user-owned organizational tag."""

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("owner_id", "normalized_name", name="uq_tags_owner_normalized_name"),
        CheckConstraint("char_length(normalized_name) > 0", name="ck_tags_normalized_name_nonempty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)


class NoteTag(Base):
    """Many-to-many note/tag assignment with explicit ownership scope."""

    __tablename__ = "note_tags"
    __table_args__ = (
        Index("ix_note_tags_owner_tag", "owner_id", "tag_id"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    note_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Attachment(TimestampMixin, Base):
    """Metadata for externally stored attachment bytes."""

    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_attachments_size_nonnegative"),
        CheckConstraint("char_length(sha256) = 64", name="ck_attachments_sha256_length"),
        Index("ix_attachments_owner_note", "owner_id", "note_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    extra_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class NoteRevision(Base):
    """Immutable content snapshot for note history and recovery."""

    __tablename__ = "note_revisions"
    __table_args__ = (
        UniqueConstraint("note_id", "revision_number", name="uq_note_revisions_note_number"),
        UniqueConstraint("note_id", "content_version", name="uq_note_revisions_note_content_version"),
        CheckConstraint("revision_number > 0", name="ck_note_revisions_number_positive"),
        CheckConstraint("document_schema > 0", name="ck_note_revisions_document_schema_positive"),
        CheckConstraint("content_version > 0", name="ck_note_revisions_content_version_positive"),
        Index("ix_note_revisions_owner_note", "owner_id", "note_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    document: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    document_schema: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
