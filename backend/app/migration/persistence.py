"""Persistent provenance for controlled imports into native GoreeCloud Notes.

Migration provenance is intentionally separate from ordinary note fields. It preserves
source identities and the normalized source record even when current native behavior does
not yet have a first-class equivalent for every transitional concept.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class MigrationImport(Base):
    """One owner-scoped import checkpoint from a validated external source."""

    __tablename__ = "migration_imports"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "provider",
            "source_export_sha256",
            name="uq_migration_imports_owner_provider_source",
        ),
        CheckConstraint("char_length(source_export_sha256) = 64", name="ck_migration_imports_source_sha256"),
        CheckConstraint("char_length(manifest_sha256) = 64", name="ck_migration_imports_manifest_sha256"),
        CheckConstraint("char_length(evidence_sha256) = 64", name="ck_migration_imports_evidence_sha256"),
        CheckConstraint("source_note_count >= 0", name="ck_migration_imports_source_note_count"),
        CheckConstraint("imported_note_count >= 0", name="ck_migration_imports_imported_note_count"),
        Index("ix_migration_imports_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    source_export_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_note_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_note_count: Mapped[int] = mapped_column(Integer, nullable=False)
    conversion_profile: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MigrationNoteRecord(Base):
    """Exact normalized source record tied to its created native note."""

    __tablename__ = "migration_note_records"
    __table_args__ = (
        UniqueConstraint("import_id", "source_name", name="uq_migration_note_records_import_source"),
        UniqueConstraint("import_id", "note_id", name="uq_migration_note_records_import_note"),
        CheckConstraint("source_order >= 0", name="ck_migration_note_records_source_order"),
        CheckConstraint("char_length(record_sha256) = 64", name="ck_migration_note_records_record_sha256"),
        Index("ix_migration_note_records_owner_import", "owner_id", "import_id"),
        Index("ix_migration_note_records_owner_note", "owner_id", "note_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    import_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("migration_imports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_name: Mapped[str] = mapped_column(String(512), nullable=False)
    source_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)
    record_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_record: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
