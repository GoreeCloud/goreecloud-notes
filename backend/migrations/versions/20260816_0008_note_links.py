"""Add owner-scoped derived internal-note link index.

Revision ID: 0008_note_links
Revises: 0007_admin_audit_events
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_note_links"
down_revision: str | None = "0007_admin_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LINK_IDS_FUNCTION = "goreecloud_notes_note_link_ids"
_REFRESH_FUNCTION = "goreecloud_notes_refresh_note_links"
_REFRESH_TRIGGER = "notes_refresh_note_links"
_UUID_PATTERN = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"


def upgrade() -> None:
    # A redundant owner/id key lets the relationship table use composite foreign keys
    # and therefore makes cross-account relationships impossible at the database layer.
    op.create_unique_constraint("uq_notes_owner_id", "notes", ["owner_id", "id"])

    op.create_table(
        "note_links",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("source_note_id", sa.Uuid(), nullable=False),
        sa.Column("target_note_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_note_id <> target_note_id", name="ck_note_links_not_self"),
        sa.ForeignKeyConstraint(
            ["owner_id", "source_note_id"],
            ["notes.owner_id", "notes.id"],
            name="fk_note_links_source_owned_note",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "target_note_id"],
            ["notes.owner_id", "notes.id"],
            name="fk_note_links_target_owned_note",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("owner_id", "source_note_id", "target_note_id"),
    )
    op.create_index(
        "ix_note_links_owner_target",
        "note_links",
        ["owner_id", "target_note_id"],
        unique=False,
    )
    op.create_index(
        "ix_note_links_owner_source",
        "note_links",
        ["owner_id", "source_note_id"],
        unique=False,
    )

    # The document remains the portable source of truth. This immutable helper extracts
    # syntactically valid noteLink mark UUIDs from any nested goreecloud.blocks document.
    # strict recursive descent avoids the duplicate-unwrapping behavior of lax JSONPath.
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {_LINK_IDS_FUNCTION}(document jsonb)
            RETURNS TABLE(note_id uuid)
            LANGUAGE sql
            IMMUTABLE
            STRICT
            PARALLEL SAFE
            AS $$
                SELECT DISTINCT (item ->> 'note_id')::uuid
                FROM jsonb_path_query(document, 'strict $.** ? (@.type == "noteLink")') AS item
                WHERE jsonb_typeof(item) = 'object'
                  AND item ? 'note_id'
                  AND jsonb_typeof(item -> 'note_id') = 'string'
                  AND (item ->> 'note_id') ~ '{_UUID_PATTERN}'
            $$
            """
        )
    )

    # Resolve only targets owned by the same account. Unresolved identifiers remain in the
    # authoritative document for portability but never become visible cross-account rows.
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {_REFRESH_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                DELETE FROM note_links
                WHERE owner_id = NEW.owner_id
                  AND (source_note_id = NEW.id OR target_note_id = NEW.id);

                INSERT INTO note_links (owner_id, source_note_id, target_note_id)
                SELECT NEW.owner_id, NEW.id, target.id
                FROM {_LINK_IDS_FUNCTION}(NEW.document) AS link
                JOIN notes AS target
                  ON target.id = link.note_id
                 AND target.owner_id = NEW.owner_id
                WHERE target.id <> NEW.id
                ON CONFLICT DO NOTHING;

                -- A native re-import can insert the target after its source. Rebuild incoming
                -- references whenever any note arrives or changes so insertion order cannot
                -- make the derived backlink index incomplete.
                INSERT INTO note_links (owner_id, source_note_id, target_note_id)
                SELECT source.owner_id, source.id, NEW.id
                FROM notes AS source
                WHERE source.owner_id = NEW.owner_id
                  AND source.id <> NEW.id
                  AND EXISTS (
                      SELECT 1
                      FROM {_LINK_IDS_FUNCTION}(source.document) AS link
                      WHERE link.note_id = NEW.id
                  )
                ON CONFLICT DO NOTHING;

                RETURN NEW;
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {_REFRESH_TRIGGER}
            AFTER INSERT OR UPDATE OF document ON notes
            FOR EACH ROW EXECUTE FUNCTION {_REFRESH_FUNCTION}()
            """
        )
    )

    # Backfill any internal links already present before this migration is applied.
    op.execute(
        sa.text(
            f"""
            INSERT INTO note_links (owner_id, source_note_id, target_note_id)
            SELECT source.owner_id, source.id, target.id
            FROM notes AS source
            CROSS JOIN LATERAL {_LINK_IDS_FUNCTION}(source.document) AS link
            JOIN notes AS target
              ON target.id = link.note_id
             AND target.owner_id = source.owner_id
            WHERE source.id <> target.id
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_REFRESH_TRIGGER} ON notes"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_REFRESH_FUNCTION}()"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_LINK_IDS_FUNCTION}(jsonb)"))
    op.drop_index("ix_note_links_owner_source", table_name="note_links")
    op.drop_index("ix_note_links_owner_target", table_name="note_links")
    op.drop_table("note_links")
    op.drop_constraint("uq_notes_owner_id", "notes", type_="unique")
