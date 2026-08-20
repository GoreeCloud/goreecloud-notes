from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from app.migration.enex_conversion import (
    CONVERSION_FORMAT,
    build_enex_conversion,
    main as conversion_main,
    serialize_enex_conversion,
)
from app.migration.enex_normalization import build_enex_normalization, serialize_enex_normalization
from app.migration.enex_resources import EVIDENCE_FILENAME, extract_enex_resources

FIXTURE = Path(__file__).parent / "fixtures" / "evernote_export.enex"


def _inputs(tmp_path: Path, source: Path = FIXTURE) -> tuple[Path, Path | None]:
    evidence_path: Path | None = None
    if "<resource>" in source.read_text(encoding="utf-8"):
        evidence_root = tmp_path / "resource-evidence"
        extract_enex_resources(source, evidence_root)
        evidence_path = evidence_root / EVIDENCE_FILENAME
    normalization = build_enex_normalization(source, resource_evidence_path=evidence_path)
    normalization_path = tmp_path / "normalization.json"
    normalization_path.write_text(serialize_enex_normalization(normalization), encoding="utf-8")
    return normalization_path, evidence_path


def _write_enex(tmp_path: Path, enml: str, *, resource: tuple[bytes, str, str] | None = None) -> Path:
    resource_xml = ""
    if resource is not None:
        import base64

        raw, mime, file_name = resource
        md5 = hashlib.md5(raw, usedforsecurity=False).hexdigest()
        encoded = base64.b64encode(raw).decode("ascii")
        resource_xml = (
            f'<resource><data encoding="base64" hash="{md5}">{encoded}</data>'
            f'<mime>{mime}</mime><resource-attributes><file-name>{file_name}</file-name>'
            f'</resource-attributes></resource>'
        )
    source = tmp_path / "source.enex"
    source.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<en-export export-date="20260815T050000Z" application="Evernote/10.0" version="10.0">\n'
        '<note><title>Conversion</title><content><![CDATA['
        + enml
        + ']]></content><created>20260814T120000Z</created><updated>20260815T040000Z</updated>'
        + resource_xml
        + '</note></en-export>\n',
        encoding="utf-8",
    )
    return source


def test_enex_conversion_is_deterministic_and_produces_valid_native_candidates(tmp_path: Path) -> None:
    normalization_path, evidence_path = _inputs(tmp_path)

    first = build_enex_conversion(FIXTURE, normalization_path, resource_evidence_path=evidence_path)
    second = build_enex_conversion(FIXTURE, normalization_path, resource_evidence_path=evidence_path)

    assert first == second
    assert first["format"] == CONVERSION_FORMAT
    assert first["schemaVersion"] == 1
    assert first["conversion"] == {
        "documentFormat": "goreecloud.blocks",
        "documentVersion": 1,
        "noteCount": 2,
        "convertedNotes": 2,
        "blockedNotes": 0,
        "reviewRequiredNotes": 1,
        "complete": True,
        "reviewRequired": True,
        "enmlConversionPerformed": True,
        "nativeNotesCreated": False,
        "nativeAttachmentsCreated": False,
        "sourceMutationPerformed": False,
        "targetDatabaseMutationPerformed": False,
    }
    note = first["notes"][0]
    assert note["document"] == {
        "format": "goreecloud.blocks",
        "version": 1,
        "blocks": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "World"}]},
        ],
    }
    assert note["attachments"][0]["fileName"] == "hello.txt"
    assert note["attachments"][0]["enmlReferenceCount"] == 0
    assert note["conversionStatus"] == "converted-review-required"
    assert {item["code"] for item in note["reviewNotices"]} == {"unreferenced-enex-resource"}
    assert note["nativePersistencePerformed"] is False
    assert serialize_enex_conversion(first) == serialize_enex_conversion(second)


def test_enex_conversion_maps_supported_rich_structure(tmp_path: Path) -> None:
    source = _write_enex(
        tmp_path,
        '<en-note><h2>Heading</h2><div><strong>Bold</strong><br/><em>Italic</em></div>'
        '<ul><li>One</li><li><code>Two</code></li></ul><blockquote>Quote</blockquote>'
        '<pre>code\nblock</pre><hr/></en-note>',
    )
    normalization_path, evidence_path = _inputs(tmp_path, source)
    artifact = build_enex_conversion(source, normalization_path, resource_evidence_path=evidence_path)

    assert artifact["conversion"]["complete"] is True
    assert artifact["conversion"]["reviewRequired"] is False
    blocks = artifact["notes"][0]["document"]["blocks"]
    assert blocks[0]["type"] == "heading" and blocks[0]["level"] == 2
    assert blocks[1]["content"][0]["marks"] == [{"type": "bold"}]
    assert blocks[1]["content"][1] == {"type": "hardBreak"}
    assert blocks[1]["content"][2]["marks"] == [{"type": "italic"}]
    assert blocks[2]["type"] == "bulletList"
    assert blocks[3]["type"] == "blockquote"
    assert blocks[4]["type"] == "codeBlock"
    assert blocks[5] == {"type": "horizontalRule"}


def test_en_media_image_uses_deterministic_future_attachment_id(tmp_path: Path) -> None:
    raw = b"\x89PNG\r\n\x1a\n"
    md5 = hashlib.md5(raw, usedforsecurity=False).hexdigest()
    source = _write_enex(
        tmp_path,
        f'<en-note>Before<en-media type="image/png" hash="{md5}" alt="Preview"/>After</en-note>',
        resource=(raw, "image/png", "preview.png"),
    )
    normalization_path, evidence_path = _inputs(tmp_path, source)
    artifact = build_enex_conversion(source, normalization_path, resource_evidence_path=evidence_path)
    note = artifact["notes"][0]
    blocks = note["document"]["blocks"]

    assert [block["type"] for block in blocks] == ["paragraph", "attachmentImage", "paragraph"]
    assert blocks[1]["attachment_id"] == note["attachments"][0]["attachmentId"]
    assert blocks[1]["alt"] == "Preview"
    assert note["attachments"][0]["enmlReferenceCount"] == 1
    assert artifact["conversion"]["reviewRequired"] is False


def test_non_image_media_links_and_style_are_explicit_review_notices(tmp_path: Path) -> None:
    raw = b"hello"
    md5 = hashlib.md5(raw, usedforsecurity=False).hexdigest()
    source = _write_enex(
        tmp_path,
        f'<en-note><div style="text-align:center"><a href="https://example.com">Example</a>'
        f'<en-media type="text/plain" hash="{md5}"/></div></en-note>',
        resource=(raw, "text/plain", "hello.txt"),
    )
    normalization_path, evidence_path = _inputs(tmp_path, source)
    artifact = build_enex_conversion(source, normalization_path, resource_evidence_path=evidence_path)
    note = artifact["notes"][0]

    assert artifact["conversion"]["complete"] is True
    assert artifact["conversion"]["reviewRequired"] is True
    assert note["conversionStatus"] == "converted-review-required"
    codes = {item["code"] for item in note["reviewNotices"]}
    assert {"enml-layout-style-not-represented", "enml-link-target-not-represented", "non-image-en-media-placeholder"} <= codes
    assert note["linksPreservedForReview"] == [
        {"href": "https://example.com", "path": "note[0]/en-note/div[0]/a[0]"}
    ]


def test_table_blocks_candidate_document_instead_of_silently_flattening(tmp_path: Path) -> None:
    source = _write_enex(tmp_path, "<en-note><table><tr><td>Cell</td></tr></table></en-note>")
    normalization_path, evidence_path = _inputs(tmp_path, source)
    artifact = build_enex_conversion(source, normalization_path, resource_evidence_path=evidence_path)

    assert artifact["conversion"]["complete"] is False
    assert artifact["conversion"]["blockedNotes"] == 1
    note = artifact["notes"][0]
    assert note["document"] is None
    assert note["conversionStatus"] == "blocked"
    assert note["blockingIssues"][0]["code"] == "enml-table-not-supported"


def test_tampered_normalization_is_refused_before_conversion(tmp_path: Path) -> None:
    normalization_path, evidence_path = _inputs(tmp_path)
    payload = json.loads(normalization_path.read_text(encoding="utf-8"))
    payload["notes"][0]["content"]["title"] = "Tampered"
    normalization_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="record fingerprint is invalid"):
        build_enex_conversion(FIXTURE, normalization_path, resource_evidence_path=evidence_path)


def test_normalization_from_another_source_is_refused(tmp_path: Path) -> None:
    normalization_path, evidence_path = _inputs(tmp_path)
    changed = tmp_path / "changed.enex"
    changed.write_text(
        FIXTURE.read_text(encoding="utf-8").replace("Migration Fixture", "Changed Fixture", 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match the exact source ENEX fingerprint"):
        build_enex_conversion(changed, normalization_path, resource_evidence_path=evidence_path)


def test_conversion_cli_emits_machine_readable_zero_write_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    normalization_path, evidence_path = _inputs(tmp_path)
    assert evidence_path is not None
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m app.migration.enex_conversion",
            str(FIXTURE),
            "--normalization",
            str(normalization_path),
            "--resource-evidence",
            str(evidence_path),
        ],
    )

    assert conversion_main() == 0
    stdout = capsys.readouterr().out
    artifact = json.loads(stdout)
    assert artifact["format"] == CONVERSION_FORMAT
    assert artifact["conversion"]["targetDatabaseMutationPerformed"] is False
    assert artifact["conversion"]["nativeNotesCreated"] is False
    assert stdout == serialize_enex_conversion(artifact)
