"""Add append-only administrative account audit events.

Revision ID: 0007_admin_audit_events
Revises: 0006_migration_provenance
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_admin_audit_events"
down_revision: str | None = "0006_migration_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_IMMUTABLE_FUNCTION = "goreecloud_notes_reject_admin_audit_mutation"
_IMMUTABLE_TRIGGER = "admin_audit_events_immutable"


def upgrade() -> None:
    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        # Deliberately not a foreign key: the audit target identity is an immutable
        # snapshot and must survive any future, separately approved user deletion.
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_username", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("operator_identifier", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "char_length(target_username) > 0",
            name="ck_admin_audit_target_username_nonempty",
        ),
        sa.CheckConstraint("char_length(action) > 0", name="ck_admin_audit_action_nonempty"),
        sa.CheckConstraint(
            "char_length(operator_identifier) > 0",
            name="ck_admin_audit_operator_nonempty",
        ),
        sa.CheckConstraint("char_length(reason) > 0", name="ck_admin_audit_reason_nonempty"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_audit_events_target_user_id",
        "admin_audit_events",
        ["target_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_target_created",
        "admin_audit_events",
        ["target_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_action_created",
        "admin_audit_events",
        ["action", "created_at"],
        unique=False,
    )

    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {_IMMUTABLE_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'admin audit events are append-only';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {_IMMUTABLE_TRIGGER}
            BEFORE UPDATE OR DELETE ON admin_audit_events
            FOR EACH ROW EXECUTE FUNCTION {_IMMUTABLE_FUNCTION}()
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_IMMUTABLE_TRIGGER} ON admin_audit_events"))
    op.drop_index("ix_admin_audit_action_created", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_target_created", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_target_user_id", table_name="admin_audit_events")
    op.drop_table("admin_audit_events")
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_IMMUTABLE_FUNCTION}()"))
