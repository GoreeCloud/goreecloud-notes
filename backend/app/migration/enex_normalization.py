"""Provider-neutral Evernote ENEX note normalization with exact ENML preservation."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import stat
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .enex import DEFAULT_MAX_ENEX_BYTES, inspect_enex_export
from .enex_resources import EVIDENCE_FILENAME

NORMALIZATION_FORMAT = "goreecloud-notes-enex-normalization"
NORMALIZATION_SCHEMA_VERSION = 1
DEFAULT_MAX_ENEX_EVIDENCE_BYTES = 32 * 1024 * 1024
_ENEX_TIMESTAMP = "%Y%m%dT%H%M%SZ"
_XML_ENCODING_PATTERN = re.compile(rb"<\?xml[^>]*encoding=[\"']([^\"']+)[\"']", re.IGNORECASE)
_ENML_CDATA_PATTERN = re.compile(
    rb"<content\s*>\s*<!\[CDATA\[(.*?)\]\]>\s*</content\s*>",
    re.DOTALL,
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _iso_timestamp(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    parsed = datetime.strptime(value.strip(), _ENEX_TIMESTAMP).replace(tzinfo=UTC)
    return parsed.isoformat().replace("+00:00", "Z")


def _element_snapshot(element: ET.Element | None) -> dict[str, Any] | None:
    if element is None:
        return None
    return {
        "name": element.tag,
        "attributes": dict(sorted(element.attrib.items())),
        "text": element.text,
        "children": [_element_snapshot(child) for child in list(element)],
    }


def _exact_enml_payloads(raw: bytes, expected_notes: int) -> list[tuple[str, str, int]]:
    encoding_match = _XML_ENCODING_PATTERN.search(raw[:512])
    if encoding_match is not None:
        source_encoding = encoding_match.group(1).decode("ascii", errors="strict").casefold().replace("_", "-")
        if source_encoding not in {"utf-8", "utf8"}:
            raise ValueError(
                "ENEX normalization requires a UTF-8 source so original ENML CDATA bytes can be preserved exactly."
            )

    payloads = _ENML_CDATA_PATTERN.findall(raw)
    if len(payloads) != expected_notes:
        raise ValueError(
            "ENEX normalization requires exactly one UTF-8 CDATA <content> payload per note; "
            "the source cannot yet be normalized without weakening exact ENML preservation."
        )

    result: list[tuple[str, str, int]] = []
    for note_index, payload in enumerate(payloads):
        try:
            enml = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"ENEX note[{note_index}] ENML is not valid UTF-8 and cannot be preserved exactly."
            ) from exc
        result.append((enml, _sha256_bytes(payload), len(payload)))
    return result


def _source_bytes_if_unchanged(source: Path, *, sha256: str, size_bytes: int) -> bytes:
    try:
        source_stat = source.lstat()
    except OSError as exc:
        raise ValueError("ENEX source became unavailable during normalization.") from exc
    if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
        raise ValueError("ENEX source changed type during normalization.")
    raw = source.read_bytes()
    if len(raw) != size_bytes or _sha256_bytes(raw) != sha256:
        raise ValueError("ENEX source changed during normalization; no normalization artifact was created.")
    return raw


def _read_evidence(path: Path, *, max_bytes: int) -> tuple[dict[str, Any], str, int]:
    if max_bytes <= 0:
        raise ValueError("ENEX resource-evidence size limit must be positive.")

    source = path.expanduser()
    try:
        source_stat = source.lstat()
    except OSError as exc:
        raise ValueError("ENEX resource evidence is unavailable.") from exc
    if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
        raise ValueError("ENEX resource evidence must be a regular file, not a symbolic link.")
    if source_stat.st_size > max_bytes:
        raise ValueError(
            f"ENEX resource evidence is {source_stat.st_size} bytes, exceeding the configured {max_bytes}-byte limit."
        )

    raw = source.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("ENEX resource evidence is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("ENEX resource evidence root must be a JSON object.")
    return payload, _sha256_bytes(raw), len(raw)


def _decode_resource(resource: ET.Element) -> bytes:
    data = resource.find("data")
    if data is None or data.get("encoding") != "base64":
        raise ValueError("Validated ENEX resource no longer contains supported base64 data.")
    compact = "".join((data.text or "").split())
    try:
        return base64.b64decode(compact.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError("Validated ENEX resource data is no longer valid base64.") from exc


def _source_file_name(resource: ET.Element) -> str | None:
    value = resource.findtext("resource-attributes/file-name")
    if value is None or not value.strip():
        return None
    return value.strip()


def _safe_relative_resource_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("ENEX resource evidence contains an invalid generated relative path.")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        raise ValueError("ENEX resource evidence contains an unsafe generated relative path.")
    return candidate.as_posix()


def _resource_expectations(root: ET.Element) -> tuple[list[dict[str, Any]], int]:
    resources: list[dict[str, Any]] = []
    total_bytes = 0
    seen_sha256: dict[str, str] = {}

    for note_index, note in enumerate(root.findall("note")):
        for resource_index, resource in enumerate(note.findall("resource")):
            decoded = _decode_resource(resource)
            sha256 = _sha256_bytes(decoded)
            size_bytes = len(decoded)
            total_bytes += size_bytes
            relative_path = (
                f"resources/note-{note_index:06d}/"
                f"resource-{resource_index:06d}-{sha256}.bin"
            )
            duplicate_of = seen_sha256.get(sha256)
            seen_sha256.setdefault(sha256, relative_path)
            data = resource.find("data")
            resources.append(
                {
                    "noteIndex": note_index,
                    "resourceIndex": resource_index,
                    "mime": (resource.findtext("mime") or "").strip().casefold(),
                    "source": {
                        "fileName": _source_file_name(resource),
                        "evernoteMd5": data.get("hash") if data is not None else None,
                    },
                    "output": {
                        "relativePath": relative_path,
                        "sha256": sha256,
                        "sizeBytes": size_bytes,
                    },
                    "duplicateOf": duplicate_of,
                }
            )
    return resources, total_bytes


def _validate_resource_evidence(
    evidence: dict[str, Any],
    *,
    source_sha256: str,
    source_size_bytes: int,
    expected_resources: list[dict[str, Any]],
    expected_total_bytes: int,
) -> None:
    if evidence.get("format") != "goreecloud-notes-enex-resource-evidence" or evidence.get("schemaVersion") != 1:
        raise ValueError("Unsupported ENEX resource-evidence format or schema version.")

    source = evidence.get("source")
    if not isinstance(source, dict):
        raise ValueError("ENEX resource evidence is missing its source record.")
    if source.get("provider") != "evernote" or source.get("format") != "enex":
        raise ValueError("ENEX resource evidence does not identify an Evernote ENEX source.")
    if source.get("sha256") != source_sha256 or source.get("sizeBytes") != source_size_bytes:
        raise ValueError("ENEX resource evidence does not match the exact source ENEX fingerprint.")

    inspection = evidence.get("inspection")
    if not isinstance(inspection, dict) or inspection.get("metadataValid") is not True:
        raise ValueError("ENEX resource evidence is not tied to a metadata-valid inspection.")

    extraction = evidence.get("extraction")
    if not isinstance(extraction, dict):
        raise ValueError("ENEX resource evidence is missing extraction status.")
    required_extraction = {
        "complete": True,
        "resourceCount": len(expected_resources),
        "extractedBytes": expected_total_bytes,
        "evidenceFile": EVIDENCE_FILENAME,
        "sourceMutationPerformed": False,
        "targetDatabaseMutationPerformed": False,
        "outputOverwritePerformed": False,
    }
    for key, expected in required_extraction.items():
        if extraction.get(key) != expected:
            raise ValueError(f"ENEX resource evidence extraction field {key!r} does not match the validated source.")

    resources = evidence.get("resources")
    if not isinstance(resources, list) or len(resources) != len(expected_resources):
        raise ValueError("ENEX resource evidence does not contain the expected one-to-one resource inventory.")

    for index, (actual, expected) in enumerate(zip(resources, expected_resources, strict=True)):
        if not isinstance(actual, dict):
            raise ValueError(f"ENEX resource evidence entry {index} must be an object.")
        actual_output = actual.get("output")
        if not isinstance(actual_output, dict):
            raise ValueError(f"ENEX resource evidence entry {index} is missing output evidence.")
        relative_path = _safe_relative_resource_path(actual_output.get("relativePath"))
        if not _SHA256_PATTERN.fullmatch(str(actual_output.get("sha256", ""))):
            raise ValueError(f"ENEX resource evidence entry {index} contains an invalid SHA-256 value.")
        normalized_actual = {
            "noteIndex": actual.get("noteIndex"),
            "resourceIndex": actual.get("resourceIndex"),
            "mime": actual.get("mime"),
            "source": actual.get("source"),
            "output": {
                "relativePath": relative_path,
                "sha256": actual_output.get("sha256"),
                "sizeBytes": actual_output.get("sizeBytes"),
            },
            "duplicateOf": actual.get("duplicateOf"),
        }
        if normalized_actual != expected:
            raise ValueError(f"ENEX resource evidence entry {index} does not match the validated source resource bytes.")


def _resource_reference(entry: dict[str, Any], resource: ET.Element) -> dict[str, Any]:
    return {
        "source": {
            "provider": "evernote",
            "noteIndex": entry["noteIndex"],
            "resourceIndex": entry["resourceIndex"],
            "fileName": entry["source"]["fileName"],
            "evernoteMd5": entry["source"]["evernoteMd5"],
        },
        "mimeType": {
            "source": resource.findtext("mime") or "",
            "normalized": entry["mime"],
        },
        "binary": {
            "status": "extracted-and-verified",
            "relativePath": entry["output"]["relativePath"],
            "sha256": entry["output"]["sha256"],
            "sizeBytes": entry["output"]["sizeBytes"],
            "duplicateOf": entry["duplicateOf"],
        },
        "sourceMetadata": {
            "resourceAttributes": _element_snapshot(resource.find("resource-attributes")),
            "recognition": _element_snapshot(resource.find("recognition")),
            "alternateData": _element_snapshot(resource.find("alternate-data")),
        },
    }


def build_enex_normalization(
    source_path: Path,
    *,
    resource_evidence_path: Path | None = None,
    max_bytes: int = DEFAULT_MAX_ENEX_BYTES,
    max_evidence_bytes: int = DEFAULT_MAX_ENEX_EVIDENCE_BYTES,
) -> dict[str, Any]:
    """Build a deterministic zero-write ENEX normalization artifact without converting ENML."""

    if max_bytes <= 0:
        raise ValueError("ENEX normalization input-size limit must be positive.")
    if max_evidence_bytes <= 0:
        raise ValueError("ENEX resource-evidence size limit must be positive.")

    report = inspect_enex_export(source_path, max_bytes=max_bytes)
    if not report.metadata_valid:
        error_codes = sorted({issue.code for issue in report.issues if issue.severity == "error"})
        suffix = f" ({', '.join(error_codes)})" if error_codes else ""
        raise ValueError(f"Source metadata validation failed; ENEX normalization was not created{suffix}.")

    source = Path(report.source_path)
    raw = _source_bytes_if_unchanged(
        source,
        sha256=report.source_sha256,
        size_bytes=report.source_size_bytes,
    )

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("ENEX source became unparsable after inspection.") from exc

    exact_enml = _exact_enml_payloads(raw, report.note_count)
    expected_resources, total_resource_bytes = _resource_expectations(root)

    evidence: dict[str, Any] | None = None
    evidence_sha256: str | None = None
    evidence_size_bytes: int | None = None
    if resource_evidence_path is not None:
        evidence, evidence_sha256, evidence_size_bytes = _read_evidence(
            resource_evidence_path,
            max_bytes=max_evidence_bytes,
        )
        _validate_resource_evidence(
            evidence,
            source_sha256=report.source_sha256,
            source_size_bytes=report.source_size_bytes,
            expected_resources=expected_resources,
            expected_total_bytes=total_resource_bytes,
        )
    elif expected_resources:
        raise ValueError(
            "ENEX normalization requires the validated resource-evidence JSON when the source contains embedded resources."
        )

    evidence_resources = evidence["resources"] if evidence is not None else []
    evidence_by_note: dict[int, list[dict[str, Any]]] = {}
    for entry in evidence_resources:
        evidence_by_note.setdefault(int(entry["noteIndex"]), []).append(entry)

    notes: list[dict[str, Any]] = []
    for note_index, note in enumerate(root.findall("note")):
        enml, enml_sha256, enml_size_bytes = exact_enml[note_index]
        note_resources = list(note.findall("resource"))
        resource_entries = evidence_by_note.get(note_index, [])
        if len(resource_entries) != len(note_resources):
            raise ValueError("ENEX resource evidence no longer aligns with the source note/resource ordering.")

        record: dict[str, Any] = {
            "source": {
                "provider": "evernote",
                "noteIndex": note_index,
            },
            "content": {
                "title": note.findtext("title") or "",
                "enml": enml,
                "enmlEncoding": "utf-8",
                "enmlSha256": enml_sha256,
                "enmlSizeBytes": enml_size_bytes,
                "conversionStatus": "preserved-source-enml",
            },
            "timestamps": {
                "createdAt": _iso_timestamp(note.findtext("created")),
                "updatedAt": _iso_timestamp(note.findtext("updated")),
                "deletedAt": _iso_timestamp(note.findtext("deleted")),
            },
            "tags": [
                {
                    "sourceOrder": tag_index,
                    "value": tag.text or "",
                    "normalizedName": (tag.text or "").strip(),
                }
                for tag_index, tag in enumerate(note.findall("tag"))
            ],
            "resources": [
                _resource_reference(entry, resource)
                for entry, resource in zip(resource_entries, note_resources, strict=True)
            ],
            "sourceMetadata": {
                "noteAttributes": _element_snapshot(note.find("note-attributes")),
            },
        }
        record["recordSha256"] = _canonical_sha256(record)
        notes.append(record)

    warning_issues = [asdict(issue) for issue in report.issues if issue.severity == "warning"]
    normalization: dict[str, Any] = {
        "format": NORMALIZATION_FORMAT,
        "schemaVersion": NORMALIZATION_SCHEMA_VERSION,
        "source": {
            "provider": "evernote",
            "format": "enex",
            "application": report.application,
            "version": report.version,
            "exportedAt": report.exported_at,
            "sha256": report.source_sha256,
            "sizeBytes": report.source_size_bytes,
        },
        "validation": {
            "sourceMetadataValid": True,
            "sourceWarnings": warning_issues,
            "resourceEvidenceRequired": bool(expected_resources),
            "resourceEvidenceValidated": evidence is not None,
            "exactEnmlPreserved": True,
            "enmlConversionPerformed": False,
            "nativeDocumentCreated": False,
            "sourceMutationPerformed": False,
            "targetMutationPerformed": False,
        },
        "inventory": {
            "notes": report.note_count,
            "deletedNotes": report.deleted_note_count,
            "uniqueTags": report.unique_tag_count,
            "resources": report.resource_count,
            "embeddedResourceBytes": report.embedded_resource_bytes,
        },
        "resourceEvidence": (
            {
                "format": evidence["format"],
                "schemaVersion": evidence["schemaVersion"],
                "sha256": evidence_sha256,
                "sizeBytes": evidence_size_bytes,
            }
            if evidence is not None
            else None
        ),
        "notes": notes,
    }

    # A final source fingerprint check closes the window between parsing and serialization.
    _source_bytes_if_unchanged(
        source,
        sha256=report.source_sha256,
        size_bytes=report.source_size_bytes,
    )
    return normalization


def serialize_enex_normalization(normalization: dict[str, Any]) -> str:
    """Serialize ENEX normalization deterministically for review and later gated conversion."""

    return json.dumps(
        normalization,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic provider-neutral Evernote ENEX normalization artifact while preserving "
            "the original ENML and never writing native GoreeCloud Notes data."
        )
    )
    parser.add_argument("export", type=Path, help="Path to an Evernote ENEX export.")
    parser.add_argument(
        "--resource-evidence",
        type=Path,
        default=None,
        help=(
            "Path to enex-resource-evidence.json. Required when the ENEX source contains embedded resources."
        ),
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_ENEX_BYTES,
        help=f"Maximum ENEX size to normalize (default: {DEFAULT_MAX_ENEX_BYTES} bytes).",
    )
    parser.add_argument(
        "--max-evidence-bytes",
        type=int,
        default=DEFAULT_MAX_ENEX_EVIDENCE_BYTES,
        help=(
            "Maximum resource-evidence JSON size "
            f"(default: {DEFAULT_MAX_ENEX_EVIDENCE_BYTES} bytes)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_bytes <= 0:
        parser.error("--max-bytes must be positive.")
    if args.max_evidence_bytes <= 0:
        parser.error("--max-evidence-bytes must be positive.")
    try:
        normalization = build_enex_normalization(
            args.export,
            resource_evidence_path=args.resource_evidence,
            max_bytes=args.max_bytes,
            max_evidence_bytes=args.max_evidence_bytes,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(serialize_enex_normalization(normalization))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
