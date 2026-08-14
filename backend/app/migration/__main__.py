"""Command-line entry point for non-destructive GoreeCloud Notes migration tools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evidence import DEFAULT_MAX_MANIFEST_BYTES, serialize_evidence, verify_attachment_binaries
from .manifest import build_memos_manifest, serialize_manifest
from .memos import DEFAULT_MAX_EXPORT_BYTES, format_text_report, inspect_memos_export


def _add_export_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("export", type=Path, help="Path to a GoreeCloud Notes full-library JSON export.")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_EXPORT_BYTES,
        help=f"Maximum JSON export size to inspect (default: {DEFAULT_MAX_EXPORT_BYTES} bytes).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GoreeCloud Notes read-only migration tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser(
        "inspect-memos-export",
        help="Validate and inventory a GoreeCloud Notes schema-v1 JSON export without importing or mutating data.",
    )
    _add_export_arguments(inspect)
    inspect.add_argument("--json", action="store_true", help="Emit a machine-readable inventory report.")

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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in {"inspect-memos-export", "build-memos-manifest"} and args.max_bytes <= 0:
        parser.error("--max-bytes must be positive.")
    if args.command == "verify-attachment-binaries" and args.max_manifest_bytes <= 0:
        parser.error("--max-manifest-bytes must be positive.")

    try:
        if args.command == "inspect-memos-export":
            report = inspect_memos_export(args.export, max_bytes=args.max_bytes)
            if args.json:
                print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
            else:
                print(format_text_report(report))
            return 0 if report.metadata_valid else 3

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
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
