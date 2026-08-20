"""Read-only inspection for GoreeCloud Notes exports produced by the transitional Memos fork."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

EXPECTED_FORMAT = "goreecloud-notes"
SUPPORTED_SCHEMA_VERSIONS = {1}
DEFAULT_MAX_EXPORT_BYTES = 256 * 1024 * 1024
VALID_STATES = {"normal", "archived", "trash"}
VALID_RESTORE_TARGETS = {"normal", "archived"}


@dataclass(frozen=True)
class MigrationIssue:
    severity: str
    code: str
    path: str
    message: str


@dataclass
class MemosExportReport:
    source_path: str
    source_sha256: str
    source_size_bytes: int
    export_format: str | None
    schema_version: int | None
    exported_at: str | None
    note_count: int
    state_counts: dict[str, int]
    unique_tag_count: int
    attachment_count: int
    local_attachment_count: int
    external_attachment_count: int
    relation_count: int
    relation_type_counts: dict[str, int]
    issues: list[MigrationIssue]

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def metadata_valid(self) -> bool:
        return self.error_count == 0

    @property
    def attachment_binary_recovery_required(self) -> bool:
        return self.local_attachment_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": {
                "path": self.source_path,
                "sha256": self.source_sha256,
                "sizeBytes": self.source_size_bytes,
            },
            "export": {
                "format": self.export_format,
                "schemaVersion": self.schema_version,
                "exportedAt": self.exported_at,
            },
            "inventory": {
                "notes": self.note_count,
                "states": self.state_counts,
                "uniqueTags": self.unique_tag_count,
                "attachments": self.attachment_count,
                "localAttachmentMetadata": self.local_attachment_count,
                "externalAttachments": self.external_attachment_count,
                "relations": self.relation_count,
                "relationTypes": self.relation_type_counts,
            },
            "validation": {
                "metadataValid": self.metadata_valid,
                "errors": self.error_count,
                "warnings": self.warning_count,
                "attachmentBinaryRecoveryRequired": self.attachment_binary_recovery_required,
                "sourceMutationPerformed": False,
            },
            "issues": [asdict(issue) for issue in self.issues],
        }


def _issue(issues: list[MigrationIssue], severity: str, code: str, path: str, message: str) -> None:
    issues.append(MigrationIssue(severity=severity, code=code, path=path, message=message))


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_timestamp(value: Any, path: str, issues: list[MigrationIssue], *, required: bool = False) -> None:
    if value is None:
        if required:
            _issue(issues, "error", "missing-timestamp", path, "Expected an ISO-8601 timestamp.")
        return
    if not isinstance(value, str):
        _issue(issues, "error", "invalid-timestamp-type", path, "Timestamp must be a string or null.")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _issue(issues, "error", "invalid-timestamp", path, "Timestamp is not valid ISO-8601.")
        return
    if parsed.tzinfo is None:
        _issue(issues, "error", "naive-timestamp", path, "Timestamp must include an explicit timezone offset or Z.")


def _validate_string_list(value: Any, path: str, issues: list[MigrationIssue]) -> list[str]:
    if not isinstance(value, list):
        _issue(issues, "error", "invalid-list", path, "Expected a JSON array of strings.")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            _issue(issues, "error", "invalid-string", f"{path}[{index}]", "Expected a string.")
            continue
        result.append(item)
    return result


def _validate_attachment(
    attachment: Any,
    *,
    path: str,
    note_name: str | None,
    attachment_names: set[str],
    issues: list[MigrationIssue],
) -> tuple[bool, bool]:
    if not isinstance(attachment, dict):
        _issue(issues, "error", "invalid-attachment", path, "Attachment metadata must be a JSON object.")
        return False, False

    name = attachment.get("name")
    if not _is_nonempty_string(name):
        _issue(issues, "error", "invalid-attachment-name", f"{path}.name", "Attachment name must be a non-empty string.")
    elif name in attachment_names:
        _issue(issues, "error", "duplicate-attachment-name", f"{path}.name", f"Duplicate attachment name: {name}")
    else:
        attachment_names.add(name)

    filename = attachment.get("filename")
    if not _is_nonempty_string(filename):
        _issue(issues, "error", "invalid-attachment-filename", f"{path}.filename", "Attachment filename must be a non-empty string.")

    mime_type = attachment.get("mimeType")
    if not _is_nonempty_string(mime_type):
        _issue(issues, "error", "invalid-attachment-mime-type", f"{path}.mimeType", "Attachment MIME type must be a non-empty string.")

    size_bytes = attachment.get("sizeBytes")
    if not isinstance(size_bytes, str):
        _issue(issues, "error", "invalid-attachment-size-type", f"{path}.sizeBytes", "Schema v1 stores attachment sizeBytes as a decimal string.")
    else:
        try:
            if int(size_bytes) < 0:
                raise ValueError
        except ValueError:
            _issue(issues, "error", "invalid-attachment-size", f"{path}.sizeBytes", "Attachment sizeBytes must be a non-negative decimal string.")

    _validate_timestamp(attachment.get("createTime"), f"{path}.createTime", issues)

    memo = attachment.get("memo")
    if not _is_nonempty_string(memo):
        _issue(issues, "error", "invalid-attachment-memo", f"{path}.memo", "Attachment memo relationship must be a non-empty string.")
    elif note_name and memo != note_name:
        _issue(
            issues,
            "warning",
            "attachment-memo-mismatch",
            f"{path}.memo",
            "Attachment metadata points at a memo name different from the containing exported note; preserve for manual review.",
        )

    external_link = attachment.get("externalLink")
    if external_link is not None and not _is_nonempty_string(external_link):
        _issue(issues, "error", "invalid-external-link", f"{path}.externalLink", "externalLink must be a non-empty string or null.")

    for metadata_key in ("motionMedia", "mediaMetadata"):
        metadata_value = attachment.get(metadata_key)
        if metadata_value is not None and not isinstance(metadata_value, dict):
            _issue(issues, "error", "invalid-attachment-metadata", f"{path}.{metadata_key}", f"{metadata_key} must be an object or null.")

    return external_link is None, external_link is not None


def inspect_memos_export(path: Path, *, max_bytes: int = DEFAULT_MAX_EXPORT_BYTES) -> MemosExportReport:
    """Inspect a transitional GoreeCloud/Memos JSON export without mutating any source or target state."""

    source = path.expanduser().resolve()
    size = source.stat().st_size
    if size > max_bytes:
        raise ValueError(f"Export is {size} bytes, exceeding the configured {max_bytes}-byte inspection limit.")

    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Export is not valid UTF-8 JSON: {exc}") from exc

    issues: list[MigrationIssue] = []
    if not isinstance(payload, dict):
        _issue(issues, "error", "invalid-envelope", "$", "Export root must be a JSON object.")
        payload = {}

    export_format = payload.get("format") if isinstance(payload.get("format"), str) else None
    if export_format != EXPECTED_FORMAT:
        _issue(issues, "error", "unsupported-format", "$.format", f"Expected format {EXPECTED_FORMAT!r}.")

    schema_value = payload.get("schemaVersion")
    schema_version = schema_value if type(schema_value) is int else None
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        _issue(issues, "error", "unsupported-schema-version", "$.schemaVersion", "Only GoreeCloud Notes export schemaVersion 1 is supported by this inspector.")

    exported_at = payload.get("exportedAt") if isinstance(payload.get("exportedAt"), str) else None
    _validate_timestamp(payload.get("exportedAt"), "$.exportedAt", issues, required=True)

    source_info = payload.get("source")
    if not isinstance(source_info, dict):
        _issue(issues, "error", "invalid-source", "$.source", "Source provenance must be a JSON object.")
    else:
        if source_info.get("application") != "GoreeCloud Notes":
            _issue(issues, "error", "unexpected-source-application", "$.source.application", "Expected source application 'GoreeCloud Notes'.")
        if source_info.get("upstream") != "Memos":
            _issue(issues, "error", "unexpected-source-upstream", "$.source.upstream", "Expected transitional upstream 'Memos'.")

    scope = payload.get("scope")
    if not isinstance(scope, dict):
        _issue(issues, "error", "invalid-scope", "$.scope", "Export scope must be a JSON object.")
    else:
        includes = _validate_string_list(scope.get("includes"), "$.scope.includes", issues)
        excludes = _validate_string_list(scope.get("excludes"), "$.scope.excludes", issues)
        if "top-level notes" not in includes:
            _issue(issues, "warning", "unexpected-export-scope", "$.scope.includes", "Export does not declare top-level notes in its include scope.")
        if "attachment binary content" not in excludes:
            _issue(issues, "warning", "binary-exclusion-not-declared", "$.scope.excludes", "Schema v1 normally declares attachment binary content as excluded; do not assume JSON contains attachment bytes.")

    notes_value = payload.get("notes")
    if not isinstance(notes_value, list):
        _issue(issues, "error", "invalid-notes", "$.notes", "notes must be a JSON array.")
        notes: list[Any] = []
    else:
        notes = notes_value

    note_names: set[str] = set()
    note_uids: set[str] = set()
    attachment_names: set[str] = set()
    all_tags: set[str] = set()
    state_counts: Counter[str] = Counter()
    relation_type_counts: Counter[str] = Counter()
    relation_targets: list[tuple[str, str]] = []
    attachment_count = 0
    local_attachment_count = 0
    external_attachment_count = 0
    relation_count = 0

    for index, note in enumerate(notes):
        note_path = f"$.notes[{index}]"
        if not isinstance(note, dict):
            _issue(issues, "error", "invalid-note", note_path, "Each note must be a JSON object.")
            continue

        name = note.get("name")
        if not _is_nonempty_string(name):
            _issue(issues, "error", "invalid-note-name", f"{note_path}.name", "Note name must be a non-empty string.")
            note_name = None
        else:
            note_name = name
            if name in note_names:
                _issue(issues, "error", "duplicate-note-name", f"{note_path}.name", f"Duplicate note name: {name}")
            else:
                note_names.add(name)

        uid = note.get("uid")
        if not _is_nonempty_string(uid):
            _issue(issues, "error", "invalid-note-uid", f"{note_path}.uid", "Note uid must be a non-empty string.")
        elif uid in note_uids:
            _issue(issues, "error", "duplicate-note-uid", f"{note_path}.uid", f"Duplicate note uid: {uid}")
        else:
            note_uids.add(uid)

        title = note.get("title")
        if title is not None and not isinstance(title, str):
            _issue(issues, "error", "invalid-title", f"{note_path}.title", "Title must be a string or null.")

        if not isinstance(note.get("markdown"), str):
            _issue(issues, "error", "invalid-markdown", f"{note_path}.markdown", "Markdown content must be a string.")

        state = note.get("state")
        if state not in VALID_STATES:
            _issue(issues, "error", "invalid-note-state", f"{note_path}.state", f"State must be one of {sorted(VALID_STATES)}.")
        else:
            state_counts[state] += 1

        restore_target = note.get("restoreTarget")
        if state == "trash":
            if restore_target not in VALID_RESTORE_TARGETS:
                _issue(issues, "error", "invalid-restore-target", f"{note_path}.restoreTarget", "Trash notes must preserve restoreTarget as normal or archived.")
        elif restore_target is not None:
            _issue(issues, "warning", "unexpected-restore-target", f"{note_path}.restoreTarget", "Non-trash note carries restoreTarget metadata; preserve for manual review.")

        if not _is_nonempty_string(note.get("visibility")):
            _issue(issues, "error", "invalid-visibility", f"{note_path}.visibility", "Visibility must be a non-empty string.")
        if not isinstance(note.get("pinned"), bool):
            _issue(issues, "error", "invalid-pinned", f"{note_path}.pinned", "Pinned must be a boolean.")
        color = note.get("color")
        if color is not None and not isinstance(color, str):
            _issue(issues, "error", "invalid-color", f"{note_path}.color", "Color must be a string or null.")

        tags = _validate_string_list(note.get("tags"), f"{note_path}.tags", issues)
        for tag_index, tag in enumerate(tags):
            if not tag.strip():
                _issue(issues, "warning", "empty-tag", f"{note_path}.tags[{tag_index}]", "Empty tag should be reviewed before import.")
            else:
                all_tags.add(tag)
        if len(tags) != len(set(tags)):
            _issue(issues, "warning", "duplicate-note-tags", f"{note_path}.tags", "Note contains duplicate tag strings; importer must not silently duplicate assignments.")

        _validate_timestamp(note.get("createTime"), f"{note_path}.createTime", issues)
        _validate_timestamp(note.get("updateTime"), f"{note_path}.updateTime", issues)

        location = note.get("location")
        if location is not None and not isinstance(location, dict):
            _issue(issues, "error", "invalid-location", f"{note_path}.location", "Location must be an object or null.")

        attachments = note.get("attachments")
        if not isinstance(attachments, list):
            _issue(issues, "error", "invalid-attachments", f"{note_path}.attachments", "attachments must be a JSON array.")
        else:
            for attachment_index, attachment in enumerate(attachments):
                attachment_count += 1
                local_binary, external = _validate_attachment(
                    attachment,
                    path=f"{note_path}.attachments[{attachment_index}]",
                    note_name=note_name,
                    attachment_names=attachment_names,
                    issues=issues,
                )
                local_attachment_count += int(local_binary)
                external_attachment_count += int(external)

        relations = note.get("relations")
        if not isinstance(relations, list):
            _issue(issues, "error", "invalid-relations", f"{note_path}.relations", "relations must be a JSON array.")
        else:
            for relation_index, relation in enumerate(relations):
                relation_count += 1
                relation_path = f"{note_path}.relations[{relation_index}]"
                if not isinstance(relation, dict):
                    _issue(issues, "error", "invalid-relation", relation_path, "Relation must be a JSON object.")
                    continue
                relation_memo = relation.get("memo")
                if not _is_nonempty_string(relation_memo):
                    _issue(issues, "error", "invalid-relation-memo", f"{relation_path}.memo", "Relation memo must be a non-empty string.")
                elif note_name and relation_memo != note_name:
                    _issue(issues, "warning", "relation-memo-mismatch", f"{relation_path}.memo", "Relation origin differs from the containing note; preserve for manual review.")
                related_memo = relation.get("relatedMemo")
                if related_memo is not None and not _is_nonempty_string(related_memo):
                    _issue(issues, "error", "invalid-related-memo", f"{relation_path}.relatedMemo", "relatedMemo must be a non-empty string or null.")
                elif isinstance(related_memo, str) and related_memo:
                    relation_targets.append((f"{relation_path}.relatedMemo", related_memo))
                relation_type = relation.get("type")
                if not _is_nonempty_string(relation_type):
                    _issue(issues, "error", "invalid-relation-type", f"{relation_path}.type", "Relation type must be a non-empty string.")
                else:
                    relation_type_counts[relation_type] += 1
                    if relation_type not in {"REFERENCE", "COMMENT", "TYPE_UNSPECIFIED"}:
                        _issue(issues, "warning", "unknown-relation-type", f"{relation_path}.type", "Unknown relation type should be preserved and reviewed, not silently discarded.")

    for relation_path, target in relation_targets:
        if target not in note_names:
            _issue(
                issues,
                "warning",
                "relation-target-not-exported",
                relation_path,
                "Related memo is not present among exported top-level notes. This can be expected for excluded comments, but must be reconciled during migration.",
            )

    if local_attachment_count:
        _issue(
            issues,
            "warning",
            "attachment-binaries-require-separate-recovery",
            "$.notes[*].attachments",
            f"{local_attachment_count} attachment metadata record(s) reference local binary content that schema v1 intentionally does not embed. Binary extraction and checksum validation remain a separate migration gate.",
        )

    return MemosExportReport(
        source_path=str(source),
        source_sha256=digest,
        source_size_bytes=size,
        export_format=export_format,
        schema_version=schema_version,
        exported_at=exported_at,
        note_count=len(notes),
        state_counts=dict(sorted(state_counts.items())),
        unique_tag_count=len(all_tags),
        attachment_count=attachment_count,
        local_attachment_count=local_attachment_count,
        external_attachment_count=external_attachment_count,
        relation_count=relation_count,
        relation_type_counts=dict(sorted(relation_type_counts.items())),
        issues=issues,
    )


def format_text_report(report: MemosExportReport) -> str:
    state_summary = ", ".join(f"{state}={count}" for state, count in report.state_counts.items()) or "none"
    lines = [
        "GoreeCloud Notes transitional Memos export inventory",
        f"Source: {report.source_path}",
        f"SHA-256: {report.source_sha256}",
        f"Format: {report.export_format or 'unknown'}; schemaVersion={report.schema_version!s}",
        f"Notes: {report.note_count} ({state_summary})",
        f"Unique tags: {report.unique_tag_count}",
        f"Attachments: {report.attachment_count} metadata record(s); local-binary recovery required={report.local_attachment_count}; external={report.external_attachment_count}",
        f"Relations: {report.relation_count}",
        f"Metadata validation: {'PASS' if report.metadata_valid else 'FAIL'}; errors={report.error_count}; warnings={report.warning_count}",
        "Source mutation performed: no",
    ]
    if report.issues:
        lines.append("Issues:")
        lines.extend(f"- {issue.severity.upper()} {issue.code} {issue.path}: {issue.message}" for issue in report.issues)
    return "\n".join(lines)
