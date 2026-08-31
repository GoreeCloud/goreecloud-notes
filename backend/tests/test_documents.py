from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.documents import (
    DocumentValidationError,
    attachment_image_ids,
    canonicalize_document,
    empty_document,
    note_link_ids,
)


def test_empty_document_is_valid() -> None:
    assert canonicalize_document(empty_document()) == empty_document()


def test_legacy_paragraph_text_is_canonicalized() -> None:
    document = {
        "format": "goreecloud.blocks",
        "version": 1,
        "blocks": [{"type": "paragraph", "text": "legacy text"}],
    }

    assert canonicalize_document(document) == {
        "format": "goreecloud.blocks",
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "legacy text"}],
            }
        ],
    }


def test_rich_document_attachment_and_note_link_are_canonicalized() -> None:
    attachment_id = uuid4()
    linked_note_id = uuid4()
    document = {
        "format": "goreecloud.blocks",
        "version": 1,
        "blocks": [
            {
                "type": "heading",
                "level": 2,
                "content": [
                    {
                        "type": "text",
                        "text": "Title",
                        "marks": [
                            {"type": "bold"},
                            {"type": "noteLink", "note_id": str(linked_note_id).upper()},
                        ],
                    }
                ],
            },
            {
                "type": "attachmentImage",
                "attachment_id": str(attachment_id).upper(),
                "alt": "Architecture diagram",
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Portable"}],
                            }
                        ],
                    }
                ],
            },
        ],
    }

    clean = canonicalize_document(document)
    assert clean["blocks"][0]["content"][0]["marks"] == [
        {"type": "bold"},
        {"type": "noteLink", "note_id": str(linked_note_id)},
    ]
    assert clean["blocks"][1] == {
        "type": "attachmentImage",
        "attachment_id": str(attachment_id),
        "alt": "Architecture diagram",
    }
    assert attachment_image_ids(clean) == {attachment_id}
    assert note_link_ids(clean) == {linked_note_id}


@pytest.mark.parametrize(
    "document",
    [
        {"format": "prosemirror", "version": 1, "blocks": []},
        {"format": "goreecloud.blocks", "version": 2, "blocks": []},
        {
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": [{"type": "script", "content": []}],
        },
        {
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": [{"type": "paragraph", "content": [{"type": "attachmentImage", "attachment_id": str(uuid4()), "alt": "bad placement"}]}],
        },
        {
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": [{"type": "text", "text": "top-level inline"}],
        },
        {
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": [{"type": "attachmentImage", "attachment_id": "not-a-uuid", "alt": "bad"}],
        },
        {
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": [{"type": "paragraph", "content": [], "unknown": True}],
        },
        {
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "x", "marks": [{"type": "link"}]}
                    ],
                }
            ],
        },
        {
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "x", "marks": [{"type": "noteLink", "note_id": "not-a-uuid"}]}
                    ],
                }
            ],
        },
        {
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "x", "marks": [{"type": "noteLink", "note_id": str(uuid4()), "href": "https://example.invalid"}]}
                    ],
                }
            ],
        },
    ],
)
def test_invalid_documents_are_rejected(document: dict[str, object]) -> None:
    with pytest.raises(DocumentValidationError):
        canonicalize_document(document)


def test_attachment_id_collector_is_fail_closed_and_tolerant() -> None:
    first = uuid4()
    second = uuid4()
    document = {
        "format": "future-or-partially-invalid",
        "blocks": [
            {"type": "attachmentImage", "attachment_id": str(first)},
            {
                "type": "unknown",
                "content": [
                    {"type": "attachmentImage", "attachment_id": str(second)},
                    {"type": "attachmentImage", "attachment_id": "not-a-uuid"},
                ],
            },
        ],
    }

    found = attachment_image_ids(document)
    assert found == {UUID(str(first)), UUID(str(second))}


def test_note_link_id_collector_tolerates_unresolved_and_invalid_surroundings() -> None:
    first = uuid4()
    second = uuid4()
    document = {
        "format": "future-or-partially-invalid",
        "blocks": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "one", "marks": [{"type": "noteLink", "note_id": str(first)}]},
                    {"type": "text", "text": "bad", "marks": [{"type": "noteLink", "note_id": "invalid"}]},
                ],
            },
            {
                "type": "unknown",
                "content": [
                    {"type": "text", "text": "two", "marks": [{"type": "noteLink", "note_id": str(second)}]},
                ],
            },
        ],
    }

    assert note_link_ids(document) == {UUID(str(first)), UUID(str(second))}
