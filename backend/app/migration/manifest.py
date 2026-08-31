"""Provider-neutral migration manifest generation for validated GoreeCloud/Memos exports."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .memos import DEFAULT_MAX_EXPORT_BYTES, inspect_memos_export

MANIFEST_FORMAT = "goreecloud-notes-migration"
MANIFEST_SCHEMA_VERSION = 1

_STATE_MAP = {
    "normal": "active",
    "archived": "archived",
    "trash": "trashed",
}
_RESTORE_TARGET_MAP = {
    "normal": "active",
    "archived": "archived",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _normalize_attachment(attachment: dict[str, Any], *, source_order: int) -> dict[str, Any]:
    external_link = attachment["externalLink"]
    binary_status = "external" if external_link is not None else "required"
    return {
        "source": {
            "provider": "memos",
            "name": attachment["name"],
            "memo": attachment["memo"],
            "order": source_order,
        },
        "filename": attachment["filename"],
        "mimeType": attachment["mimeType"],
        "declaredSizeBytes": int(attachment["sizeBytes"]),
        "createTime": attachment["createTime"],
        "externalLink": external_link,
        "binary": {
            "status": binary_status,
            "sha256": None,
            "verifiedSizeBytes": None,
        },
        "sourceMetadata": {
            "motionMedia": attachment["motionMedia"],
            "mediaMetadata": attachment["mediaMetadata"],
        },
    }


def _normalize_relation(
    relation: dict[str, Any],
    *,
    source_order: int,
    exported_note_names: set[str],
) -> dict[str, Any]:
    target = relation["relatedMemo"]
    return {
        "source": {
            "provider": "memos",
            "memo": relation["memo"],
            "order": source_order,
        },
        "type": relation["type"],
        "targetSourceMemo": target,
        "targetExported": target in exported_note_names if target is not None else False,
    }


def _normalize_note(
    note: dict[str, Any],
    *,
    source_order: int,
    exported_note_names: set[str],
) -> dict[str, Any]:
    source_state = note["state"]
    source_restore_target = note["restoreTarget"]
    record: dict[str, Any] = {
        "source": {
            "provider": "memos",
            "name": note["name"],
            "uid": note["uid"],
            "order": source_order,
            "state": source_state,
            "restoreTarget": source_restore_target,
        },
        "content": {
            "title": note["title"],
            "markdown": note["markdown"],
            "markdownSha256": _sha256_text(note["markdown"]),
        },
        "lifecycle": {
            "state": _STATE_MAP[source_state],
            "restoreTarget": (
                _RESTORE_TARGET_MAP[source_restore_target]
                if source_restore_target is not None
                else None
            ),
            "pinned": note["pinned"],
        },
        "metadata": {
            "visibility": note["visibility"],
            "color": note["color"],
            "tags": list(note["tags"]),
            "createTime": note["createTime"],
            "updateTime": note["updateTime"],
            "location": note["location"],
        },
        "attachments": [
            _normalize_attachment(attachment, source_order=index)
            for index, attachment in enumerate(note["attachments"])
        ],
        "relations": [
            _normalize_relation(
                relation,
                source_order=index,
                exported_note_names=exported_note_names,
            )
            for index, relation in enumerate(note["relations"])
        ],
    }
    record["recordSha256"] = _canonical_sha256(record)
    return record


def build_memos_manifest(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_EXPORT_BYTES,
) -> dict[str, Any]:
    """Build a deterministic zero-write migration manifest from a validated Memos export."""

    source = path.expanduser().resolve()
    report = inspect_memos_export(source, max_bytes=max_bytes)
    if not report.metadata_valid:
        error_codes = sorted({issue.code for issue in report.issues if issue.severity == "error"})
        suffix = f" ({', '.join(error_codes)})" if error_codes else ""
        raise ValueError(f"Source metadata validation failed; migration manifest was not created{suffix}.")

    raw = source.read_bytes()
    if len(raw) != report.source_size_bytes or _sha256_bytes(raw) != report.source_sha256:
        raise ValueError("Source export changed during validation; migration manifest was not created.")

    payload = json.loads(raw)
    notes = payload["notes"]
    exported_note_names = {note["name"] for note in notes}
    warning_issues = [
        asdict(issue)
        for issue in report.issues
        if issue.severity == "warning"
    ]

    manifest = {
        "format": MANIFEST_FORMAT,
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "source": {
            "provider": "memos",
            "application": "GoreeCloud Notes",
            "exportFormat": payload["format"],
            "exportSchemaVersion": payload["schemaVersion"],
            "exportedAt": payload["exportedAt"],
            "sha256": report.source_sha256,
            "sizeBytes": report.source_size_bytes,
        },
        "validation": {
            "sourceMetadataValid": True,
            "sourceWarnings": warning_issues,
            "attachmentBinaryRecoveryRequired": report.attachment_binary_recovery_required,
            "sourceMutationPerformed": False,
            "targetMutationPerformed": False,
        },
        "inventory": {
            "notes": report.note_count,
            "states": report.state_counts,
            "uniqueTags": report.unique_tag_count,
            "attachments": report.attachment_count,
            "localAttachmentMetadata": report.local_attachment_count,
            "externalAttachments": report.external_attachment_count,
            "relations": report.relation_count,
            "relationTypes": report.relation_type_counts,
        },
        "notes": [
            _normalize_note(
                note,
                source_order=index,
                exported_note_names=exported_note_names,
            )
            for index, note in enumerate(notes)
        ],
    }
    return manifest


def serialize_manifest(manifest: dict[str, Any]) -> str:
    """Serialize a manifest deterministically for review, hashing, and later import tooling."""

    return json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
