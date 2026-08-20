"""Add persistent migration provenance records.

Revision ID: 0006_migration_provenance
Revises: 0005_login_abuse_controls
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_migration_provenance"
down_revision: str | None = "0005_login_abuse_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "migration_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("source_export_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_exported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_note_count", sa.Integer(), nullable=False),
        sa.Column("imported_note_count", sa.Integer(), nullable=False),
        sa.Column("conversion_profile", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "char_length(source_export_sha256) = 64",
            name="ck_migration_imports_source_sha256",
        ),
        sa.CheckConstraint(
            "char_length(manifest_sha256) = 64",
            name="ck_migration_imports_manifest_sha256",
        ),
        sa.CheckConstraint(
            "char_length(evidence_sha256) = 64",
            name="ck_migration_imports_evidence_sha256",
        ),
        sa.CheckConstraint("source_note_count >= 0", name="ck_migration_imports_source_note_count"),
        sa.CheckConstraint("imported_note_count >= 0", name="ck_migration_imports_imported_note_count"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "provider",
            "source_export_sha256",
            name="uq_migration_imports_owner_provider_source",
        ),
    )
    op.create_index(
        "ix_migration_imports_owner_id",
        "migration_imports",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_migration_imports_owner_created",
        "migration_imports",
        ["owner_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "migration_note_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("source_name", sa.String(length=512), nullable=False),
        sa.Column("source_uid", sa.String(length=255), nullable=True),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column("record_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_record", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_order >= 0", name="ck_migration_note_records_source_order"),
        sa.CheckConstraint(
            "char_length(record_sha256) = 64",
            name="ck_migration_note_records_record_sha256",
        ),
        sa.ForeignKeyConstraint(["import_id"], ["migration_imports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_id", "note_id", name="uq_migration_note_records_import_note"),
        sa.UniqueConstraint(
            "import_id",
            "source_name",
            name="uq_migration_note_records_import_source",
        ),
    )
    op.create_index(
        "ix_migration_note_records_import_id",
        "migration_note_records",
        ["import_id"],
        unique=False,
    )
    op.create_index(
        "ix_migration_note_records_note_id",
        "migration_note_records",
        ["note_id"],
        unique=False,
    )
    op.create_index(
        "ix_migration_note_records_owner_id",
        "migration_note_records",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_migration_note_records_owner_import",
        "migration_note_records",
        ["owner_id", "import_id"],
        unique=False,
    )
    op.create_index(
        "ix_migration_note_records_owner_note",
        "migration_note_records",
        ["owner_id", "note_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_migration_note_records_owner_note", table_name="migration_note_records")
    op.drop_index("ix_migration_note_records_owner_import", table_name="migration_note_records")
    op.drop_index("ix_migration_note_records_owner_id", table_name="migration_note_records")
    op.drop_index("ix_migration_note_records_note_id", table_name="migration_note_records")
    op.drop_index("ix_migration_note_records_import_id", table_name="migration_note_records")
    op.drop_table("migration_note_records")
    op.drop_index("ix_migration_imports_owner_created", table_name="migration_imports")
    op.drop_index("ix_migration_imports_owner_id", table_name="migration_imports")
    op.drop_table("migration_imports")
