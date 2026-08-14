"""Create the initial native GoreeCloud Notes relational schema.

Revision ID: 0001_native_notes_schema
Revises:
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_native_notes_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("username_normalized", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "char_length(username_normalized) > 0",
            name="ck_users_username_normalized_nonempty",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username_normalized"),
    )

    op.create_table(
        "notebooks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("char_length(name) > 0", name="ck_notebooks_name_nonempty"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["notebooks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notebooks_owner_id", "notebooks", ["owner_id"], unique=False)
    op.create_index("ix_notebooks_owner_parent", "notebooks", ["owner_id", "parent_id"], unique=False)

    op.create_table(
        "notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("notebook_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=512), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "document",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("document_schema", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("state", sa.String(length=16), server_default=sa.text("'normal'"), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("state IN ('normal', 'archived', 'trashed')", name="ck_notes_state"),
        sa.CheckConstraint("document_schema > 0", name="ck_notes_document_schema_positive"),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notes_owner_id", "notes", ["owner_id"], unique=False)
    op.create_index("ix_notes_owner_notebook", "notes", ["owner_id", "notebook_id"], unique=False)
    op.create_index("ix_notes_owner_state_updated", "notes", ["owner_id", "state", "updated_at"], unique=False)

    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("normalized_name", sa.String(length=128), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "char_length(normalized_name) > 0",
            name="ck_tags_normalized_name_nonempty",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "normalized_name", name="uq_tags_owner_normalized_name"),
    )
    op.create_index("ix_tags_owner_id", "tags", ["owner_id"], unique=False)

    op.create_table(
        "note_tags",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("owner_id", "note_id", "tag_id"),
    )
    op.create_index("ix_note_tags_owner_tag", "note_tags", ["owner_id", "tag_id"], unique=False)

    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column(
            "extra_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("size_bytes >= 0", name="ck_attachments_size_nonnegative"),
        sa.CheckConstraint("char_length(sha256) = 64", name="ck_attachments_sha256_length"),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_attachments_owner_id", "attachments", ["owner_id"], unique=False)
    op.create_index("ix_attachments_owner_note", "attachments", ["owner_id", "note_id"], unique=False)

    op.create_table(
        "note_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("document_schema", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.CheckConstraint("revision_number > 0", name="ck_note_revisions_number_positive"),
        sa.CheckConstraint(
            "document_schema > 0",
            name="ck_note_revisions_document_schema_positive",
        ),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("note_id", "revision_number", name="uq_note_revisions_note_number"),
    )
    op.create_index("ix_note_revisions_owner_id", "note_revisions", ["owner_id"], unique=False)
    op.create_index("ix_note_revisions_owner_note", "note_revisions", ["owner_id", "note_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_note_revisions_owner_note", table_name="note_revisions")
    op.drop_index("ix_note_revisions_owner_id", table_name="note_revisions")
    op.drop_table("note_revisions")

    op.drop_index("ix_attachments_owner_note", table_name="attachments")
    op.drop_index("ix_attachments_owner_id", table_name="attachments")
    op.drop_table("attachments")

    op.drop_index("ix_note_tags_owner_tag", table_name="note_tags")
    op.drop_table("note_tags")

    op.drop_index("ix_tags_owner_id", table_name="tags")
    op.drop_table("tags")

    op.drop_index("ix_notes_owner_state_updated", table_name="notes")
    op.drop_index("ix_notes_owner_notebook", table_name="notes")
    op.drop_index("ix_notes_owner_id", table_name="notes")
    op.drop_table("notes")

    op.drop_index("ix_notebooks_owner_parent", table_name="notebooks")
    op.drop_index("ix_notebooks_owner_id", table_name="notebooks")
    op.drop_table("notebooks")

    op.drop_table("users")
