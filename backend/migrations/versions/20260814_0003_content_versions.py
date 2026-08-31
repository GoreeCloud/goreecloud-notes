"""Add optimistic content versions for autosave safety.

Revision ID: 0003_content_versions
Revises: 0002_authentication
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_content_versions"
down_revision: str | None = "0002_authentication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notes", sa.Column("content_version", sa.Integer(), nullable=True))
    op.add_column("note_revisions", sa.Column("content_version", sa.Integer(), nullable=True))

    # Existing development revisions are mapped monotonically to their historical
    # revision number. Each note then advances one version beyond its latest
    # preserved revision. This keeps the migration safe for already-used dev DBs.
    op.execute("UPDATE note_revisions SET content_version = revision_number")
    op.execute(
        """
        UPDATE notes
        SET content_version = COALESCE(
            (
                SELECT MAX(note_revisions.content_version) + 1
                FROM note_revisions
                WHERE note_revisions.note_id = notes.id
            ),
            1
        )
        """
    )

    op.alter_column(
        "notes",
        "content_version",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("1"),
    )
    op.alter_column(
        "note_revisions",
        "content_version",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.create_check_constraint(
        "ck_notes_content_version_positive",
        "notes",
        "content_version > 0",
    )
    op.create_check_constraint(
        "ck_note_revisions_content_version_positive",
        "note_revisions",
        "content_version > 0",
    )
    op.create_unique_constraint(
        "uq_note_revisions_note_content_version",
        "note_revisions",
        ["note_id", "content_version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_note_revisions_note_content_version",
        "note_revisions",
        type_="unique",
    )
    op.drop_constraint(
        "ck_note_revisions_content_version_positive",
        "note_revisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_notes_content_version_positive",
        "notes",
        type_="check",
    )
    op.drop_column("note_revisions", "content_version")
    op.drop_column("notes", "content_version")
