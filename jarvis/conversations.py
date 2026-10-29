"""
jarvis/conversations.py - cached, read-only conversation loaders.

Moves recent_conversations() out of app_pages/chat.py and
search_conversations() out of jarvis/tasks.py so ui.py can import both
from one place without importing chat.py (which would draw widgets).
"""
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from . import tasks


def _ensure_title_table() -> None:
    try:
        with sqlite3.connect(str(tasks.DB_PATH), timeout=3) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS conversation_titles (
                thread_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
    except sqlite3.Error:
        pass


def recent_conversations(limit: int = 12) -> list:
    """[(thread_id, title), ...] newest first, for the sidebar."""
    _ensure_title_table()
    try:
        conn = sqlite3.connect(str(tasks.DB_PATH), timeout=3)
        try:
            rows = conn.execute(
                "SELECT thread_id, MAX(ts) AS last_ts FROM conversation_log "
                "WHERE thread_id LIKE 'ui-%' GROUP BY thread_id "
                "ORDER BY last_ts DESC LIMIT ?", (max(1, min(int(limit), 500)),)
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    out = []
    for thread_id, ckpt in rows:
        title = _conversation_title(thread_id, str(ckpt))
        if title:
            out.append((thread_id, title))
    return out


def _conversation_title(thread_id: str, checkpoint_id: str) -> str:
    """Use a saved title or a clean short title from the first user message."""
    _ensure_title_table()
    try:
        conn = sqlite3.connect(str(tasks.DB_PATH), timeout=3)
        try:
            saved = conn.execute(
                "SELECT title FROM conversation_titles WHERE thread_id=?", (thread_id,)
            ).fetchone()
            if saved and str(saved[0]).strip():
                return str(saved[0]).strip()
            row = conn.execute(
                "SELECT text FROM conversation_log WHERE thread_id=? ORDER BY ts ASC LIMIT 1",
                (thread_id,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return ""
    if not row:
        return ""
    transcript = str(row[0] or "")
    first = re.search(r"(?:^|\n)User:\s*(.*?)(?=\nJARVIS:|$)", transcript, re.S | re.I)
    text = (first.group(1) if first else transcript).strip()
    words = text.split()
    title = " ".join(words[:7])
    if len(words) > 7:
        title += "…"
    return title[:56] or "New chat"


def search_conversations(query: str, limit: int = 8) -> list[dict]:
    """Full-text (FTS5) search over past turns. Returns list of dicts
    {thread_id, ts, snippet}. Sanitizes the query so no FTS syntax crashes."""
    q = (query or "").strip()
    if not q:
        return []
    safe = re.sub(r"[^a-zA-Z0-9\s\-_]", " ", q).strip()
    if len(safe) < 2:
        return []
    limit = max(1, min(int(limit), 50))
    out = []
    try:
        conn = sqlite3.connect(str(tasks.DB_PATH), timeout=3)
        try:
            rows = conn.execute(
                "SELECT cl.thread_id, cl.ts, cl.text FROM conversation_fts f "
                "JOIN conversation_log cl ON cl.id = f.rowid "
                "WHERE conversation_fts MATCH ? ORDER BY cl.ts DESC LIMIT ?",
                (safe, limit),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    for r in rows:
        snippet = str(r["text"] or "").replace("\n", " ").strip()[:160]
        tail = "" if len(str(r["text"] or "")) <= 160 else "…"
        out.append({"thread_id": r["thread_id"], "ts": r["ts"],
                    "snippet": f"{snippet}{tail}"})
    return out
