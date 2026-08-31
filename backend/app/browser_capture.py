"""Bounded Browser-capture draft construction for GoreeCloud Notes.

This module intentionally stops before persistence. It converts a reviewed Browser
capture payload into the native Notes document contract while the one-time write
intent, adapter authorization, and production route remain fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, model_validator

from .documents import DOCUMENT_SCHEMA, canonicalize_document

CaptureKind = Literal["page", "link", "selection"]
MAX_CAPTURE_TEXT_CHARS = 100_000
MAX_CAPTURE_URL_CHARS = 4_096
MAX_CAPTURE_TITLE_CHARS = 512


class BrowserCaptureValidationError(ValueError):
    """Raised when a Browser capture cannot enter the Notes draft boundary."""


class BrowserCapturePayload(BaseModel):
    kind: CaptureKind
    title: str = Field(default="", max_length=MAX_CAPTURE_TITLE_CHARS)
    source_url: str | None = Field(default=None, max_length=MAX_CAPTURE_URL_CHARS)
    text: str = Field(default="", max_length=MAX_CAPTURE_TEXT_CHARS)

    @model_validator(mode="after")
    def validate_capture_shape(self) -> "BrowserCapturePayload":
        self.title = self.title.strip()
        self.text = self.text.strip()
        if self.source_url is not None:
            self.source_url = normalize_source_url(self.source_url)

        if self.kind in {"page", "link"} and self.source_url is None:
            raise ValueError("page and link captures require a source URL")
        if self.kind == "selection" and not self.text:
            raise ValueError("selection captures require selected text")
        if self.kind == "link" and not self.title:
            self.title = self.source_url or "Captured link"
        return self


@dataclass(frozen=True, slots=True)
class BrowserCaptureDraft:
    title: str
    document: dict[str, object]
    document_schema: int = DOCUMENT_SCHEMA


def normalize_source_url(value: str) -> str:
    """Accept only bounded HTTP(S) source URLs and remove fragments.

    Fragments are omitted because they can contain selected/captured text or other
    page-local content. Credentials are never accepted in source URLs.
    """

    normalized = value.strip()
    if not normalized:
        raise ValueError("source URL must not be empty")
    parts = urlsplit(normalized)
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        raise ValueError("source URL must use HTTP or HTTPS")
    if parts.username is not None or parts.password is not None:
        raise ValueError("source URL must not contain credentials")
    return urlunsplit((parts.scheme.casefold(), parts.netloc, parts.path, parts.query, ""))


def _paragraph(text: str) -> dict[str, object]:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def build_capture_draft(payload: BrowserCapturePayload) -> BrowserCaptureDraft:
    """Build a canonical native Notes draft without writing owner data."""

    blocks: list[dict[str, object]] = []
    if payload.text:
        blocks.append(_paragraph(payload.text))
    if payload.source_url:
        blocks.append(_paragraph(f"Source: {payload.source_url}"))

    document = canonicalize_document(
        {
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": blocks,
        }
    )
    title = payload.title
    if not title and payload.source_url:
        title = payload.source_url
    if not title:
        title = "Captured note"

    return BrowserCaptureDraft(
        title=title[:MAX_CAPTURE_TITLE_CHARS],
        document=document,
    )
