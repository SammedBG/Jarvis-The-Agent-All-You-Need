"""Authentication for the JARVIS API.

Endpoints:
    POST /api/auth/setup        - first-run: create owner (min 12 chars, only when no owner)
    POST /api/auth/login        - credentials -> session cookie
    POST /api/auth/logout       - clear session
    GET  /api/me                - current user + CSRF token

Security:
    * Argon2id password hash stored in DB
    * random session token stored hashed (sha256), HttpOnly + SameSite=Strict cookie
    * idle timeout 30 min, absolute 12 hours
    * login rate limiting: 5 failures -> 5 min lockout, doubling
    * generic error messages (no user enumeration)
    * CSRF token returned by /api/me, required in X-CSRF-Token on POST/PUT/DELETE
    * Origin check against allowed list from settings
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from argon2 import PasswordHasher
from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(BASE_DIR))

from jarvis.tasks import DB_PATH  # noqa: E402

router = APIRouter(tags=["auth"])

_hasher = PasswordHasher()


def _db() -> sqlite3.Connection:
    """Short-lived connection to the shared jarvis.db (reads JARVIS_DB env)."""
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


_AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    is_owner      INTEGER NOT NULL DEFAULT 1,
    locked_until  TEXT,
    failed_count  INTEGER NOT NULL DEFAULT 0,
    last_attempt  TEXT
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    csrf_token  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
CREATE TABLE IF NOT EXISTS auth_failed_logins (
    identifier    TEXT PRIMARY KEY,
    count         INTEGER NOT NULL DEFAULT 0,
    lockout_until TEXT,
    last_attempt  TEXT
);
"""


def _ensure_schema() -> None:
    try:
        conn = _db()
        try:
            conn.executescript(_AUTH_SCHEMA)
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass


_ensure_schema()

# ---- constants ----
IDLE_TIMEOUT = timedelta(minutes=30)
ABSOLUTE_TIMEOUT = timedelta(hours=12)
LOCKOUT_BASE = 5 * 60  # 5 minutes
MAX_FAILURES = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_password(password: str) -> str:
    return _hasher.hash(password)


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except Exception:
        return False


def _make_token() -> str:
    return secrets.token_urlsafe(32)


def _make_csrf() -> str:
    return secrets.token_urlsafe(24)


# ---- owner / failure helpers ----

def _owner_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM auth_users WHERE is_owner=1 LIMIT 1").fetchone()
    return row is not None


def _rate_limit_key(identifier: str) -> str:
    return (identifier or "").strip().lower() or "anonymous"


def _fetch_failures(identifier: str):
    conn = _db()
    try:
        return conn.execute(
            "SELECT count, lockout_until FROM auth_failed_logins WHERE identifier=?",
            (identifier,),
        ).fetchone()
    finally:
        conn.close()


def _record_failure(identifier: str) -> tuple[int, Optional[datetime]]:
    """Record a failed login attempt. Returns (count, lockout_until)."""
    key = _rate_limit_key(identifier)
    now = datetime.now(timezone.utc)
    row = _fetch_failures(key)
    count = int(row["count"]) if row else 0
    count += 1
    lockout_until = None
    if count >= MAX_FAILURES:
        minutes = LOCKOUT_BASE * (2 ** (count - MAX_FAILURES))
        lockout_until = now + timedelta(minutes=minutes)
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO auth_failed_logins (identifier, count, lockout_until, last_attempt) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(identifier) DO UPDATE SET "
            "count=excluded.count, lockout_until=excluded.lockout_until, "
            "last_attempt=excluded.last_attempt",
            (key, count,
             lockout_until.isoformat(timespec="seconds") if lockout_until else None,
             now.isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return count, lockout_until


def _clear_failures(identifier: str) -> None:
    key = _rate_limit_key(identifier)
    conn = _db()
    try:
        conn.execute("DELETE FROM auth_failed_logins WHERE identifier=?", (key,))
        conn.commit()
    finally:
        conn.close()


def _is_locked(identifier: str) -> Optional[datetime]:
    row = _fetch_failures(identifier)
    if not row:
        return None
    until = _parse_iso(row["lockout_until"]) if row["lockout_until"] else None
    if until and until > datetime.now(timezone.utc):
        return until
    return None


def _request_identifier(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "anonymous"


def _check_origin(request: Request) -> None:
    """Reject requests whose Origin is not in the allowed list."""
    from api.main import get_allowed_origins  # noqa: PLC0415

    allowed = get_allowed_origins()
    origin = request.headers.get("origin")
    if not origin:
        return
    if allowed and origin not in allowed:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="origin not allowed",
        )


# ---- CSRF ----

def _constant_time_compare(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


def _require_csrf(request: Request) -> None:
    """Validate X-CSRF-Token against the session's csrf_token on mutating methods."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    provided = request.headers.get("x-csrf-token", "")
    session = getattr(request.state, "session", None)
    if not session or not provided:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="csrf token required")
    if not _constant_time_compare(provided, session["csrf_token"]):
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="csrf token invalid")


# ---- session ----

def get_session_from_request(request: Request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get("session")
    if not token:
        return None
    token_hash = _hash_token(token)
    conn = _db()
    try:
        row = conn.execute(
            "SELECT s.*, u.username FROM auth_sessions s "
            "JOIN auth_users u ON u.id=s.user_id WHERE s.token_hash=?",
            (token_hash,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    now = datetime.now(timezone.utc)
    last_seen = _parse_iso(row["last_seen"])
    expires_at = _parse_iso(row["expires_at"])
    if expires_at and expires_at <= now:
        return None  # absolute timeout
    if last_seen and last_seen + IDLE_TIMEOUT <= now:
        return None  # idle timeout
    # refresh last_seen
    conn = _db()
    try:
        conn.execute(
            "UPDATE auth_sessions SET last_seen=? WHERE token_hash=?",
            (now.isoformat(timespec="seconds"), token_hash),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": row["user_id"],
        "username": row["username"],
        "csrf_token": row["csrf_token"],
    }


def require_user(request: Request) -> Dict[str, Any]:
    """Dependency: authenticate via session cookie; raise 401 if missing/invalid."""
    session = get_session_from_request(request)
    if not session:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    return session


# ---- routes ----

class SetupPayload(BaseModel):
    username: str
    password: str


@router.post("/setup")
def setup(payload: SetupPayload, request: Request, response: Response):
    """Create the owner account (first-run only, min 12 chars)."""
    _check_origin(request)
    _ensure_schema()
    conn = _db()
    try:
        if _owner_exists(conn):
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="auth already configured",
            )
        username = (payload.username or "").strip()
        password = payload.password or ""
        if len(username) < 3:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="invalid credentials",
            )
        if len(password) < 12:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="invalid credentials",
            )
        now = _now_iso()
        conn.execute(
            "INSERT INTO auth_users (username, password_hash, created_at, is_owner) "
            "VALUES (?,?,?,1)",
            (username, _hash_password(password), now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


class LoginPayload(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginPayload, request: Request, response: Response):
    """Verify credentials and issue a session cookie."""
    _check_origin(request)
    username = (payload.username or "").strip()
    password = payload.password or ""
    identifier = _rate_limit_key(username)

    until = _is_locked(identifier)
    if until:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="too many attempts, try again later",
        )

    conn = _db()
    try:
        row = conn.execute(
            "SELECT * FROM auth_users WHERE username=? LIMIT 1", (username,)
        ).fetchone()
        ok = bool(row) and _verify_password(password, row["password_hash"])
    finally:
        conn.close()

    if not ok:
        count, lockout_until = _record_failure(identifier)
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    _clear_failures(identifier)

    token = _make_token()
    token_hash = _hash_token(token)
    csrf_token = _make_csrf()
    now = datetime.now(timezone.utc)
    expires_at = now + ABSOLUTE_TIMEOUT
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, csrf_token, created_at, "
            "last_seen, expires_at) VALUES (?,?,?,?,?,?)",
            (token_hash, row["id"], csrf_token, now.isoformat(timespec="seconds"),
             now.isoformat(timespec="seconds"), expires_at.isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()

    response.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="strict",
        path="/",
        max_age=int(ABSOLUTE_TIMEOUT.total_seconds()),
        secure=False,
    )
    return {"ok": True, "username": username}


@router.post("/logout")
def logout(request: Request, response: Response):
    """Clear the session cookie."""
    _check_origin(request)
    _require_csrf(request)
    token = request.cookies.get("session")
    if token:
        conn = _db()
        try:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash=?",
                         (_hash_token(token),))
            conn.commit()
        finally:
            conn.close()
    response.delete_cookie("session", path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    """Current user + CSRF token (needed for mutating requests)."""
    _check_origin(request)
    session = get_session_from_request(request)
    if not session:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    return {
        "id": session["id"],
        "username": session.get("username", ""),
        "csrf_token": session["csrf_token"],
    }


# make require_user importable elsewhere
__all__ = ["require_user", "get_session_from_request", "_check_origin", "_require_csrf"]
