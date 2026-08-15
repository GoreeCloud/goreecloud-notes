"""Structural tests for the native GoreeCloud Notes persistence model."""

from sqlalchemy import CheckConstraint, UniqueConstraint

from app import admin_audit, login_security, models  # noqa: F401
from app.database import Base
from app.migration import persistence  # noqa: F401


def test_native_core_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "admin_audit_events",
        "attachments",
        "auth_sessions",
        "login_rate_buckets",
        "migration_imports",
        "migration_note_records",
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
        "migration_imports",
        "migration_note_records",
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


def test_admin_audit_keeps_minimal_immutable_identity_snapshots() -> None:
    audit_events = Base.metadata.tables["admin_audit_events"]

    assert {
        "id",
        "target_user_id",
        "target_username",
        "action",
        "operator_identifier",
        "reason",
        "details",
        "created_at",
    } == set(audit_events.c.keys())
    assert audit_events.c.target_user_id.nullable is False
    assert not audit_events.c.target_user_id.foreign_keys
    assert "updated_at" not in audit_events.c

    for prohibited in (
        "password",
        "password_hash",
        "session_token",
        "csrf_token",
        "ip_address",
        "note_content",
        "attachment_path",
    ):
        assert prohibited not in audit_events.c


def test_login_rate_state_keeps_only_opaque_bucket_signals() -> None:
    buckets = Base.metadata.tables["login_rate_buckets"]

    assert {
        "bucket_key",
        "scope",
        "failure_count",
        "window_started_at",
        "blocked_until",
        "last_failed_at",
        "expires_at",
    } == set(buckets.c.keys())
    for clear_identifier in ("username", "source", "ip", "ip_address", "account"):
        assert clear_identifier not in buckets.c


def test_migration_provenance_keeps_source_fingerprints_and_exact_record() -> None:
    imports = Base.metadata.tables["migration_imports"]
    records = Base.metadata.tables["migration_note_records"]

    assert {
        "provider",
        "source_export_sha256",
        "manifest_sha256",
        "evidence_sha256",
        "source_exported_at",
        "source_note_count",
        "imported_note_count",
        "conversion_profile",
    }.issubset(imports.c.keys())
    assert {
        "import_id",
        "note_id",
        "source_name",
        "source_uid",
        "source_order",
        "record_sha256",
        "source_record",
    }.issubset(records.c.keys())

    import_unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in imports.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    record_unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in records.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("owner_id", "provider", "source_export_sha256") in import_unique_columns
    assert ("import_id", "source_name") in record_unique_columns
    assert ("import_id", "note_id") in record_unique_columns


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


def test_notes_and_revisions_track_positive_content_versions() -> None:
    notes = Base.metadata.tables["notes"]
    revisions = Base.metadata.tables["note_revisions"]

    assert notes.c.content_version.nullable is False
    assert notes.c.content_version.server_default is not None
    assert revisions.c.content_version.nullable is False

    note_checks = {
        str(constraint.sqltext)
        for constraint in notes.constraints
        if isinstance(constraint, CheckConstraint)
    }
    revision_checks = {
        str(constraint.sqltext)
        for constraint in revisions.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "content_version > 0" in note_checks
    assert "content_version > 0" in revision_checks

    revision_unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in revisions.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("note_id", "content_version") in revision_unique_columns


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
    assert {
        "revision_number",
        "content_version",
        "title",
        "document",
        "document_schema",
    }.issubset(revisions.c.keys())
