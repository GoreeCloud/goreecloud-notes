"""Read-only inspection for Evernote ENEX exports before native GoreeCloud Notes migration."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import stat
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .memos import MigrationIssue

DEFAULT_MAX_ENEX_BYTES = 256 * 1024 * 1024
_ENEX_TIMESTAMP = "%Y%m%dT%H%M%SZ"
_MD5_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")


@dataclass
class EnexExportReport:
    source_path: str
    source_sha256: str
    source_size_bytes: int
    application: str | None
    version: str | None
    exported_at: str | None
    note_count: int
    deleted_note_count: int
    unique_tag_count: int
    resource_count: int
    embedded_resource_bytes: int
    resource_mime_type_counts: dict[str, int]
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
    def resource_extraction_required(self) -> bool:
        return self.resource_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": {
                "provider": "evernote",
                "path": self.source_path,
                "sha256": self.source_sha256,
                "sizeBytes": self.source_size_bytes,
            },
            "export": {
                "format": "enex",
                "application": self.application,
                "version": self.version,
                "exportedAt": self.exported_at,
            },
            "inventory": {
                "notes": self.note_count,
                "deletedNotes": self.deleted_note_count,
                "uniqueTags": self.unique_tag_count,
                "resources": self.resource_count,
                "embeddedResourceBytes": self.embedded_resource_bytes,
                "resourceMimeTypes": self.resource_mime_type_counts,
            },
            "validation": {
                "metadataValid": self.metadata_valid,
                "errors": self.error_count,
                "warnings": self.warning_count,
                "resourceExtractionRequired": self.resource_extraction_required,
                "sourceMutationPerformed": False,
                "targetMutationPerformed": False,
            },
            "issues": [asdict(issue) for issue in self.issues],
        }


def _issue(issues: list[MigrationIssue], severity: str, code: str, path: str, message: str) -> None:
    issues.append(MigrationIssue(severity=severity, code=code, path=path, message=message))


def _normalize_enex_timestamp(
    value: str | None,
    *,
    path: str,
    issues: list[MigrationIssue],
    required: bool = False,
) -> str | None:
    if value is None or not value.strip():
        if required:
            _issue(issues, "error", "missing-timestamp", path, "Expected an Evernote UTC timestamp.")
        return None
    try:
        parsed = datetime.strptime(value.strip(), _ENEX_TIMESTAMP).replace(tzinfo=UTC)
    except ValueError:
        _issue(
            issues,
            "error",
            "invalid-enex-timestamp",
            path,
            "Expected Evernote timestamp format YYYYMMDDTHHMMSSZ.",
        )
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def _required_text(
    parent: ET.Element,
    tag: str,
    *,
    path: str,
    issues: list[MigrationIssue],
) -> str | None:
    element = parent.find(tag)
    value = element.text if element is not None else None
    if value is None or not value.strip():
        _issue(issues, "error", f"missing-{tag}", f"{path}.{tag}", f"Expected non-empty <{tag}> content.")
        return None
    return value


def _resource_bytes(
    resource: ET.Element,
    *,
    path: str,
    issues: list[MigrationIssue],
) -> bytes | None:
    data = resource.find("data")
    if data is None:
        _issue(issues, "error", "missing-resource-data", f"{path}.data", "Resource is missing its embedded data element.")
        return None
    if data.get("encoding") != "base64":
        _issue(
            issues,
            "error",
            "unsupported-resource-encoding",
            f"{path}.data.@encoding",
            "Only base64 ENEX resource data is supported.",
        )
        return None
    compact = "".join((data.text or "").split())
    try:
        encoded = compact.encode("ascii")
        decoded = base64.b64decode(encoded, validate=True)
    except (UnicodeEncodeError, binascii.Error):
        _issue(issues, "error", "invalid-resource-base64", f"{path}.data", "Resource data is not valid base64.")
        return None

    source_hash = data.get("hash")
    if source_hash:
        if not _MD5_PATTERN.fullmatch(source_hash):
            _issue(
                issues,
                "warning",
                "malformed-evernote-resource-hash",
                f"{path}.data.@hash",
                "Evernote resource hash is not a 32-character hexadecimal MD5 value; preserve for review.",
            )
        else:
            digest = hashlib.md5(decoded, usedforsecurity=False).hexdigest()
            if digest.casefold() != source_hash.casefold():
                _issue(
                    issues,
                    "error",
                    "resource-hash-mismatch",
                    f"{path}.data.@hash",
                    "Embedded resource bytes do not match the hash recorded by the ENEX export.",
                )
    return decoded


def inspect_enex_export(path: Path, *, max_bytes: int = DEFAULT_MAX_ENEX_BYTES) -> EnexExportReport:
    """Inspect one ENEX file without mutating the source, target, or extracted-resource state."""

    if max_bytes <= 0:
        raise ValueError("ENEX inspection limit must be positive.")

    source = path.expanduser()
    try:
        source_stat = source.lstat()
    except OSError as exc:
        raise ValueError("ENEX export is unavailable.") from exc
    if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
        raise ValueError("ENEX export must be a regular file, not a symbolic link.")
    if source_stat.st_size > max_bytes:
        raise ValueError(
            f"ENEX export is {source_stat.st_size} bytes, exceeding the configured {max_bytes}-byte inspection limit."
        )

    source = source.resolve(strict=True)
    raw = source.read_bytes()
    source_sha256 = hashlib.sha256(raw).hexdigest()

    # Standard ENEX files commonly include an external DOCTYPE declaration. ElementTree
    # does not need that DTD for inspection. Explicit entity declarations are rejected before
    # parsing so an ENEX file cannot introduce custom entity expansion into this tool.
    if b"<!ENTITY" in raw:
        raise ValueError("ENEX export contains an entity declaration and was refused for safe inspection.")

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"ENEX export is not well-formed XML: {exc}") from exc
    if root.tag != "en-export":
        raise ValueError("ENEX export root must be <en-export>.")

    issues: list[MigrationIssue] = []
    application = root.get("application")
    version = root.get("version")
    if application is None or not application.strip():
        _issue(issues, "warning", "missing-application", "$.@application", "ENEX export does not identify its source application.")
        application = None
    if version is None or not version.strip():
        _issue(issues, "warning", "missing-version", "$.@version", "ENEX export does not identify its source application version.")
        version = None
    exported_at = _normalize_enex_timestamp(
        root.get("export-date"),
        path="$.@export-date",
        issues=issues,
        required=True,
    )

    all_tags: set[str] = set()
    mime_counts: Counter[str] = Counter()
    resource_count = 0
    embedded_resource_bytes = 0
    deleted_note_count = 0
    notes = list(root.findall("note"))

    for note_index, note in enumerate(notes):
        note_path = f"$.note[{note_index}]"
        _required_text(note, "title", path=note_path, issues=issues)
        content = _required_text(note, "content", path=note_path, issues=issues)
        if content is not None and "<en-note" not in content:
            _issue(
                issues,
                "warning",
                "unexpected-enml-content",
                f"{note_path}.content",
                "Note content does not contain an <en-note> root marker; preserve the original ENML for manual review.",
            )

        _normalize_enex_timestamp(
            note.findtext("created"),
            path=f"{note_path}.created",
            issues=issues,
        )
        _normalize_enex_timestamp(
            note.findtext("updated"),
            path=f"{note_path}.updated",
            issues=issues,
        )
        deleted = note.findtext("deleted")
        if deleted and deleted.strip():
            deleted_note_count += 1
            _normalize_enex_timestamp(
                deleted,
                path=f"{note_path}.deleted",
                issues=issues,
            )

        for tag_index, tag in enumerate(note.findall("tag")):
            value = tag.text or ""
            if not value.strip():
                _issue(issues, "warning", "empty-tag", f"{note_path}.tag[{tag_index}]", "Empty Evernote tag was ignored.")
                continue
            all_tags.add(value.strip())

        for resource_index, resource in enumerate(note.findall("resource")):
            resource_count += 1
            resource_path = f"{note_path}.resource[{resource_index}]"
            mime = _required_text(resource, "mime", path=resource_path, issues=issues)
            if mime is not None:
                mime_counts[mime.strip().casefold()] += 1
            decoded = _resource_bytes(resource, path=resource_path, issues=issues)
            if decoded is not None:
                embedded_resource_bytes += len(decoded)

    if resource_count:
        _issue(
            issues,
            "warning",
            "embedded-resources-require-controlled-extraction",
            "$.note[*].resource",
            "ENEX embeds attachment bytes inside XML. Native import must extract and re-hash them through a separate controlled migration stage.",
        )

    return EnexExportReport(
        source_path=str(source),
        source_sha256=source_sha256,
        source_size_bytes=len(raw),
        application=application,
        version=version,
        exported_at=exported_at,
        note_count=len(notes),
        deleted_note_count=deleted_note_count,
        unique_tag_count=len(all_tags),
        resource_count=resource_count,
        embedded_resource_bytes=embedded_resource_bytes,
        resource_mime_type_counts=dict(sorted(mime_counts.items())),
        issues=issues,
    )


def format_text_report(report: EnexExportReport) -> str:
    """Return a compact human-readable ENEX inspection report."""

    lines = [
        "GoreeCloud Notes ENEX migration inspection",
        f"Source: {report.source_path}",
        f"SHA-256: {report.source_sha256}",
        f"Bytes: {report.source_size_bytes}",
        f"Application: {report.application or 'unknown'}",
        f"Version: {report.version or 'unknown'}",
        f"Exported at: {report.exported_at or 'invalid/unknown'}",
        f"Notes: {report.note_count}",
        f"Deleted notes: {report.deleted_note_count}",
        f"Unique tags: {report.unique_tag_count}",
        f"Embedded resources: {report.resource_count}",
        f"Embedded resource bytes: {report.embedded_resource_bytes}",
        f"Metadata valid: {'yes' if report.metadata_valid else 'no'}",
        f"Errors: {report.error_count}",
        f"Warnings: {report.warning_count}",
        "Source mutation performed: no",
        "Target mutation performed: no",
    ]
    if report.issues:
        lines.append("Issues:")
        lines.extend(
            f"- [{issue.severity}] {issue.code} {issue.path}: {issue.message}"
            for issue in report.issues
        )
    return "\n".join(lines) + "\n"
