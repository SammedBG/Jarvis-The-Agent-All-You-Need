"""manage.py - JARVIS admin CLI.

    python manage.py reset-password
"""
from __future__ import annotations

import sys

from argon2 import PasswordHasher

from jarvis.tasks import DB_PATH  # noqa: E402

import sqlite3


def reset_password(username: str, password: str) -> None:
    if len(password) < 12:
        print("Error: password must be at least 12 characters.")
        sys.exit(1)
    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT id FROM auth_users WHERE username=? LIMIT 1", (username,)
        ).fetchone()
        if not row:
            print(f"Error: user '{username}' not found.")
            sys.exit(1)
        conn.execute(
            "UPDATE auth_users SET password_hash=? WHERE id=?",
            (hasher.hash(password), row[0]),
        )
        conn.commit()
        print(f"Password reset for user '{username}'.")
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "reset-password":
        print("Usage: python manage.py reset-password <username>")
        print("  then enter the new password when prompted")
        return 2
    import getpass

    username = argv[2]
    password = getpass.getpass(f"New password for '{username}': ")
    confirm = getpass.getpass("Repeat password: ")
    if password != confirm:
        print("Error: passwords do not match.")
        return 1
    reset_password(username, password)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
