"""
app_data.py - cached, read-only data loaders shared by the dashboard pages.

No LLM and no agent import here, so the Today / Tasks / Memory / Documents
pages stay fast even when the Groq API is down or rate-limited.
Every loader is cached; call bust() after any write so the next render
shows fresh data.
"""
import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from . import memory as long_memory
from .tasks import current_user

TASK_COLS = ["id", "title", "details", "due", "due_time", "priority", "repeat",
             "status", "created_at", "closed_at"]


def bust() -> None:
    """Invalidate every cached loader (call after any task/rule/memory write)."""
    st.cache_data.clear()


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    import sqlite3

    from .tasks import DB_PATH

    conn = sqlite3.connect(str(DB_PATH), timeout=3)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


_RANK = ("CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 "
         "WHEN 'normal' THEN 2 ELSE 3 END")


@st.cache_data(ttl=60, show_spinner=False)
def tasks_df(status: str = "pending") -> pd.DataFrame:
    """The current user's tasks for one status, ordered by due date then priority."""
    rows = _rows(
        f"SELECT {', '.join(TASK_COLS)} FROM tasks WHERE status=? AND user_id=? "
        f"ORDER BY due IS NULL, due, {_RANK}",
        (status, current_user()),
    )
    df = pd.DataFrame(rows, columns=TASK_COLS)
    if not df.empty:
        df["due"] = df["due"].fillna("")
        df["due_time"] = df["due_time"].fillna("")
        df["details"] = df["details"].fillna("")
        df["repeat"] = df["repeat"].fillna("")
    return df


@st.cache_data(ttl=60, show_spinner=False)
def task_counts() -> dict:
    """KPI numbers for the Today page, plus a 14-day completion series."""
    today = date.today()
    iso = today.isoformat()
    week = (today + timedelta(days=7)).isoformat()
    rows = _rows("SELECT due, closed_at FROM tasks WHERE status='pending' AND user_id=?",
                 (current_user(),))
    done = _rows("SELECT closed_at FROM tasks WHERE status='done' AND user_id=? "
                 "AND closed_at >= ?", (current_user(), (today - timedelta(days=14)).isoformat()))
    done_7d = _rows("SELECT 1 FROM tasks WHERE status='done' AND user_id=? AND closed_at >= ?",
                    (current_user(), (today - timedelta(days=7)).isoformat()))
    series = []
    for i in range(13, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        series.append({"day": d, "done": sum(1 for r in done
                                             if (r["closed_at"] or "")[:10] == d)})
    return {
        "overdue": sum(1 for r in rows if r["due"] and r["due"] < iso),
        "today": sum(1 for r in rows if r["due"] == iso),
        "week": sum(1 for r in rows if r["due"] and iso < r["due"] <= week),
        "nodue": sum(1 for r in rows if not r["due"]),
        "done_7d": len(done_7d),
        "series": pd.DataFrame(series),
    }   


@st.cache_data(ttl=60, show_spinner=False)
def rules_df() -> pd.DataFrame:
    rows = _rows("SELECT id, text, created_at FROM rules WHERE active=1 AND user_id=? ORDER BY id",
                 (current_user(),))
    return pd.DataFrame(rows, columns=["id", "text", "created_at"])


@st.cache_data(ttl=60, show_spinner=False)
def decisions_df(limit: int = 30) -> pd.DataFrame:
    rows = _rows("SELECT id, text, created_at FROM decisions WHERE user_id=? "
                 "ORDER BY id DESC LIMIT ?", (current_user(), limit))
    return pd.DataFrame(rows, columns=["id", "text", "created_at"])


@st.cache_data(ttl=60, show_spinner=False)
def memories_df() -> pd.DataFrame:
    rows = [{"id": i, "text": t} for i, t in long_memory.list_facts()]
    return pd.DataFrame(rows, columns=["id", "text"])


@st.cache_data(ttl=300, show_spinner=False)
def index_stats() -> dict:
    """What is currently in the RAG index (no re-indexing, just a peek)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from rag import INDEX_DIR

    path = INDEX_DIR / "chunks.json"
    if not path.exists():
        return {"files": 0, "chunks": 0, "sources": []}
    chunks = json.loads(path.read_text(encoding="utf-8"))
    counts: dict = {}
    for c in chunks:
        counts[c["source"]] = counts.get(c["source"], 0) + 1
    return {
        "files": len(counts),
        "chunks": len(chunks),
        "sources": [{"source": s, "chunks": n} for s, n in sorted(counts.items())],
    }
