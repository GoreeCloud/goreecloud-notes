"""Append-only administrative audit primitives for GoreeCloud Notes.

Administrative account mutations remain local CLI operations. This module records
minimal, non-secret accountability metadata for those operations without creating a
browser or public administrator API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base
from .models import User

MAX_OPERATOR_IDENTIFIER_LENGTH = 120
MAX_AUDIT_REASON_LENGTH = 500
MAX_AUDIT_RESULTS = 200


class AdminAuditEvent(Base):
    """Immutable accountability record for a privileged local account operation.

    The target user UUID and username are snapshots rather than a foreign-key
    relationship. That preserves the audit record byte-for-byte even if a future,
    separately approved account-deletion workflow removes the user record.

    The database migration adds a PostgreSQL trigger that rejects ordinary UPDATE
    and DELETE operations. The event intentionally stores no credential material,
    browser-session secrets, note content, attachment paths, or client addresses.
    """

    __tablename__ = "admin_audit_events"
    __table_args__ = (
        CheckConstraint("char_length(target_username) > 0", name="ck_admin_audit_target_username_nonempty"),
        CheckConstraint("char_length(action) > 0", name="ck_admin_audit_action_nonempty"),
        CheckConstraint("char_length(operator_identifier) > 0", name="ck_admin_audit_operator_nonempty"),
        CheckConstraint("char_length(reason) > 0", name="ck_admin_audit_reason_nonempty"),
        Index("ix_admin_audit_target_created", "target_user_id", "created_at"),
        Index("ix_admin_audit_action_created", "action", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    target_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    target_username: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_identifier: Mapped[str] = mapped_column(String(MAX_OPERATOR_IDENTIFIER_LENGTH), nullable=False)
    reason: Mapped[str] = mapped_column(String(MAX_AUDIT_REASON_LENGTH), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


@dataclass(frozen=True, slots=True)
class AdminAuditContext:
    """Validated, non-secret attribution supplied for one privileged operation."""

    operator_identifier: str
    reason: str


def resolve_admin_audit_context(
    *,
    operator_identifier: str | None,
    reason: str | None,
    production_required: bool,
) -> AdminAuditContext | None:
    """Validate audit attribution and fail closed for production mutations.

    Development/test fixtures may omit both values. Supplying only one value is
    always rejected so an incomplete audit context cannot be recorded by mistake.
    """

    operator = (operator_identifier or "").strip()
    clean_reason = (reason or "").strip()

    if not operator and not clean_reason:
        if production_required:
            raise ValueError("Production administrative mutations require --operator and --reason.")
        return None

    if not operator or not clean_reason:
        raise ValueError("--operator and --reason must be supplied together.")
    if len(operator) > MAX_OPERATOR_IDENTIFIER_LENGTH:
        raise ValueError(
            f"Operator identifier must not exceed {MAX_OPERATOR_IDENTIFIER_LENGTH} characters."
        )
    if len(clean_reason) > MAX_AUDIT_REASON_LENGTH:
        raise ValueError(f"Audit reason must not exceed {MAX_AUDIT_REASON_LENGTH} characters.")

    return AdminAuditContext(operator_identifier=operator, reason=clean_reason)


def record_admin_audit_event(
    db: Session,
    *,
    action: str,
    context: AdminAuditContext | None,
    target_user: User,
    details: dict[str, object] | None = None,
) -> None:
    """Append one audit event inside the caller's existing database transaction."""

    if context is None:
        return

    clean_action = action.strip()
    if not clean_action or len(clean_action) > 64:
        raise ValueError("Administrative audit action must contain 1 to 64 characters.")

    db.add(
        AdminAuditEvent(
            target_user_id=target_user.id,
            target_username=target_user.username,
            action=clean_action,
            operator_identifier=context.operator_identifier,
            reason=context.reason,
            details=details or {},
        )
    )
    db.flush()


def list_admin_audit_events(
    db: Session,
    *,
    target_user_id: UUID | None,
    limit: int,
) -> list[AdminAuditEvent]:
    """Return newest administrative events through a bounded read-only query."""

    if limit < 1 or limit > MAX_AUDIT_RESULTS:
        raise ValueError(f"Audit result limit must contain 1 to {MAX_AUDIT_RESULTS} records.")

    statement = select(AdminAuditEvent)
    if target_user_id is not None:
        statement = statement.where(AdminAuditEvent.target_user_id == target_user_id)
    statement = statement.order_by(AdminAuditEvent.created_at.desc(), AdminAuditEvent.id.desc()).limit(limit)
    return list(db.scalars(statement))
