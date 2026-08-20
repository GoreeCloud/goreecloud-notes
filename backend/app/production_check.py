"""Non-destructive production configuration preflight for GoreeCloud Notes."""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from .config import Settings


def _secret_file_ready(path_value: str | None) -> bool:
    if not path_value:
        return False

    path = Path(path_value).expanduser()
    try:
        if path.is_symlink() or not path.is_file():
            return False
        file_stat = path.stat()
    except OSError:
        return False

    mode = stat.S_IMODE(file_stat.st_mode)
    if mode & (stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH):
        return False
    return file_stat.st_size > 0 and os.access(path, os.R_OK)


def _attachment_root_ready(path_value: str) -> bool:
    path = Path(path_value).expanduser()
    try:
        if path.is_symlink():
            return False
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False

    return resolved.is_dir() and os.access(resolved, os.R_OK | os.W_OK | os.X_OK)


def production_runtime_report(settings: Settings) -> dict[str, Any]:
    """Return non-sensitive static readiness evidence for a production configuration.

    This check intentionally does not connect to PostgreSQL, mutate attachment storage,
    inspect application data, or claim publication/recovery approval. Live dependencies
    remain the responsibility of ``/ready`` and target-environment validation.
    """

    checks = {
        "environmentProduction": settings.is_production,
        "secureCookies": settings.secure_cookies,
        "httpsCredentialedOrigins": bool(settings.cors_origins)
        and all(urlsplit(origin).scheme == "https" for origin in settings.cors_origins),
        "trustedProxyCidrsConfigured": bool(settings.trusted_proxy_networks),
        "databaseSecretFileReady": _secret_file_ready(settings.database_password_file),
        "attachmentRootReady": _attachment_root_ready(settings.attachment_root),
        "attachmentUserQuotaConfigured": settings.attachment_user_quota_bytes
        >= settings.attachment_max_bytes
        > 0,
    }
    passed = all(checks.values())
    return {
        "format": "goreecloud-notes-production-preflight",
        "schemaVersion": 1,
        "status": "pass" if passed else "fail",
        "checks": checks,
        "nonDestructive": True,
        "liveDependencyValidationPerformed": False,
        "productionApprovalGranted": False,
    }


def _validation_messages(exc: ValidationError) -> list[str]:
    messages: list[str] = []
    for error in exc.errors(include_url=False, include_context=False, include_input=False):
        message = str(error.get("msg", "invalid configuration"))
        if message.startswith("Value error, "):
            message = message[len("Value error, ") :]
        messages.append(message)
    return messages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the non-secret GoreeCloud Notes production runtime boundary."
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        settings = Settings()
    except ValidationError as exc:
        messages = _validation_messages(exc)
        if args.json_output:
            print(
                json.dumps(
                    {
                        "format": "goreecloud-notes-production-preflight",
                        "schemaVersion": 1,
                        "status": "fail",
                        "configurationErrors": messages,
                        "nonDestructive": True,
                        "liveDependencyValidationPerformed": False,
                        "productionApprovalGranted": False,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        else:
            print("GoreeCloud Notes production preflight: FAILED", file=os.sys.stderr)
            for message in messages:
                print(f"- {message}", file=os.sys.stderr)
        return 2

    report = production_runtime_report(settings)
    if args.json_output:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        label = "passed" if report["status"] == "pass" else "FAILED"
        print(f"GoreeCloud Notes production preflight: {label}")
        for name, passed in report["checks"].items():
            print(f"- {name}: {'pass' if passed else 'fail'}")
        print("Production approval granted: no")

    return 0 if report["status"] == "pass" else 3


if __name__ == "__main__":
    raise SystemExit(main())
