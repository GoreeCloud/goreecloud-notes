"""Validation and compatibility rules for the GoreeCloud Notes document contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

DOCUMENT_FORMAT = "goreecloud.blocks"
DOCUMENT_VERSION = 1
DOCUMENT_SCHEMA = 1

# Inline rendering is intentionally narrower than generic attachment download. These
# types are passive raster formats that use the existing authenticated preview route.
SAFE_INLINE_IMAGE_MEDIA_TYPES = frozenset(
    {
        "image/avif",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)

SUPPORTED_MARKS = frozenset({"bold", "italic", "strike", "code", "noteLink"})
ROOT_BLOCK_TYPES = frozenset(
    {
        "paragraph",
        "heading",
        "bulletList",
        "orderedList",
        "blockquote",
        "codeBlock",
        "horizontalRule",
        "attachmentImage",
    }
)
SUPPORTED_NODE_TYPES = ROOT_BLOCK_TYPES | frozenset({"listItem", "text", "hardBreak"})

MAX_DOCUMENT_NODES = 20_000
MAX_DOCUMENT_DEPTH = 32
MAX_DOCUMENT_TEXT_CHARS = 1_000_000
MAX_IMAGE_ALT_CHARS = 512


class DocumentValidationError(ValueError):
    """Raised when a document cannot be represented by the current native schema."""


@dataclass
class _Budget:
    nodes: int = 0
    text_chars: int = 0

    def consume_node(self, *, depth: int) -> None:
        if depth > MAX_DOCUMENT_DEPTH:
            raise DocumentValidationError("document nesting is too deep")
        self.nodes += 1
        if self.nodes > MAX_DOCUMENT_NODES:
            raise DocumentValidationError("document contains too many nodes")

    def consume_text(self, value: str) -> None:
        self.text_chars += len(value)
        if self.text_chars > MAX_DOCUMENT_TEXT_CHARS:
            raise DocumentValidationError("document text is too large")


def empty_document() -> dict[str, object]:
    return {"format": DOCUMENT_FORMAT, "version": DOCUMENT_VERSION, "blocks": []}


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise DocumentValidationError(f"{label} must be an object")
    return value


def _sequence(value: object, *, label: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise DocumentValidationError(f"{label} must be an array")
    return value


def _reject_unknown_keys(value: Mapping[str, object], allowed: set[str], *, label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise DocumentValidationError(f"{label} contains unsupported fields")


def _canonical_marks(value: object, *, budget: _Budget) -> list[dict[str, str]]:
    if value is None:
        return []

    marks = _sequence(value, label="text marks")
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str | None]] = set()
    for raw_mark in marks:
        mark = _mapping(raw_mark, label="mark")
        mark_type = mark.get("type")
        if not isinstance(mark_type, str) or mark_type not in SUPPORTED_MARKS:
            raise DocumentValidationError("document contains an unsupported text mark")

        if mark_type == "noteLink":
            _reject_unknown_keys(mark, {"type", "note_id"}, label="note link mark")
            raw_note_id = mark.get("note_id")
            if not isinstance(raw_note_id, str):
                raise DocumentValidationError("note link mark requires a note_id")
            try:
                note_id = str(UUID(raw_note_id))
            except ValueError as exc:
                raise DocumentValidationError("note link mark contains an invalid note_id") from exc
            key = (mark_type, note_id)
            if key not in seen:
                result.append({"type": mark_type, "note_id": note_id})
                seen.add(key)
            continue

        _reject_unknown_keys(mark, {"type"}, label="mark")
        key = (mark_type, None)
        if key not in seen:
            result.append({"type": mark_type})
            seen.add(key)
    return result


def _canonical_text_node(raw: Mapping[str, object], *, budget: _Budget) -> dict[str, object]:
    _reject_unknown_keys(raw, {"type", "text", "marks"}, label="text node")
    text = raw.get("text", "")
    if not isinstance(text, str):
        raise DocumentValidationError("text node text must be a string")
    budget.consume_text(text)
    node: dict[str, object] = {"type": "text", "text": text}
    marks = _canonical_marks(raw.get("marks"), budget=budget)
    if marks:
        node["marks"] = marks
    return node


def _canonical_attachment_image(raw: Mapping[str, object], *, budget: _Budget) -> dict[str, object]:
    _reject_unknown_keys(raw, {"type", "attachment_id", "alt"}, label="attachment image")
    raw_attachment_id = raw.get("attachment_id")
    if not isinstance(raw_attachment_id, str):
        raise DocumentValidationError("attachment image requires an attachment_id")
    try:
        attachment_id = str(UUID(raw_attachment_id))
    except ValueError as exc:
        raise DocumentValidationError("attachment image contains an invalid attachment_id") from exc

    alt = raw.get("alt", "")
    if not isinstance(alt, str):
        raise DocumentValidationError("attachment image alt text must be a string")
    if len(alt) > MAX_IMAGE_ALT_CHARS:
        raise DocumentValidationError("attachment image alt text is too long")
    budget.consume_text(alt)
    return {"type": "attachmentImage", "attachment_id": attachment_id, "alt": alt}


def _canonical_children(
    raw: Mapping[str, object],
    *,
    allowed_children: frozenset[str],
    depth: int,
    budget: _Budget,
    legacy_text: bool = False,
) -> list[dict[str, object]]:
    if "content" in raw:
        children = _sequence(raw["content"], label="node content")
        return [
            _canonical_node(child, allowed_types=allowed_children, depth=depth + 1, budget=budget)
            for child in children
        ]

    # Compatibility with the earliest Milestone 0 paragraph envelope.
    if legacy_text and isinstance(raw.get("text"), str) and raw["text"]:
        legacy = str(raw["text"])
        budget.consume_node(depth=depth + 1)
        budget.consume_text(legacy)
        return [{"type": "text", "text": legacy}]
    return []


def _canonical_node(
    value: object,
    *,
    allowed_types: frozenset[str],
    depth: int,
    budget: _Budget,
) -> dict[str, object]:
    raw = _mapping(value, label="document node")
    node_type = raw.get("type")
    if not isinstance(node_type, str) or node_type not in SUPPORTED_NODE_TYPES or node_type not in allowed_types:
        raise DocumentValidationError("document contains an unsupported node or node placement")

    budget.consume_node(depth=depth)

    if node_type == "text":
        return _canonical_text_node(raw, budget=budget)
    if node_type == "hardBreak":
        _reject_unknown_keys(raw, {"type"}, label="hard break")
        return {"type": "hardBreak"}
    if node_type == "horizontalRule":
        _reject_unknown_keys(raw, {"type"}, label="horizontal rule")
        return {"type": "horizontalRule"}
    if node_type == "attachmentImage":
        return _canonical_attachment_image(raw, budget=budget)

    if node_type == "paragraph":
        _reject_unknown_keys(raw, {"type", "content", "text"}, label="paragraph")
        return {
            "type": node_type,
            "content": _canonical_children(
                raw,
                allowed_children=frozenset({"text", "hardBreak"}),
                depth=depth,
                budget=budget,
                legacy_text=True,
            ),
        }

    if node_type == "heading":
        _reject_unknown_keys(raw, {"type", "level", "content"}, label="heading")
        level = raw.get("level", 1)
        if level not in {1, 2, 3}:
            raise DocumentValidationError("heading level must be 1, 2, or 3")
        return {
            "type": node_type,
            "level": int(level),
            "content": _canonical_children(
                raw,
                allowed_children=frozenset({"text", "hardBreak"}),
                depth=depth,
                budget=budget,
            ),
        }

    if node_type == "codeBlock":
        _reject_unknown_keys(raw, {"type", "content"}, label="code block")
        children = _canonical_children(
            raw,
            allowed_children=frozenset({"text"}),
            depth=depth,
            budget=budget,
        )
        for child in children:
            if child.get("marks"):
                raise DocumentValidationError("code block text cannot contain inline marks")
        return {"type": node_type, "content": children}

    if node_type in {"bulletList", "orderedList"}:
        _reject_unknown_keys(raw, {"type", "content"}, label="list")
        return {
            "type": node_type,
            "content": _canonical_children(
                raw,
                allowed_children=frozenset({"listItem"}),
                depth=depth,
                budget=budget,
            ),
        }

    if node_type == "listItem":
        _reject_unknown_keys(raw, {"type", "content"}, label="list item")
        return {
            "type": node_type,
            "content": _canonical_children(
                raw,
                allowed_children=ROOT_BLOCK_TYPES,
                depth=depth,
                budget=budget,
            ),
        }

    if node_type == "blockquote":
        _reject_unknown_keys(raw, {"type", "content"}, label="blockquote")
        return {
            "type": node_type,
            "content": _canonical_children(
                raw,
                allowed_children=ROOT_BLOCK_TYPES,
                depth=depth,
                budget=budget,
            ),
        }

    raise DocumentValidationError("document contains an unsupported node")


def canonicalize_document(value: object) -> dict[str, object]:
    """Validate and canonicalize one `goreecloud.blocks` version-1 document.

    Unknown versions, node types, placements, and fields are rejected rather than silently
    discarded. This protects notes from accidental data loss when clients and servers are on
    different document-schema generations.
    """

    root = _mapping(value, label="document")
    _reject_unknown_keys(root, {"format", "version", "blocks"}, label="document")
    if root.get("format") != DOCUMENT_FORMAT or root.get("version") != DOCUMENT_VERSION:
        raise DocumentValidationError("unsupported GoreeCloud Notes document format or version")

    blocks = _sequence(root.get("blocks"), label="document blocks")
    budget = _Budget()
    canonical_blocks = [
        _canonical_node(block, allowed_types=ROOT_BLOCK_TYPES, depth=1, budget=budget)
        for block in blocks
    ]
    return {"format": DOCUMENT_FORMAT, "version": DOCUMENT_VERSION, "blocks": canonical_blocks}


def attachment_image_ids(value: object) -> set[UUID]:
    """Collect valid inline attachment-image identifiers without trusting document shape.

    This deliberately tolerates older or partially invalid stored documents so attachment
    deletion can fail closed when a recoverable current or historical document still refers to
    the underlying bytes.
    """

    found: set[UUID] = set()

    def walk(item: object) -> None:
        if isinstance(item, Mapping):
            if item.get("type") == "attachmentImage":
                raw_id = item.get("attachment_id")
                if isinstance(raw_id, str):
                    try:
                        found.add(UUID(raw_id))
                    except ValueError:
                        pass
            for child in item.values():
                walk(child)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for child in item:
                walk(child)

    walk(value)
    return found


def note_link_ids(value: object) -> set[UUID]:
    """Collect syntactically valid internal-note references from any document-shaped value.

    Link targets are intentionally allowed to be unresolved in the document contract. The
    persistence index resolves only notes owned by the same account, so exports can preserve a
    reference even when its target is absent while cross-account note identifiers never resolve
    into visible relationship data.
    """

    found: set[UUID] = set()

    def walk(item: object) -> None:
        if isinstance(item, Mapping):
            if item.get("type") == "noteLink":
                raw_id = item.get("note_id")
                if isinstance(raw_id, str):
                    try:
                        found.add(UUID(raw_id))
                    except ValueError:
                        pass
            for child in item.values():
                walk(child)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for child in item:
                walk(child)

    walk(value)
    return found
