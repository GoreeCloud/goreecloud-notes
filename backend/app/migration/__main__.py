"""Command-line entry point for controlled GoreeCloud Notes migration tools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from ..auth import normalize_username
from ..config import get_settings
from ..database import SessionLocal
from ..models import User
from .enex import DEFAULT_MAX_ENEX_BYTES, format_text_report as format_enex_text_report, inspect_enex_export
from .enex_resources import (
    DEFAULT_MAX_ENEX_EXTRACTED_BYTES,
    DEFAULT_MAX_ENEX_RESOURCE_BYTES,
    DEFAULT_MAX_ENEX_RESOURCE_COUNT,
    extract_enex_resources,
    serialize_enex_resource_evidence,
)
from .evidence import DEFAULT_MAX_MANIFEST_BYTES, serialize_evidence, verify_attachment_binaries
from .importer import (
    DEFAULT_MAX_INPUT_BYTES,
    MigrationImportError,
    serialize_import_result,
    verify_imported_memos_data,
)
from .manifest import build_memos_manifest, serialize_manifest
from .memos import DEFAULT_MAX_EXPORT_BYTES, format_text_report, inspect_memos_export
from .target_import import import_memos_manifest


def _add_export_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("export", type=Path, help="Path to a GoreeCloud Notes full-library JSON export.")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_EXPORT_BYTES,
        help=f"Maximum JSON export size to inspect (default: {DEFAULT_MAX_EXPORT_BYTES} bytes).",
    )


def _add_enex_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("export", type=Path, help="Path to an Evernote ENEX export.")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_ENEX_BYTES,
        help=f"Maximum ENEX size to inspect (default: {DEFAULT_MAX_ENEX_BYTES} bytes).",
    )


def _target_user(username: str) -> User:
    normalized = normalize_username(username)
    if not normalized:
        raise MigrationImportError("Target username must not be empty.")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username_normalized == normalized))
        if user is None:
            raise MigrationImportError("Target GoreeCloud Notes account was not found.")
        # Return a detached identity object containing scalar values only.
        db.expunge(user)
        return user


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "GoreeCloud Notes migration tools. Inspection, manifest, evidence, and verification commands are read-only. "
            "ENEX resource extraction writes only to a newly created local evidence directory and never to native "
            "application data. The import command writes only to an explicitly confirmed empty native account and "
            "never connects to Memos."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser(
        "inspect-memos-export",
        help="Validate and inventory a GoreeCloud Notes schema-v1 JSON export without importing or mutating data.",
    )
    _add_export_arguments(inspect)
    inspect.add_argument("--json", action="store_true", help="Emit a machine-readable inventory report.")

    inspect_enex = subparsers.add_parser(
        "inspect-enex-export",
        help="Validate and inventory an Evernote ENEX export without extracting resources or importing data.",
    )
    _add_enex_arguments(inspect_enex)
    inspect_enex.add_argument("--json", action="store_true", help="Emit a machine-readable ENEX inventory report.")

    extract_enex = subparsers.add_parser(
        "extract-enex-resources",
        help=(
            "Extract validated embedded ENEX resources into a new local evidence directory with SHA-256 verification. "
            "This command never writes native Notes data."
        ),
    )
    _add_enex_arguments(extract_enex)
    extract_enex.add_argument(
        "output",
        type=Path,
        help="New extraction directory to create. The path must not already exist.",
    )
    extract_enex.add_argument(
        "--max-resource-bytes",
        type=int,
        default=DEFAULT_MAX_ENEX_RESOURCE_BYTES,
        help=(
            "Maximum decoded size of any one ENEX resource "
            f"(default: {DEFAULT_MAX_ENEX_RESOURCE_BYTES} bytes)."
        ),
    )
    extract_enex.add_argument(
        "--max-total-resource-bytes",
        type=int,
        default=DEFAULT_MAX_ENEX_EXTRACTED_BYTES,
        help=(
            "Maximum decoded size of all ENEX resources "
            f"(default: {DEFAULT_MAX_ENEX_EXTRACTED_BYTES} bytes)."
        ),
    )
    extract_enex.add_argument(
        "--max-resources",
        type=int,
        default=DEFAULT_MAX_ENEX_RESOURCE_COUNT,
        help=f"Maximum number of ENEX resources to extract (default: {DEFAULT_MAX_ENEX_RESOURCE_COUNT}).",
    )

    manifest = subparsers.add_parser(
        "build-memos-manifest",
        help="Emit a deterministic provider-neutral migration manifest from a validated schema-v1 export.",
    )
    _add_export_arguments(manifest)

    evidence = subparsers.add_parser(
        "verify-attachment-binaries",
        help="Hash and verify operator-supplied local attachment bytes against a migration manifest without importing them.",
    )
    evidence.add_argument("manifest", type=Path, help="Path to a goreecloud-notes-migration schema-v1 manifest.")
    evidence.add_argument("attachment_map", type=Path, help="Path to a goreecloud-notes-attachment-map schema-v1 JSON mapping.")
    evidence.add_argument("evidence_root", type=Path, help="Directory containing the operator-supplied extracted attachment files.")
    evidence.add_argument(
        "--max-manifest-bytes",
        type=int,
        default=DEFAULT_MAX_MANIFEST_BYTES,
        help=f"Maximum manifest/map JSON size (default: {DEFAULT_MAX_MANIFEST_BYTES} bytes).",
    )

    importer = subparsers.add_parser(
        "import-memos-manifest",
        help=(
            "Persist one validated manifest/evidence set into an explicitly confirmed empty native account. "
            "This command writes target data but never connects to or mutates Memos."
        ),
    )
    importer.add_argument("manifest", type=Path)
    importer.add_argument("evidence", type=Path)
    importer.add_argument("evidence_root", type=Path)
    importer.add_argument("--username", required=True, help="Existing empty native target account.")
    importer.add_argument(
        "--confirm-empty-target",
        action="store_true",
        help="Required explicit acknowledgement that this command may write to the selected empty target account.",
    )
    importer.add_argument(
        "--max-input-bytes",
        type=int,
        default=DEFAULT_MAX_INPUT_BYTES,
        help=f"Maximum size of each manifest/evidence JSON input (default: {DEFAULT_MAX_INPUT_BYTES} bytes).",
    )

    verify_import = subparsers.add_parser(
        "verify-memos-import",
        help="Read-only verification of persisted native notes, provenance, tag assignments, and attachment-byte integrity.",
    )
    verify_import.add_argument("--username", required=True)
    verify_import.add_argument("--import-id", required=True, type=UUID)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in {
        "inspect-memos-export",
        "build-memos-manifest",
        "inspect-enex-export",
        "extract-enex-resources",
    } and args.max_bytes <= 0:
        parser.error("--max-bytes must be positive.")
    if args.command == "extract-enex-resources":
        if args.max_resource_bytes <= 0:
            parser.error("--max-resource-bytes must be positive.")
        if args.max_total_resource_bytes <= 0:
            parser.error("--max-total-resource-bytes must be positive.")
        if args.max_resources <= 0:
            parser.error("--max-resources must be positive.")
    if args.command == "verify-attachment-binaries" and args.max_manifest_bytes <= 0:
        parser.error("--max-manifest-bytes must be positive.")
    if args.command == "import-memos-manifest" and args.max_input_bytes <= 0:
        parser.error("--max-input-bytes must be positive.")
    if args.command == "import-memos-manifest" and not args.confirm_empty_target:
        parser.error("--confirm-empty-target is required for the target-writing import command.")

    try:
        if args.command == "inspect-memos-export":
            report = inspect_memos_export(args.export, max_bytes=args.max_bytes)
            if args.json:
                print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
            else:
                print(format_text_report(report))
            return 0 if report.metadata_valid else 3

        if args.command == "inspect-enex-export":
            report = inspect_enex_export(args.export, max_bytes=args.max_bytes)
            if args.json:
                print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
            else:
                print(format_enex_text_report(report), end="")
            return 0 if report.metadata_valid else 3

        if args.command == "extract-enex-resources":
            evidence = extract_enex_resources(
                args.export,
                args.output,
                max_bytes=args.max_bytes,
                max_resource_bytes=args.max_resource_bytes,
                max_total_bytes=args.max_total_resource_bytes,
                max_resources=args.max_resources,
            )
            sys.stdout.write(serialize_enex_resource_evidence(evidence))
            return 0

        if args.command == "build-memos-manifest":
            manifest = build_memos_manifest(args.export, max_bytes=args.max_bytes)
            sys.stdout.write(serialize_manifest(manifest))
            return 0

        if args.command == "verify-attachment-binaries":
            evidence = verify_attachment_binaries(
                args.manifest,
                args.attachment_map,
                args.evidence_root,
                max_manifest_bytes=args.max_manifest_bytes,
            )
            sys.stdout.write(serialize_evidence(evidence))
            return 0 if evidence["verification"]["complete"] else 4

        if args.command == "import-memos-manifest":
            owner = _target_user(args.username)
            settings = get_settings()
            with SessionLocal() as db:
                result = import_memos_manifest(
                    db,
                    owner=owner,
                    manifest_path=args.manifest,
                    evidence_path=args.evidence,
                    evidence_root=args.evidence_root,
                    attachment_root=Path(settings.attachment_root),
                    attachment_max_bytes=settings.attachment_max_bytes,
                    max_input_bytes=args.max_input_bytes,
                )
            sys.stdout.write(serialize_import_result(result))
            return 0

        if args.command == "verify-memos-import":
            owner = _target_user(args.username)
            settings = get_settings()
            with SessionLocal() as db:
                result = verify_imported_memos_data(
                    db,
                    owner=owner,
                    import_id=args.import_id,
                    attachment_root=Path(settings.attachment_root),
                )
            sys.stdout.write(serialize_import_result(result))
            return 0
    except (OSError, ValueError, MigrationImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
