"""
backup.py - encrypted backup and restore for JARVIS personal data.

Encrypts your private data (jarvis.db + notes/) into one password-protected
file using AES (Fernet) with a key derived via PBKDF2-SHA256 (600k rounds).
Put the resulting .bin on a USB drive or upload it somewhere safe.

Usage:
    python backup.py --password "your secret"                 # create backup
    python backup.py --restore backup-XXXXXX.bin --password "your secret"
    # or set JARVIS_BACKUP_PASSWORD in .env and omit --password

Keeps the 10 most recent backups in backups/ ; older ones are pruned.
Run with JARVIS stopped (or stop it after) so the DB isn't open.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import os
import sys
import tarfile
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = Path(os.environ.get("JARVIS_DB", BASE_DIR / "jarvis.db"))
NOTES_DIR = BASE_DIR / "notes"
BACKUP_DIR = BASE_DIR / "backups"
SALT = b"jarvis-backup-salt-2026"
ITERATIONS = 600_000


def _key(password: str) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                      salt=SALT, iterations=ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def _archive(out_tar: Path) -> None:
    with tarfile.open(out_tar, "w:gz") as tf:
        if DB_FILE.exists():
            tf.add(DB_FILE, arcname="jarvis.db")
        if NOTES_DIR.exists():
            for p in NOTES_DIR.glob("*.txt"):
                tf.add(p, arcname=f"notes/{p.name}")


def _prune(keep: int = 10) -> None:
    BACKUP_DIR.mkdir(exist_ok=True)
    files = sorted(BACKUP_DIR.glob("backup-*.bin"), reverse=True)
    for f in files[keep:]:
        try:
            f.unlink()
        except OSError:
            pass


def make_backup(password: str, output_dir: Path) -> Path:
    output_dir.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    tar = output_dir / f"backup-{stamp}.tar.gz"
    out = output_dir / f"backup-{stamp}.bin"
    _archive(tar)
    cipher = Fernet(_key(password)).encrypt(tar.read_bytes())
    out.write_bytes(cipher)
    tar.unlink(missing_ok=True)
    _prune()
    return out


def restore(archive: Path, password: str, into: Path) -> None:
    raw = archive.read_bytes()
    data = Fernet(_key(password)).decrypt(raw)  # raises on wrong password
    into = Path(into).resolve()
    # never restore into a system/root-level dir
    if not str(into).startswith(str(Path.home())):
        raise ValueError(f"Restore target {into} is not under your home directory.")
    into.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tf:
        tf.write(data)
        tmp = Path(tf.name)
    try:
        with tarfile.open(tmp, "r:gz") as tf:
            # Python 3.12+: 'data' filter strips unsafe members; fall back gracefully
            try:
                tf.extractall(into, filter="data")
            except TypeError:
                tf.extractall(into)
    finally:
        tmp.unlink(missing_ok=True)


def load_password(args) -> str:
    p = args.password or os.getenv("JARVIS_BACKUP_PASSWORD")
    if not p:
        print("Error: password required (--password or JARVIS_BACKUP_PASSWORD in .env)")
        sys.exit(1)
    return p


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Backup / restore JARVIS data (AES-128-CBC + PBKDF2-SHA256).")
    ap.add_argument("--password", help="encryption password")
    ap.add_argument("--output", type=Path, default=BACKUP_DIR, help="output folder for backup")
    ap.add_argument("--restore", metavar="FILE", help="restore from a .bin file")
    ap.add_argument("--into", type=Path, default=BASE_DIR, help="restore target folder")
    args = ap.parse_args()
    p = load_password(args)

    if args.restore:
        print(f"Restoring {args.restore} -> {args.into}")
        restore(Path(args.restore), p, args.into)
        print("Restored OK. Restart JARVIS before continuing.")
        print("(Note: this overwrites jarvis.db; take another backup first if unsure.)")
    else:
        out = make_backup(p, args.output)
        print(f"Backup written: {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()