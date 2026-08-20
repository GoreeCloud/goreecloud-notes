"""Add persistent bounded login-abuse rate state.

Revision ID: 0005_login_abuse_controls
Revises: 0004_full_text_search
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_login_abuse_controls"
down_revision: str | None = "0004_full_text_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_rate_buckets",
        sa.Column("bucket_key", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('source', 'source_account')",
            name="ck_login_rate_buckets_scope",
        ),
        sa.CheckConstraint(
            "failure_count >= 0",
            name="ck_login_rate_buckets_failure_count_nonnegative",
        ),
        sa.PrimaryKeyConstraint("bucket_key"),
    )
    op.create_index(
        "ix_login_rate_buckets_expires_at",
        "login_rate_buckets",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_login_rate_buckets_expires_at", table_name="login_rate_buckets")
    op.drop_table("login_rate_buckets")
