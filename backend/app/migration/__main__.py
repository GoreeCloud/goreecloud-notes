"""Command-line entry point for non-destructive GoreeCloud Notes migration tools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .memos import DEFAULT_MAX_EXPORT_BYTES, format_text_report, inspect_memos_export


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GoreeCloud Notes read-only migration tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser(
        "inspect-memos-export",
        help="Validate and inventory a GoreeCloud Notes schema-v1 JSON export without importing or mutating data.",
    )
    inspect.add_argument("export", type=Path, help="Path to a GoreeCloud Notes full-library JSON export.")
    inspect.add_argument("--json", action="store_true", help="Emit a machine-readable inventory report.")
    inspect.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_EXPORT_BYTES,
        help=f"Maximum JSON export size to inspect (default: {DEFAULT_MAX_EXPORT_BYTES} bytes).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.max_bytes <= 0:
        parser.error("--max-bytes must be positive.")

    try:
        report = inspect_memos_export(args.export, max_bytes=args.max_bytes)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_text_report(report))

    return 0 if report.metadata_valid else 3


if __name__ == "__main__":
    raise SystemExit(main())
