import pytest
from pydantic import ValidationError

from app.browser_capture import BrowserCapturePayload, build_capture_draft


def test_page_capture_builds_native_note_draft_without_fragment():
    payload = BrowserCapturePayload(
        kind="page",
        title="  Example page  ",
        source_url="https://example.com/read?q=1#selected-private-fragment",
        text="  Useful summary  ",
    )

    draft = build_capture_draft(payload)

    assert draft.title == "Example page"
    assert draft.document_schema == 1
    assert draft.document["format"] == "goreecloud.blocks"
    assert draft.document["blocks"] == [
        {"type": "paragraph", "content": [{"type": "text", "text": "Useful summary"}]},
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Source: https://example.com/read?q=1"}
            ],
        },
    ]


def test_selection_requires_text():
    with pytest.raises(ValidationError):
        BrowserCapturePayload(kind="selection", text="   ")


def test_page_and_link_require_source_url():
    with pytest.raises(ValidationError):
        BrowserCapturePayload(kind="page", title="No source")
    with pytest.raises(ValidationError):
        BrowserCapturePayload(kind="link", title="No source")


def test_rejects_non_http_and_credential_bearing_source_urls():
    with pytest.raises(ValidationError):
        BrowserCapturePayload(kind="link", source_url="file:///tmp/private.txt")
    with pytest.raises(ValidationError):
        BrowserCapturePayload(kind="link", source_url="https://user:secret@example.com/")


def test_link_uses_source_as_title_when_title_is_missing():
    payload = BrowserCapturePayload(kind="link", source_url="https://example.com/article")

    draft = build_capture_draft(payload)

    assert draft.title == "https://example.com/article"


def test_capture_text_limit_is_fail_closed():
    with pytest.raises(ValidationError):
        BrowserCapturePayload(kind="selection", text="x" * 100_001)
