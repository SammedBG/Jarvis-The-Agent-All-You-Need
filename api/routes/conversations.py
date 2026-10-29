"""Conversation endpoints (list, detail, search, rename, delete)."""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
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
def list_conversations(request, user: dict = Depends(require_user)):  # type: ignore[arg-type]
    """List conversations grouped Today / Yesterday / Earlier."""
    recents = recent_conversations() if recent_conversations else []
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
    from jarvis.tasks import log_conversation  # noqa: PLC0415

    conn = _db()
    try:
        rows = conn.execute(
            "SELECT role, content, ts FROM conversation_log WHERE thread_id=? ORDER BY ts ASC",
            (thread_id,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="conversation not found")
    messages = [
        {"role": r["role"], "content": r["content"], "ts": r["ts"]} for r in rows
    ]
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
    from jarvis.tasks import log_decision  # noqa: PLC0415

    title = (payload.title or "").strip() if payload else ""
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    conn = _db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM conversation_log WHERE thread_id=? LIMIT 1", (thread_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="conversation not found")
    finally:
        conn.close()
    log_decision(f"Renamed conversation {thread_id} to '{title}'")
    return {"ok": True, "thread_id": thread_id, "title": title}


@router.delete("/conversations/{thread_id}")
def delete_conversation(
    thread_id: str = PathParam(...),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    """Delete a conversation (its log entries)."""
    conn = _db()
    try:
        cur = conn.execute("DELETE FROM conversation_log WHERE thread_id=?", (thread_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="conversation not found")
    finally:
        conn.close()
    return {"ok": True, "thread_id": thread_id}
