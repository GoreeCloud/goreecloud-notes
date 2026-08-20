"""Administrative command-line tools for GoreeCloud Notes."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from .admin_audit import (
    AdminAuditContext,
    list_admin_audit_events,
    record_admin_audit_event,
    resolve_admin_audit_context,
)
from .attachment_audit import audit_user_attachment_store
from .auth import (
    hash_password,
    normalize_username,
    replace_user_password,
    set_user_active_state,
    validate_password,
)
from .config import get_settings
from .database import SessionLocal
from .models import AuthSession, User, UserCredential
from .native_import import NativeImportError, import_native_library
from .portability import ExportError, verify_export_bundle
from .portability_migration import export_user_library_with_provenance


def _read_password(password_stdin: bool) -> str:
    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise ValueError("Passwords do not match.")

    validate_password(password)
    return password


def _normalized_required_username(username: str) -> str:
    normalized = normalize_username(username)
    if not normalized:
        raise ValueError("Username must not be empty.")
    return normalized


def _admin_audit_context(args: argparse.Namespace) -> AdminAuditContext | None:
    """Resolve CLI-supplied accountability metadata for a privileged mutation."""

    return resolve_admin_audit_context(
        operator_identifier=args.operator,
        reason=args.reason,
        production_required=get_settings().is_production,
    )


def _add_admin_audit_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--operator",
        help=(
            "Non-secret administrative operator identifier. Required with --reason in production. "
            "This is an asserted operational identity, not a password or token."
        ),
    )
    command.add_argument(
        "--reason",
        help=(
            "Non-secret reason for the administrative action. Required with --operator in production; "
            "do not include credentials, note content, recovery codes, or other secrets."
        ),
    )


def create_user(
    *,
    username: str,
    display_name: str,
    password_stdin: bool,
    audit_context: AdminAuditContext | None = None,
) -> None:
    normalized = normalize_username(username)
    clean_username = username.strip()
    clean_display_name = display_name.strip()
    if not normalized or not clean_username:
        raise ValueError("Username must not be empty.")
    if len(clean_username) > 64 or len(normalized) > 64:
        raise ValueError("Username must not exceed 64 characters.")
    if not clean_display_name or len(clean_display_name) > 120:
        raise ValueError("Display name must contain 1 to 120 characters.")

    password = _read_password(password_stdin)
    password_hash = hash_password(password)

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.username_normalized == normalized))
        if existing is not None:
            raise ValueError("An account with that normalized username already exists.")

        user = User(
            username=clean_username,
            username_normalized=normalized,
            display_name=clean_display_name,
        )
        db.add(user)
        db.flush()
        db.add(UserCredential(user_id=user.id, password_hash=password_hash))
        record_admin_audit_event(
            db,
            action="account.create",
            context=audit_context,
            target_user=user,
            details={"accountCreated": True},
        )
        db.commit()

    print(f"Created GoreeCloud Notes account: {clean_username}")


def account_status(*, username: str, json_output: bool) -> None:
    """Report non-sensitive lifecycle state for one private account."""

    normalized = _normalized_required_username(username)
    now = datetime.now(UTC)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username_normalized == normalized))
        if user is None:
            raise ValueError("Account not found.")

        active_sessions = db.scalar(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.user_id == user.id,
                AuthSession.expires_at > now,
            )
        )
        result = {
            "schemaVersion": 1,
            "username": user.username,
            "displayName": user.display_name,
            "isActive": bool(user.is_active),
            "activeSessions": int(active_sessions or 0),
        }

    if json_output:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return

    print(f"Account: {result['username']}")
    print(f"Display name: {result['displayName']}")
    print(f"Active: {'yes' if result['isActive'] else 'no'}")
    print(f"Active browser sessions: {result['activeSessions']}")


def set_account_active(
    *,
    username: str,
    is_active: bool,
    confirm_disable: bool,
    audit_context: AdminAuditContext | None = None,
) -> None:
    """Enable or disable one account without deleting its credentials or user data."""

    if not is_active and not confirm_disable:
        raise ValueError("Disabling an account requires --confirm-disable.")

    normalized = _normalized_required_username(username)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username_normalized == normalized))
        if user is None:
            raise ValueError("Account not found.")

        account_name = user.username
        changed, revoked_sessions = set_user_active_state(db, user=user, is_active=is_active)
        record_admin_audit_event(
            db,
            action="account.enable" if is_active else "account.disable",
            context=audit_context,
            target_user=user,
            details={
                "stateChanged": changed,
                "revokedSessions": revoked_sessions,
            },
        )
        db.commit()

    if is_active:
        if changed:
            print(
                f"Enabled GoreeCloud Notes account: {account_name}; "
                f"revoked {revoked_sessions} stale session(s); fresh sign-in required."
            )
        else:
            print(
                f"GoreeCloud Notes account already enabled: {account_name}; "
                f"revoked {revoked_sessions} stale session(s); fresh sign-in required."
            )
        return

    if changed:
        print(
            f"Disabled GoreeCloud Notes account: {account_name}; "
            f"revoked {revoked_sessions} session(s); account data preserved."
        )
    else:
        print(
            f"GoreeCloud Notes account already disabled: {account_name}; "
            f"revoked {revoked_sessions} stale session(s); account data preserved."
        )


def reset_password(
    *,
    username: str,
    password_stdin: bool,
    audit_context: AdminAuditContext | None = None,
) -> None:
    """Replace one account password and revoke all existing browser sessions."""

    normalized = _normalized_required_username(username)
    password = _read_password(password_stdin)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username_normalized == normalized))
        if user is None:
            raise ValueError("Account not found.")

        account_name = user.username
        replace_user_password(db, user=user, new_password=password)
        record_admin_audit_event(
            db,
            action="credential.reset",
            context=audit_context,
            target_user=user,
            details={"allSessionsRevoked": True},
        )
        db.commit()

    print(f"Reset GoreeCloud Notes password and revoked all sessions: {account_name}")


def admin_audit(*, username: str | None, limit: int, json_output: bool) -> None:
    """Read bounded, non-secret administrative audit history from PostgreSQL."""

    normalized = _normalized_required_username(username) if username is not None else None
    with SessionLocal() as db:
        target_user_id = None
        if normalized is not None:
            user = db.scalar(select(User).where(User.username_normalized == normalized))
            if user is None:
                raise ValueError("Account not found.")
            target_user_id = user.id

        events = list_admin_audit_events(db, target_user_id=target_user_id, limit=limit)
        result = {
            "schemaVersion": 1,
            "events": [
                {
                    "id": str(event.id),
                    "action": event.action,
                    "operator": event.operator_identifier,
                    "reason": event.reason,
                    "targetUsername": event.target_username,
                    "createdAt": event.created_at.isoformat(),
                    "details": event.details,
                }
                for event in events
            ],
        }

    if json_output:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return

    if not result["events"]:
        print("No administrative audit events found.")
        return

    for event in result["events"]:
        print(
            f"{event['createdAt']} | {event['action']} | {event['targetUsername']} | "
            f"operator={event['operator']} | reason={event['reason']}"
        )


def audit_attachments(*, username: str, json_output: bool) -> bool:
    """Read and verify one account's attachment metadata and owner-scoped bytes."""

    normalized = _normalized_required_username(username)
    settings = get_settings()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username_normalized == normalized))
        if user is None:
            raise ValueError("Account not found.")

        result = audit_user_attachment_store(
            db,
            owner=user,
            attachment_root=Path(settings.attachment_root),
        )

    if json_output:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return bool(result["clean"])

    summary = result["summary"]
    status_label = "clean" if result["clean"] else "FAILED"
    print(f"Attachment integrity audit: {status_label}")
    print(f"Account: {result['account']['username']}")
    print(f"Attachment records: {summary['attachmentRecords']}")
    print(f"Verified attachments: {summary['verifiedAttachments']}")
    print(f"Metadata bytes: {summary['metadataBytes']}")
    print(f"Observed bytes: {summary['observedBytes']}")
    print(f"Orphan files: {summary['orphanFiles']}")
    print(f"Issues: {summary['issues']}")
    for issue in result["issues"]:
        location = issue["storageKey"] or issue["attachmentId"] or "owner store"
        print(f"- {issue['code']} [{location}]: {issue['detail']}")
    return bool(result["clean"])


def export_library(*, username: str, output: str, overwrite: bool) -> None:
    """Create a complete verified native library bundle, including migration provenance."""

    normalized = _normalized_required_username(username)
    settings = get_settings()
    output_path = Path(output)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username_normalized == normalized))
        if user is None:
            raise ValueError("Account not found.")

        result = export_user_library_with_provenance(
            db,
            owner=user,
            attachment_root=Path(settings.attachment_root),
            output_path=output_path,
            overwrite=overwrite,
        )

    print(f"Exported GoreeCloud Notes library: {result.output_path}")
    print(f"SHA-256: {result.sha256}")
    print(f"Size: {result.size_bytes} bytes")
    print(f"Notes: {result.note_count}")
    print(f"Attachments: {result.attachment_count}")


def import_library(*, username: str, input_path: str, confirm_empty_target: bool, json_output: bool) -> None:
    """Reconstruct a verified native bundle into one explicitly empty existing account."""

    if not confirm_empty_target:
        raise ValueError(
            "Native re-import requires --confirm-empty-target; merging into an existing library is not supported."
        )
    normalized = _normalized_required_username(username)

    settings = get_settings()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username_normalized == normalized))
        if user is None:
            raise ValueError("Account not found; create the empty target account before native re-import.")

        result = import_native_library(
            db,
            owner=user,
            input_path=Path(input_path),
            attachment_root=Path(settings.attachment_root),
        )

    if json_output:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return

    counts = result["counts"]
    source = result["source"]
    target = result["target"]
    print(f"Imported verified GoreeCloud Notes library into: {target['username']}")
    print(f"Source account: {source['username']}")
    print(f"Source bundle SHA-256: {source['bundleSha256']}")
    print(f"Notebooks: {counts['notebooks']}")
    print(f"Notes: {counts['notes']}")
    print(f"Tags: {counts['tags']}")
    print(f"Attachments: {counts['attachments']}")
    print(f"Revisions: {counts['revisions']}")
    print(f"Migration provenance records: {counts['migrationNoteRecords']}")


def verify_library_export(*, input_path: str) -> None:
    """Verify an existing native library export without connecting to PostgreSQL."""

    result = verify_export_bundle(Path(input_path))
    print(f"Verified GoreeCloud Notes export: {result.path}")
    print(f"SHA-256: {result.sha256}")
    print(f"Size: {result.size_bytes} bytes")
    print(f"Notes: {result.note_count}")
    print(f"Attachments: {result.attachment_count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GoreeCloud Notes administrative commands")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser(
        "create-user",
        help="Create a private GoreeCloud Notes account; no public registration endpoint exists.",
    )
    create.add_argument("--username", required=True)
    create.add_argument("--display-name", required=True)
    create.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read one password line from standard input instead of prompting interactively.",
    )
    _add_admin_audit_arguments(create)

    status_command = subparsers.add_parser(
        "account-status",
        help="Report one private account's non-sensitive active state and active-session count.",
    )
    status_command.add_argument("--username", required=True)
    status_command.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable non-sensitive account lifecycle state.",
    )

    disable = subparsers.add_parser(
        "disable-user",
        help="Disable one private account and revoke every browser session without deleting account data.",
    )
    disable.add_argument("--username", required=True)
    disable.add_argument(
        "--confirm-disable",
        action="store_true",
        help="Required explicit acknowledgement before disabling the selected account.",
    )
    _add_admin_audit_arguments(disable)

    enable = subparsers.add_parser(
        "enable-user",
        help="Re-enable one private account while requiring a fresh browser sign-in.",
    )
    enable.add_argument("--username", required=True)
    _add_admin_audit_arguments(enable)

    reset = subparsers.add_parser(
        "reset-password",
        help="Reset one private account password and revoke every existing browser session.",
    )
    reset.add_argument("--username", required=True)
    reset.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read one replacement password line from standard input instead of prompting interactively.",
    )
    _add_admin_audit_arguments(reset)

    admin_audit_command = subparsers.add_parser(
        "admin-audit",
        help="Read bounded append-only administrative account-audit history.",
    )
    admin_audit_command.add_argument(
        "--username",
        help="Optional existing account whose administrative events should be returned.",
    )
    admin_audit_command.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum newest events to return (1-200; default: 50).",
    )
    admin_audit_command.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable non-secret administrative audit history.",
    )

    audit = subparsers.add_parser(
        "audit-attachments",
        help=(
            "Read-only integrity audit for one account's attachment metadata and owner-scoped filesystem bytes."
        ),
    )
    audit.add_argument("--username", required=True)
    audit.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit the audit result as machine-readable JSON.",
    )

    export = subparsers.add_parser(
        "export-library",
        help=(
            "Create a verified ZIP bundle containing one account's native library, attachment bytes, "
            "and any preserved migration provenance."
        ),
    )
    export.add_argument("--username", required=True)
    export.add_argument("--output", required=True, help="Destination ZIP path.")
    export.add_argument(
        "--overwrite",
        action="store_true",
        help="Explicitly allow replacement when the destination file already exists.",
    )

    import_bundle = subparsers.add_parser(
        "import-library",
        help=(
            "Reconstruct a verified native full-library ZIP into an existing empty account. "
            "This is a restore/import path, not a merge operation."
        ),
    )
    import_bundle.add_argument("--username", required=True, help="Existing empty target account.")
    import_bundle.add_argument("--input", required=True, dest="input_path", help="Verified native ZIP path.")
    import_bundle.add_argument(
        "--confirm-empty-target",
        action="store_true",
        help="Explicitly confirm that the selected target account is intended to be empty and replaced by the import.",
    )
    import_bundle.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit the import result as machine-readable JSON.",
    )

    verify = subparsers.add_parser(
        "verify-library-export",
        help="Verify the structure and SHA-256 integrity of a native GoreeCloud Notes export bundle.",
    )
    verify.add_argument("--input", required=True, dest="input_path")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "create-user":
            create_user(
                username=args.username,
                display_name=args.display_name,
                password_stdin=args.password_stdin,
                audit_context=_admin_audit_context(args),
            )
        elif args.command == "account-status":
            account_status(username=args.username, json_output=args.json_output)
        elif args.command == "disable-user":
            set_account_active(
                username=args.username,
                is_active=False,
                confirm_disable=args.confirm_disable,
                audit_context=_admin_audit_context(args),
            )
        elif args.command == "enable-user":
            set_account_active(
                username=args.username,
                is_active=True,
                confirm_disable=False,
                audit_context=_admin_audit_context(args),
            )
        elif args.command == "reset-password":
            reset_password(
                username=args.username,
                password_stdin=args.password_stdin,
                audit_context=_admin_audit_context(args),
            )
        elif args.command == "admin-audit":
            admin_audit(
                username=args.username,
                limit=args.limit,
                json_output=args.json_output,
            )
        elif args.command == "audit-attachments":
            clean = audit_attachments(
                username=args.username,
                json_output=args.json_output,
            )
            if not clean:
                return 3
        elif args.command == "export-library":
            export_library(
                username=args.username,
                output=args.output,
                overwrite=args.overwrite,
            )
        elif args.command == "import-library":
            import_library(
                username=args.username,
                input_path=args.input_path,
                confirm_empty_target=args.confirm_empty_target,
                json_output=args.json_output,
            )
        elif args.command == "verify-library-export":
            verify_library_export(input_path=args.input_path)
        else:
            parser.error("Unsupported command.")
    except (ValueError, ExportError, NativeImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
