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


def recent_conversations(limit: int = 12) -> list:
    """[(thread_id, title), ...] newest first, for the sidebar."""
    try:
        conn = sqlite3.connect(str(tasks.DB_PATH), timeout=3)
        try:
            rows = conn.execute(
                "SELECT thread_id, MAX(checkpoint_id) FROM checkpoints "
                "WHERE thread_id LIKE 'ui-%' GROUP BY thread_id "
                "ORDER BY MAX(checkpoint_id) DESC LIMIT ?", (limit,)
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
    """First up to 5 words of what you said — short, no-orphan, unique-ish."""
    try:
        conn = sqlite3.connect(str(tasks.DB_PATH), timeout=3)
        try:
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
    words = str(row[0] or "").split()
    text = " ".join(words[:5])
    if len(words) > 5:
        text = text + "…"
    return text[:40] or "(untitled)"


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
