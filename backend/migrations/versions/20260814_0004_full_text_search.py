"""Add indexed PostgreSQL full-text search for native notes.

Revision ID: 0004_full_text_search
Revises: 0003_content_versions
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_full_text_search"
down_revision: str | None = "0003_content_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEARCH_VECTOR_EXPRESSION = """
setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
setweight(jsonb_to_tsvector('simple', document, '[\"string\"]'::jsonb), 'B')
""".strip()


def upgrade() -> None:
    # The generated vector keeps search data derived from the authoritative title
    # and structured document; clients cannot submit or mutate an independent
    # search index value. The simple configuration is intentionally language-
    # neutral for GoreeCloud's initial family/private workspace.
    op.add_column(
        "notes",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_EXPRESSION, persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_notes_search_vector",
        "notes",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_notes_search_vector", table_name="notes", postgresql_using="gin")
    op.drop_column("notes", "search_vector")
