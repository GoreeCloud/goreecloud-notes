"""Read-only attachment-store integrity auditing for GoreeCloud Notes."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Attachment, Note, User

AUDIT_FORMAT = "goreecloud-notes-attachment-audit"
AUDIT_SCHEMA_VERSION = 1


def _issue(
    code: str,
    detail: str,
    *,
    attachment: Attachment | None = None,
    storage_key: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "attachmentId": str(attachment.id) if attachment is not None else None,
        "storageKey": storage_key if storage_key is not None else (attachment.storage_key if attachment is not None else None),
        "detail": detail,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _symlink_component(root: Path, storage_key: str) -> Path | None:
    """Return the first symlink component beneath root without following it."""

    current = root
    for part in Path(storage_key).parts:
        current = current / part
        if current.is_symlink():
            return current
    return None


def audit_attachment_records(
    *,
    owner_id: UUID,
    attachments: Iterable[Attachment],
    attachment_root: Path,
    owned_note_ids: set[UUID] | None = None,
) -> dict[str, Any]:
    """Audit attachment metadata and owner-scoped filesystem bytes without mutation.

    The audit treats PostgreSQL attachment rows as the expected inventory, verifies every
    referenced file's location, size and SHA-256 value, and reports unexpected files beneath
    the selected owner's storage directory. It never repairs, deletes, moves, or rewrites data.
    """

    records = tuple(sorted(attachments, key=lambda item: (str(item.note_id), str(item.id))))
    root = attachment_root.expanduser().resolve()
    issues: list[dict[str, Any]] = []
    expected_owner_keys: set[str] = set()
    seen_storage_keys: set[str] = set()
    metadata_bytes = 0
    observed_bytes = 0
    verified_attachments = 0

    for attachment in records:
        record_clean = True
        metadata_bytes += attachment.size_bytes

        if attachment.owner_id != owner_id:
            issues.append(
                _issue(
                    "attachment_owner_mismatch",
                    "Attachment metadata is not owned by the selected account.",
                    attachment=attachment,
                )
            )
            record_clean = False

        if owned_note_ids is not None and attachment.note_id not in owned_note_ids:
            issues.append(
                _issue(
                    "note_owner_mismatch",
                    "Attachment points to a note that is not owned by the selected account.",
                    attachment=attachment,
                )
            )
            record_clean = False

        expected_key = f"{owner_id}/{attachment.note_id}/{attachment.id}"
        if attachment.storage_key != expected_key:
            issues.append(
                _issue(
                    "storage_key_mismatch",
                    "Attachment storage key does not match the generated owner/note/attachment layout.",
                    attachment=attachment,
                )
            )
            record_clean = False

        if attachment.storage_key in seen_storage_keys:
            issues.append(
                _issue(
                    "duplicate_storage_key",
                    "More than one attachment row references the same storage key.",
                    attachment=attachment,
                )
            )
            record_clean = False
        seen_storage_keys.add(attachment.storage_key)

        raw_path = root / attachment.storage_key
        try:
            resolved_path = raw_path.resolve(strict=False)
            resolved_path.relative_to(root)
        except (OSError, ValueError):
            issues.append(
                _issue(
                    "storage_escape",
                    "Attachment storage key resolves outside the configured attachment root.",
                    attachment=attachment,
                )
            )
            continue

        owner_prefix = f"{owner_id}/"
        if attachment.storage_key.startswith(owner_prefix):
            expected_owner_keys.add(attachment.storage_key)

        try:
            linked_component = _symlink_component(root, attachment.storage_key)
        except OSError:
            linked_component = raw_path
        if linked_component is not None:
            issues.append(
                _issue(
                    "symlink_component",
                    "Attachment storage path contains a symbolic link and is not trusted as ordinary private storage.",
                    attachment=attachment,
                )
            )
            continue

        if not raw_path.exists():
            issues.append(
                _issue(
                    "missing_bytes",
                    "Attachment metadata exists but the expected attachment file is missing.",
                    attachment=attachment,
                )
            )
            continue

        if not raw_path.is_file():
            issues.append(
                _issue(
                    "non_regular_file",
                    "Attachment storage path is not a regular file.",
                    attachment=attachment,
                )
            )
            continue

        try:
            actual_size = raw_path.stat().st_size
            observed_bytes += actual_size
            if actual_size != attachment.size_bytes:
                issues.append(
                    _issue(
                        "size_mismatch",
                        f"Attachment byte size is {actual_size}, expected {attachment.size_bytes}.",
                        attachment=attachment,
                    )
                )
                record_clean = False

            actual_sha256 = _sha256_file(raw_path)
            if actual_sha256 != attachment.sha256:
                issues.append(
                    _issue(
                        "sha256_mismatch",
                        "Attachment SHA-256 does not match persisted metadata.",
                        attachment=attachment,
                    )
                )
                record_clean = False
        except OSError:
            issues.append(
                _issue(
                    "read_error",
                    "Attachment bytes could not be read completely for integrity verification.",
                    attachment=attachment,
                )
            )
            continue

        if record_clean:
            verified_attachments += 1

    orphan_files = 0
    owner_directory = root / str(owner_id)
    if owner_directory.is_symlink():
        issues.append(
            _issue(
                "owner_directory_symlink",
                "The selected account's attachment directory is a symbolic link; orphan scanning was refused.",
                storage_key=str(owner_id),
            )
        )
    elif owner_directory.exists() and not owner_directory.is_dir():
        issues.append(
            _issue(
                "owner_path_not_directory",
                "The selected account's attachment storage path exists but is not a directory.",
                storage_key=str(owner_id),
            )
        )
    elif owner_directory.is_dir():
        for directory, directory_names, file_names in os.walk(owner_directory, followlinks=False):
            current_directory = Path(directory)
            safe_directories: list[str] = []
            for name in directory_names:
                candidate = current_directory / name
                if candidate.is_symlink():
                    relative_key = candidate.relative_to(root).as_posix()
                    issues.append(
                        _issue(
                            "unexpected_symlink",
                            "Unexpected symbolic link exists beneath the owner-scoped attachment directory.",
                            storage_key=relative_key,
                        )
                    )
                else:
                    safe_directories.append(name)
            directory_names[:] = safe_directories

            for name in file_names:
                candidate = current_directory / name
                relative_key = candidate.relative_to(root).as_posix()
                if candidate.is_symlink():
                    issues.append(
                        _issue(
                            "unexpected_symlink",
                            "Unexpected symbolic link exists beneath the owner-scoped attachment directory.",
                            storage_key=relative_key,
                        )
                    )
                    continue
                if relative_key not in expected_owner_keys:
                    orphan_files += 1
                    issues.append(
                        _issue(
                            "orphan_file",
                            "Attachment file exists beneath the owner directory without a matching attachment row.",
                            storage_key=relative_key,
                        )
                    )

    return {
        "format": AUDIT_FORMAT,
        "schemaVersion": AUDIT_SCHEMA_VERSION,
        "ownerId": str(owner_id),
        "clean": not issues,
        "summary": {
            "attachmentRecords": len(records),
            "verifiedAttachments": verified_attachments,
            "metadataBytes": metadata_bytes,
            "observedBytes": observed_bytes,
            "orphanFiles": orphan_files,
            "issues": len(issues),
        },
        "issues": issues,
    }


def audit_user_attachment_store(
    db: Session,
    *,
    owner: User,
    attachment_root: Path,
) -> dict[str, Any]:
    """Audit one account's persisted attachment records and owner-scoped files."""

    attachments = tuple(
        db.scalars(
            select(Attachment)
            .where(Attachment.owner_id == owner.id)
            .order_by(Attachment.note_id.asc(), Attachment.id.asc())
        )
    )
    owned_note_ids = set(db.scalars(select(Note.id).where(Note.owner_id == owner.id)))
    result = audit_attachment_records(
        owner_id=owner.id,
        attachments=attachments,
        attachment_root=attachment_root,
        owned_note_ids=owned_note_ids,
    )
    result["account"] = {"username": owner.username}
    return result
