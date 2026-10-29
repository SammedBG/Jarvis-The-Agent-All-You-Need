"""Conversation endpoints (list, detail, search, rename, delete)."""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query, Request
from pydantic import BaseModel
from starlette.status import HTTP_404_NOT_FOUND

from api.deps import require_user  # noqa: E402

router = APIRouter(tags=["conversations"])

from jarvis.conversations import recent_conversations, search_conversations  # noqa: E402
from jarvis.tasks import DB_PATH  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(BASE_DIR))

from jarvis.conversations import recent_conversations, search_conversations  # noqa: E402
from jarvis.tasks import DB_PATH  # noqa: E402

_THREAD_RE = re.compile(r"^ui-(\d{8})-(\d{6})$")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _thread_date(thread_id: str) -> Optional[date]:
    m = _THREAD_RE.match(thread_id or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8]))
    except ValueError:
        return None


@router.get("/conversations")
def list_conversations(
    request: Request,
    limit: int = Query(12, ge=1, le=500),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    """List conversations grouped Today / Yesterday / Earlier."""
    recents = recent_conversations(limit=limit) if recent_conversations else []
    today = date.today()
    yesterday = today - timedelta(days=1)
    groups = {"today": [], "yesterday": [], "earlier": []}
    for thread_id, title in recents:
        dt = _thread_date(thread_id)
        if dt == today:
            groups["today"].append({"thread_id": thread_id, "title": title or "(untitled)"})
        elif dt == yesterday:
            groups["yesterday"].append({"thread_id": thread_id, "title": title or "(untitled)"})
        else:
            groups["earlier"].append({"thread_id": thread_id, "title": title or "(untitled)"})
    return groups


@router.get("/conversations/{thread_id}")
def get_conversation(
    thread_id: str = PathParam(...),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    """Return the messages of a conversation."""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT text, ts FROM conversation_log WHERE thread_id=? ORDER BY ts ASC, id ASC",
            (thread_id,),
        ).fetchall()
    finally:
        conn.close()
    messages = []
    for row in rows:
        transcript = str(row["text"] or "")
        user_match = re.search(r"(?:^|\n)User:\s*(.*?)(?=\nJARVIS:|$)", transcript, re.S | re.I)
        assistant_match = re.search(r"(?:^|\n)JARVIS:\s*(.*)$", transcript, re.S | re.I)
        if user_match and user_match.group(1).strip():
            messages.append({"role": "user", "content": user_match.group(1).strip(), "ts": row["ts"]})
        if assistant_match and assistant_match.group(1).strip():
            messages.append({"role": "assistant", "content": assistant_match.group(1).strip(), "ts": row["ts"]})
        if not user_match and not assistant_match and transcript.strip():
            messages.append({"role": "assistant", "content": transcript.strip(), "ts": row["ts"]})
    return {"thread_id": thread_id, "messages": messages}


@router.get("/search")
def search_conversations_route(
    q: str = Query("", description="search query"),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    """Full-text search over past conversations."""
    hits = search_conversations(q) if search_conversations else []
    return {"results": hits[:8]}


class RenamePayload(BaseModel):
    title: str


@router.patch("/conversations/{thread_id}")
def rename_conversation(
    thread_id: str = PathParam(...),
    payload: Optional[RenamePayload] = None,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    """Rename a conversation (stored as a decision log entry)."""
    from jarvis.conversations import _ensure_title_table  # noqa: PLC0415

    _ensure_title_table()
    title = (payload.title or "").strip() if payload else ""
    if not title or len(title) > 80:
        raise HTTPException(status_code=400, detail="title must be between 1 and 80 characters")
    conn = _db()
    try:
        exists = conn.execute("SELECT 1 FROM conversation_log WHERE thread_id=? LIMIT 1", (thread_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="conversation not found")
        conn.execute(
            "INSERT INTO conversation_titles(thread_id,title,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(thread_id) DO UPDATE SET title=excluded.title, updated_at=excluded.updated_at",
            (thread_id, title, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "thread_id": thread_id, "title": title}


@router.delete("/conversations/{thread_id}")
def delete_conversation(
    thread_id: str = PathParam(...),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    """Delete a conversation (its log entries)."""
    from jarvis.conversations import _ensure_title_table  # noqa: PLC0415

    _ensure_title_table()
    conn = _db()
    try:
        cur = conn.execute("DELETE FROM conversation_log WHERE thread_id=?", (thread_id,))
        conn.execute("DELETE FROM conversation_titles WHERE thread_id=?", (thread_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="conversation not found")
    finally:
        conn.close()
    return {"ok": True, "thread_id": thread_id}
