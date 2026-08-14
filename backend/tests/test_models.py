"""Structural tests for the first native GoreeCloud Notes persistence model."""

from sqlalchemy import CheckConstraint, UniqueConstraint

from app import models  # noqa: F401
from app.database import Base


def test_native_core_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "attachments",
        "auth_sessions",
        "note_revisions",
        "note_tags",
        "notebooks",
        "notes",
        "tags",
        "user_credentials",
        "users",
    }


def test_user_owned_entities_keep_explicit_owner_scope() -> None:
    for table_name in (
        "attachments",
        "note_revisions",
        "note_tags",
        "notebooks",
        "notes",
        "tags",
    ):
        owner = Base.metadata.tables[table_name].c.owner_id
        assert owner.nullable is False


def test_authentication_tables_do_not_store_raw_browser_secrets() -> None:
    sessions = Base.metadata.tables["auth_sessions"]
    credentials = Base.metadata.tables["user_credentials"]

    assert {"token_hash", "csrf_token_hash", "expires_at", "user_id"}.issubset(sessions.c.keys())
    assert "token" not in sessions.c
    assert "csrf_token" not in sessions.c
    assert "password_hash" in credentials.c
    assert "password" not in credentials.c


def test_note_state_is_native_not_hidden_content_metadata() -> None:
    notes = Base.metadata.tables["notes"]
    state_constraints = {
        str(constraint.sqltext)
        for constraint in notes.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "state IN ('normal', 'archived', 'trashed')" in state_constraints
    assert notes.c.state.server_default is not None
    assert "state" not in notes.c.document.name


def test_attachment_table_stores_metadata_not_binary_payloads() -> None:
    attachments = Base.metadata.tables["attachments"]

    assert {
        "filename",
        "media_type",
        "size_bytes",
        "sha256",
        "storage_key",
        "extra_metadata",
    }.issubset(attachments.c.keys())
    assert "content" not in attachments.c
    assert "blob" not in attachments.c
    assert "bytes" not in attachments.c


def test_tags_are_unique_within_owner_normalization_scope() -> None:
    tags = Base.metadata.tables["tags"]
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in tags.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("owner_id", "normalized_name") in unique_columns


def test_revisions_are_immutable_content_snapshots() -> None:
    revisions = Base.metadata.tables["note_revisions"]

    assert "created_at" in revisions.c
    assert "updated_at" not in revisions.c
    assert {"revision_number", "title", "document", "document_schema"}.issubset(revisions.c.keys())
