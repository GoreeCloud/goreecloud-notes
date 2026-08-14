"""Administrative command-line tools for GoreeCloud Notes."""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from .auth import hash_password, normalize_username
from .database import SessionLocal
from .models import User, UserCredential

_MIN_PASSWORD_LENGTH = 12


def _read_password(password_stdin: bool) -> str:
    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise ValueError("Passwords do not match.")

    if len(password) < _MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must contain at least {_MIN_PASSWORD_LENGTH} characters.")
    return password


def create_user(*, username: str, display_name: str, password_stdin: bool) -> None:
    normalized = normalize_username(username)
    clean_username = username.strip()
    clean_display_name = display_name.strip()
    if not normalized or not clean_username:
        raise ValueError("Username must not be empty.")
    if len(clean_username) > 64 or len(normalized) > 64:
        raise ValueError("Username must not exceed 64 characters.")
    if not clean_display_name or len(clean_display_name) > 120:
        raise ValueError("Display name must contain 1 to 120 characters.")

    password = _read_password(password_stdin)
    password_hash = hash_password(password)

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.username_normalized == normalized))
        if existing is not None:
            raise ValueError("An account with that normalized username already exists.")

        user = User(
            username=clean_username,
            username_normalized=normalized,
            display_name=clean_display_name,
        )
        db.add(user)
        db.flush()
        db.add(UserCredential(user_id=user.id, password_hash=password_hash))
        db.commit()

    print(f"Created GoreeCloud Notes account: {clean_username}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GoreeCloud Notes administrative commands")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser(
        "create-user",
        help="Create a private GoreeCloud Notes account; no public registration endpoint exists.",
    )
    create.add_argument("--username", required=True)
    create.add_argument("--display-name", required=True)
    create.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read one password line from standard input instead of prompting interactively.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "create-user":
            create_user(
                username=args.username,
                display_name=args.display_name,
                password_stdin=args.password_stdin,
            )
        else:
            parser.error("Unsupported command.")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
