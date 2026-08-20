"""Deterministic zero-write Evernote ENML to GoreeCloud Blocks conversion review."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from ..documents import SAFE_INLINE_IMAGE_MEDIA_TYPES, canonicalize_document
from .enex import DEFAULT_MAX_ENEX_BYTES
from .enex_normalization import (
    DEFAULT_MAX_ENEX_EVIDENCE_BYTES,
    NORMALIZATION_FORMAT,
    NORMALIZATION_SCHEMA_VERSION,
    build_enex_normalization,
)

CONVERSION_FORMAT = "goreecloud-notes-enex-conversion"
CONVERSION_SCHEMA_VERSION = 1
DEFAULT_MAX_NORMALIZATION_BYTES = 384 * 1024 * 1024
BLOCK_TAGS = frozenset({
    "div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol",
    "blockquote", "pre", "hr", "table",
})
MARK_TAGS = {
    "b": "bold", "strong": "bold", "i": "italic", "em": "italic",
    "s": "strike", "strike": "strike", "del": "strike", "code": "code",
}
NEUTRAL_INLINE_TAGS = frozenset({
    "span", "font", "abbr", "acronym", "bdo", "big", "cite", "dfn", "ins",
    "kbd", "q", "samp", "small", "sub", "sup", "tt", "u", "var",
})
LOSSY_INLINE_TAGS = NEUTRAL_INLINE_TAGS - {"span"}
LAYOUT_ATTRIBUTES = frozenset({
    "style", "align", "bgcolor", "color", "face", "size", "width", "height",
    "border", "cellpadding", "cellspacing", "valign", "dir", "lang",
    "{http://www.w3.org/XML/1998/namespace}lang",
})


class ConversionBlocked(ValueError):
    """One ENML construct cannot safely produce a native candidate document."""

    def __init__(self, code: str, message: str, *, path: str) -> None:
        super().__init__(message)
        self.issue = {"code": code, "message": message, "path": path}


@dataclass(frozen=True)
class ResourceEvent:
    resource_index: int
    attachment_id: str
    inline_image: bool
    alt: str
    label: str
    path: str


@dataclass
class ConversionState:
    note_index: int
    source_sha256: str
    resources: list[dict[str, Any]]
    review_notices: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    resource_references: dict[int, int] = field(default_factory=dict)

    def notice(
        self,
        code: str,
        message: str,
        *,
        path: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        item: dict[str, Any] = {"code": code, "message": message, "path": path}
        if details:
            item["details"] = details
        if item not in self.review_notices:
            self.review_notices.append(item)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("ENEX normalization contains an invalid resource relative path.")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or "." in candidate.parts or ".." in candidate.parts:
        raise ValueError("ENEX normalization contains an unsafe resource relative path.")
    return candidate.as_posix()


def _read_json(path: Path, *, max_bytes: int, label: str) -> tuple[dict[str, Any], str, int]:
    if max_bytes <= 0:
        raise ValueError(f"{label} size limit must be positive.")
    source = path.expanduser()
    try:
        info = source.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable.") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{label} must be a regular file, not a symbolic link.")
    if info.st_size > max_bytes:
        raise ValueError(f"{label} exceeds the configured {max_bytes}-byte limit.")
    raw = source.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} root must be a JSON object.")
    return payload, _sha256_bytes(raw), len(raw)


def _validate_normalization(normalization: dict[str, Any]) -> None:
    if (
        normalization.get("format") != NORMALIZATION_FORMAT
        or normalization.get("schemaVersion") != NORMALIZATION_SCHEMA_VERSION
    ):
        raise ValueError("Unsupported ENEX normalization format or schema version.")
    validation = normalization.get("validation")
    if not isinstance(validation, dict):
        raise ValueError("ENEX normalization is missing validation evidence.")
    for key, expected in {
        "sourceMetadataValid": True,
        "exactEnmlPreserved": True,
        "enmlConversionPerformed": False,
        "nativeDocumentCreated": False,
        "sourceMutationPerformed": False,
        "targetMutationPerformed": False,
    }.items():
        if validation.get(key) != expected:
            raise ValueError(f"ENEX normalization validation field {key!r} is incompatible with conversion.")
    source = normalization.get("source")
    if not isinstance(source, dict) or source.get("provider") != "evernote" or source.get("format") != "enex":
        raise ValueError("ENEX normalization source record is invalid.")
    if not isinstance(source.get("sha256"), str) or len(source["sha256"]) != 64:
        raise ValueError("ENEX normalization source SHA-256 is invalid.")
    if not isinstance(source.get("sizeBytes"), int) or source["sizeBytes"] < 0:
        raise ValueError("ENEX normalization source byte size is invalid.")
    notes = normalization.get("notes")
    if not isinstance(notes, list):
        raise ValueError("ENEX normalization notes must be an array.")
    for note_index, note in enumerate(notes):
        if not isinstance(note, dict):
            raise ValueError(f"ENEX normalization note[{note_index}] must be an object.")
        recorded = note.get("recordSha256")
        unsigned = dict(note)
        unsigned.pop("recordSha256", None)
        if not isinstance(recorded, str) or _canonical_sha256(unsigned) != recorded:
            raise ValueError(f"ENEX normalization note[{note_index}] record fingerprint is invalid.")
        content = note.get("content")
        if not isinstance(content, dict):
            raise ValueError(f"ENEX normalization note[{note_index}] is missing content.")
        enml = content.get("enml")
        if not isinstance(enml, str) or content.get("enmlEncoding") != "utf-8":
            raise ValueError(f"ENEX normalization note[{note_index}] does not contain exact UTF-8 ENML.")
        raw = enml.encode("utf-8")
        if content.get("enmlSizeBytes") != len(raw) or content.get("enmlSha256") != _sha256_bytes(raw):
            raise ValueError(f"ENEX normalization note[{note_index}] ENML fingerprint is invalid.")
        resources = note.get("resources")
        if not isinstance(resources, list):
            raise ValueError(f"ENEX normalization note[{note_index}] resources must be an array.")
        for resource_index, resource in enumerate(resources):
            if not isinstance(resource, dict):
                raise ValueError(f"ENEX normalization note[{note_index}] resource[{resource_index}] must be an object.")
            binary = resource.get("binary")
            if not isinstance(binary, dict) or binary.get("status") != "extracted-and-verified":
                raise ValueError(f"ENEX normalization note[{note_index}] resource[{resource_index}] lacks verified binary evidence.")
            _safe_relative_path(binary.get("relativePath"))
            if not isinstance(binary.get("sha256"), str) or len(binary["sha256"]) != 64:
                raise ValueError(f"ENEX normalization note[{note_index}] resource[{resource_index}] SHA-256 is invalid.")
            if not isinstance(binary.get("sizeBytes"), int) or binary["sizeBytes"] < 0:
                raise ValueError(f"ENEX normalization note[{note_index}] resource[{resource_index}] byte size is invalid.")


def _attachment_id(source_sha256: str, note_index: int, resource_index: int, resource_sha256: str) -> str:
    seed = f"goreecloud-notes:enex:{source_sha256}:note:{note_index}:resource:{resource_index}:{resource_sha256}"
    return str(uuid5(NAMESPACE_URL, seed))


def _record_attributes(state: ConversionState, element: ET.Element, *, tag: str, path: str) -> None:
    attributes = {key: value for key, value in sorted(element.attrib.items()) if key in LAYOUT_ATTRIBUTES}
    if attributes:
        state.notice(
            "enml-layout-style-not-represented",
            "ENML layout or styling attributes are preserved in source ENML but are not represented by goreecloud.blocks v1.",
            path=path,
            details={"tag": tag, "attributes": attributes},
        )


def _text_node(text: str, marks: tuple[str, ...] = ()) -> dict[str, Any] | None:
    if not text:
        return None
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = [{"type": mark} for mark in marks]
    return node


def _resource_event(state: ConversionState, element: ET.Element, *, path: str) -> ResourceEvent:
    resource_hash = element.attrib.get("hash", "").strip().casefold()
    media_type = element.attrib.get("type", "").strip().casefold()
    if not resource_hash:
        raise ConversionBlocked("en-media-missing-hash", "Evernote en-media is missing its required resource hash.", path=path)
    matches: list[tuple[int, dict[str, Any]]] = []
    for index, resource in enumerate(state.resources):
        source = resource.get("source")
        candidate = source.get("evernoteMd5") if isinstance(source, dict) else None
        if isinstance(candidate, str) and candidate.casefold() == resource_hash:
            matches.append((index, resource))
    if not matches:
        raise ConversionBlocked("en-media-resource-not-found", "Evernote en-media does not match normalized resource evidence.", path=path)
    resource_index, resource = matches[0]
    if len(matches) > 1:
        state.notice(
            "duplicate-en-media-resource-hash",
            "Multiple source resources share the en-media hash; the first source resource is used deterministically.",
            path=path,
            details={"matchingResourceIndexes": [item[0] for item in matches]},
        )
    mime = resource.get("mimeType")
    normalized_mime = mime.get("normalized") if isinstance(mime, dict) else None
    if not isinstance(normalized_mime, str) or not normalized_mime:
        raise ConversionBlocked("resource-mime-missing", "Normalized resource evidence is missing a MIME type.", path=path)
    if media_type and media_type != normalized_mime:
        raise ConversionBlocked("en-media-mime-mismatch", "Evernote en-media MIME type does not match normalized resource evidence.", path=path)
    binary = resource["binary"]
    source = resource.get("source")
    file_name = source.get("fileName") if isinstance(source, dict) else None
    state.resource_references[resource_index] = state.resource_references.get(resource_index, 0) + 1
    return ResourceEvent(
        resource_index=resource_index,
        attachment_id=_attachment_id(state.source_sha256, state.note_index, resource_index, binary["sha256"]),
        inline_image=normalized_mime in SAFE_INLINE_IMAGE_MEDIA_TYPES,
        alt=element.attrib.get("alt", "").strip(),
        label=file_name if isinstance(file_name, str) and file_name else normalized_mime,
        path=path,
    )


def _inline_events(
    element: ET.Element,
    state: ConversionState,
    *,
    path: str,
    marks: tuple[str, ...] = (),
) -> list[dict[str, Any] | ResourceEvent]:
    tag = _local_name(element.tag)
    if tag in BLOCK_TAGS:
        raise ConversionBlocked("block-element-in-inline-context", f"ENML block element <{tag}> appears in inline context.", path=path)
    _record_attributes(state, element, tag=tag, path=path)
    if tag == "br":
        return [{"type": "hardBreak"}]
    if tag == "en-media":
        return [_resource_event(state, element, path=path)]
    if tag == "en-todo":
        checked = element.attrib.get("checked", "false").strip().casefold()
        state.notice(
            "en-todo-flattened",
            "Evernote checkbox semantics are not available in goreecloud.blocks v1; a textual checkbox marker is used.",
            path=path,
            details={"checked": checked},
        )
        return [{"type": "text", "text": "[x] " if checked == "true" else "[ ] "}]
    if tag == "en-crypt":
        state.notice(
            "en-crypt-not-converted",
            "Encrypted Evernote content requires a separate decryption workflow; exact source ENML remains preserved.",
            path=path,
        )
        return [{"type": "text", "text": "[Encrypted Evernote content]"}]
    next_marks = marks
    mark = MARK_TAGS.get(tag)
    if mark and mark not in next_marks:
        next_marks = (*next_marks, mark)
    if tag == "a":
        href = element.attrib.get("href")
        if href:
            state.links.append({"href": href, "path": path})
            state.notice(
                "enml-link-target-not-represented",
                "Generic ENML link targets are preserved as review evidence but are not represented by goreecloud.blocks v1.",
                path=path,
                details={"href": href},
            )
    elif tag in LOSSY_INLINE_TAGS:
        state.notice(
            "enml-inline-semantics-not-represented",
            f"ENML inline <{tag}> semantics are preserved in source ENML but flattened to supported native text.",
            path=path,
            details={"tag": tag},
        )
    elif tag not in MARK_TAGS and tag not in NEUTRAL_INLINE_TAGS:
        raise ConversionBlocked("unsupported-enml-inline-element", f"ENML inline element <{tag}> is not supported.", path=path)
    events: list[dict[str, Any] | ResourceEvent] = []
    first = _text_node(element.text or "", next_marks)
    if first:
        events.append(first)
    for index, child in enumerate(list(element)):
        child_path = f"{path}/{_local_name(child.tag)}[{index}]"
        events.extend(_inline_events(child, state, path=child_path, marks=next_marks))
        tail = _text_node(child.tail or "", next_marks)
        if tail:
            events.append(tail)
    return events


def _events_to_blocks(events: list[dict[str, Any] | ResourceEvent], state: ConversionState) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    inline: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal inline
        if inline:
            blocks.append({"type": "paragraph", "content": inline})
            inline = []

    for event in events:
        if isinstance(event, ResourceEvent):
            flush()
            if event.inline_image:
                blocks.append({"type": "attachmentImage", "attachment_id": event.attachment_id, "alt": event.alt[:512]})
            else:
                blocks.append({"type": "paragraph", "content": [{"type": "text", "text": f"[Attachment: {event.label}]"}]})
                state.notice(
                    "non-image-en-media-placeholder",
                    "Non-image en-media placement is represented by a textual placeholder; the attachment remains separately bound for later import.",
                    path=event.path,
                    details={"resourceIndex": event.resource_index, "attachmentId": event.attachment_id},
                )
        else:
            inline.append(event)
    flush()
    return blocks


def _container_blocks(element: ET.Element, state: ConversionState, *, path: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    pending: list[dict[str, Any] | ResourceEvent] = []
    first = _text_node(element.text or "")
    if first:
        pending.append(first)

    def flush_pending() -> None:
        nonlocal pending
        if pending:
            blocks.extend(_events_to_blocks(pending, state))
            pending = []

    for index, child in enumerate(list(element)):
        tag = _local_name(child.tag)
        child_path = f"{path}/{tag}[{index}]"
        if tag in BLOCK_TAGS:
            flush_pending()
            blocks.extend(_convert_block(child, state, path=child_path))
        else:
            pending.extend(_inline_events(child, state, path=child_path))
        tail = _text_node(child.tail or "")
        if tail:
            pending.append(tail)
    flush_pending()
    return blocks


def _heading_block(element: ET.Element, state: ConversionState, *, path: str, level: int) -> list[dict[str, Any]]:
    _record_attributes(state, element, tag=f"h{level}", path=path)
    events: list[dict[str, Any] | ResourceEvent] = []
    first = _text_node(element.text or "")
    if first:
        events.append(first)
    for index, child in enumerate(list(element)):
        child_path = f"{path}/{_local_name(child.tag)}[{index}]"
        events.extend(_inline_events(child, state, path=child_path))
        tail = _text_node(child.tail or "")
        if tail:
            events.append(tail)
    if any(isinstance(event, ResourceEvent) for event in events):
        raise ConversionBlocked("en-media-in-heading", "ENML media inside a heading cannot be represented by goreecloud.blocks v1.", path=path)
    native_level = min(level, 3)
    if level > 3:
        state.notice(
            "heading-level-collapsed",
            "ENML heading levels 4-6 are represented as native heading level 3.",
            path=path,
            details={"sourceLevel": level, "nativeLevel": native_level},
        )
    return [{"type": "heading", "level": native_level, "content": events}]


def _list_block(element: ET.Element, state: ConversionState, *, path: str, ordered: bool) -> list[dict[str, Any]]:
    _record_attributes(state, element, tag="ol" if ordered else "ul", path=path)
    items: list[dict[str, Any]] = []
    for index, child in enumerate(list(element)):
        if _local_name(child.tag) != "li":
            raise ConversionBlocked("invalid-enml-list-child", "ENML list contains a non-list-item child.", path=path)
        child_path = f"{path}/li[{index}]"
        _record_attributes(state, child, tag="li", path=child_path)
        content = _container_blocks(child, state, path=child_path) or [{"type": "paragraph", "content": []}]
        items.append({"type": "listItem", "content": content})
    return [{"type": "orderedList" if ordered else "bulletList", "content": items}]


def _convert_block(element: ET.Element, state: ConversionState, *, path: str) -> list[dict[str, Any]]:
    tag = _local_name(element.tag)
    if tag in {"div", "p"}:
        _record_attributes(state, element, tag=tag, path=path)
        return _container_blocks(element, state, path=path) or [{"type": "paragraph", "content": []}]
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return _heading_block(element, state, path=path, level=int(tag[1]))
    if tag in {"ul", "ol"}:
        return _list_block(element, state, path=path, ordered=tag == "ol")
    if tag == "blockquote":
        _record_attributes(state, element, tag=tag, path=path)
        return [{"type": "blockquote", "content": _container_blocks(element, state, path=path)}]
    if tag == "pre":
        _record_attributes(state, element, tag=tag, path=path)
        code = "".join(element.itertext())
        return [{"type": "codeBlock", "content": [{"type": "text", "text": code}] if code else []}]
    if tag == "hr":
        _record_attributes(state, element, tag=tag, path=path)
        return [{"type": "horizontalRule"}]
    if tag == "table":
        raise ConversionBlocked(
            "enml-table-not-supported",
            "ENML tables are not representable by goreecloud.blocks v1 and require a separately reviewed table migration strategy.",
            path=path,
        )
    raise ConversionBlocked("unsupported-enml-block-element", f"ENML block element <{tag}> is not supported.", path=path)


def _parse_enml(enml: str, *, note_index: int) -> ET.Element:
    if "<!ENTITY" in enml.upper():
        raise ConversionBlocked("enml-entity-declaration-refused", "ENML entity declarations are refused during conversion.", path=f"note[{note_index}]")
    try:
        root = ET.fromstring(enml)
    except ET.ParseError as exc:
        raise ConversionBlocked("invalid-enml-xml", "Preserved ENML is not parseable XML.", path=f"note[{note_index}]") from exc
    if _local_name(root.tag) != "en-note":
        raise ConversionBlocked("invalid-enml-root", "Preserved ENML root must be <en-note>.", path=f"note[{note_index}]")
    return root


def _planned_attachments(state: ConversionState) -> list[dict[str, Any]]:
    planned: list[dict[str, Any]] = []
    for resource_index, resource in enumerate(state.resources):
        binary = resource["binary"]
        mime = resource.get("mimeType")
        source = resource.get("source")
        normalized_mime = mime.get("normalized") if isinstance(mime, dict) else ""
        reference_count = state.resource_references.get(resource_index, 0)
        if reference_count == 0:
            state.notice(
                "unreferenced-enex-resource",
                "A verified ENEX resource is not referenced by ENML; it is retained as a planned attachment and requires placement review before import.",
                path=f"note[{state.note_index}]/resource[{resource_index}]",
                details={"resourceIndex": resource_index},
            )
        planned.append({
            "resourceIndex": resource_index,
            "attachmentId": _attachment_id(state.source_sha256, state.note_index, resource_index, binary["sha256"]),
            "fileName": source.get("fileName") if isinstance(source, dict) else None,
            "mimeType": normalized_mime,
            "binary": {
                "relativePath": _safe_relative_path(binary.get("relativePath")),
                "sha256": binary["sha256"],
                "sizeBytes": binary["sizeBytes"],
            },
            "safeInlineImage": normalized_mime in SAFE_INLINE_IMAGE_MEDIA_TYPES,
            "enmlReferenceCount": reference_count,
        })
    return planned


def _convert_note(note: dict[str, Any], *, source_sha256: str, note_index: int) -> dict[str, Any]:
    content = note["content"]
    state = ConversionState(note_index=note_index, source_sha256=source_sha256, resources=note["resources"])
    blocking: list[dict[str, Any]] = []
    document: dict[str, Any] | None = None
    try:
        root = _parse_enml(content["enml"], note_index=note_index)
        document = canonicalize_document({
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": _container_blocks(root, state, path=f"note[{note_index}]/en-note"),
        })
    except ConversionBlocked as exc:
        blocking.append(exc.issue)
    attachments = _planned_attachments(state)
    status = "blocked" if blocking else "converted-review-required" if state.review_notices else "converted"
    record: dict[str, Any] = {
        "source": note["source"],
        "contentEvidence": {
            "enmlSha256": content["enmlSha256"],
            "enmlSizeBytes": content["enmlSizeBytes"],
            "normalizationRecordSha256": note["recordSha256"],
        },
        "title": content["title"],
        "timestamps": note["timestamps"],
        "tags": note["tags"],
        "document": document,
        "attachments": attachments,
        "linksPreservedForReview": state.links,
        "reviewNotices": state.review_notices,
        "blockingIssues": blocking,
        "conversionStatus": status,
        "nativePersistencePerformed": False,
    }
    record["recordSha256"] = _canonical_sha256(record)
    return record


def build_enex_conversion(
    source_path: Path,
    normalization_path: Path,
    *,
    resource_evidence_path: Path | None = None,
    max_bytes: int = DEFAULT_MAX_ENEX_BYTES,
    max_evidence_bytes: int = DEFAULT_MAX_ENEX_EVIDENCE_BYTES,
    max_normalization_bytes: int = DEFAULT_MAX_NORMALIZATION_BYTES,
) -> dict[str, Any]:
    """Build a deterministic zero-write conversion artifact from exact validated inputs."""

    supplied, normalization_sha256, normalization_size_bytes = _read_json(
        normalization_path,
        max_bytes=max_normalization_bytes,
        label="ENEX normalization artifact",
    )
    _validate_normalization(supplied)
    rebuilt = build_enex_normalization(
        source_path,
        resource_evidence_path=resource_evidence_path,
        max_bytes=max_bytes,
        max_evidence_bytes=max_evidence_bytes,
    )
    if supplied != rebuilt:
        raise ValueError("ENEX normalization artifact does not exactly match a fresh normalization of the selected source/evidence.")
    source = rebuilt["source"]
    notes = [
        _convert_note(note, source_sha256=source["sha256"], note_index=index)
        for index, note in enumerate(rebuilt["notes"])
    ]
    blocked = sum(note["conversionStatus"] == "blocked" for note in notes)
    review_required = sum(note["conversionStatus"] == "converted-review-required" for note in notes)
    return {
        "format": CONVERSION_FORMAT,
        "schemaVersion": CONVERSION_SCHEMA_VERSION,
        "source": {
            "provider": "evernote",
            "format": "enex",
            "sha256": source["sha256"],
            "sizeBytes": source["sizeBytes"],
        },
        "normalizationEvidence": {
            "format": NORMALIZATION_FORMAT,
            "schemaVersion": NORMALIZATION_SCHEMA_VERSION,
            "sha256": normalization_sha256,
            "sizeBytes": normalization_size_bytes,
            "canonicalSha256": _canonical_sha256(rebuilt),
        },
        "conversion": {
            "documentFormat": "goreecloud.blocks",
            "documentVersion": 1,
            "noteCount": len(notes),
            "convertedNotes": len(notes) - blocked,
            "blockedNotes": blocked,
            "reviewRequiredNotes": review_required,
            "complete": blocked == 0,
            "reviewRequired": review_required > 0,
            "enmlConversionPerformed": True,
            "nativeNotesCreated": False,
            "nativeAttachmentsCreated": False,
            "sourceMutationPerformed": False,
            "targetDatabaseMutationPerformed": False,
        },
        "notes": notes,
    }


def serialize_enex_conversion(artifact: dict[str, Any]) -> str:
    return json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert exact-preservation GoreeCloud Notes ENEX normalization into deterministic "
            "goreecloud.blocks review candidates without writing native application data."
        )
    )
    parser.add_argument("export", type=Path, help="Path to the exact Evernote ENEX source.")
    parser.add_argument("--normalization", type=Path, required=True, help="Path to the exact Stage 3 normalization JSON artifact.")
    parser.add_argument("--resource-evidence", type=Path, help="Stage 2 resource evidence JSON; required when resources exist.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_ENEX_BYTES)
    parser.add_argument("--max-evidence-bytes", type=int, default=DEFAULT_MAX_ENEX_EVIDENCE_BYTES)
    parser.add_argument("--max-normalization-bytes", type=int, default=DEFAULT_MAX_NORMALIZATION_BYTES)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.max_bytes <= 0:
        parser.error("--max-bytes must be positive.")
    if args.max_evidence_bytes <= 0:
        parser.error("--max-evidence-bytes must be positive.")
    if args.max_normalization_bytes <= 0:
        parser.error("--max-normalization-bytes must be positive.")
    try:
        artifact = build_enex_conversion(
            args.export,
            args.normalization,
            resource_evidence_path=args.resource_evidence,
            max_bytes=args.max_bytes,
            max_evidence_bytes=args.max_evidence_bytes,
            max_normalization_bytes=args.max_normalization_bytes,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(serialize_enex_conversion(artifact))
    return 0 if artifact["conversion"]["complete"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
