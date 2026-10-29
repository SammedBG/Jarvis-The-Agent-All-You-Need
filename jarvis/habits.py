"""
habits.py - daily check-in habits with streak tracking.

A habit is just a name you check in for each day. There's no preset list - use
`log_habit("morning run")` whenever you've done it; the first call creates the
habit. Streaks count consecutive days up to today (missing a day resets to 1).

Everything is stored in jarvis.db so it survives refreshes, restarts and the
desktop overlay. Read-only helpers (for the briefing / prompt) are plain
functions; the agent tools are added in agent.py.
"""
from __future__ import annotations

import datetime
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("JARVIS_DB", os.environ.get("AGNET_TASKS_DB", BASE_DIR / "jarvis.db")))
MAX_NAME = 60
MAX_HABITS = 20


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), timeout=3)
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE IF NOT EXISTS habits "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
        " date TEXT NOT NULL, user_id INTEGER NOT NULL DEFAULT 1)"
    )
    c.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_habits_name_date "
        "ON habits(name, date, user_id)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_habits_user_name ON habits(user_id, name)")
    c.commit()
    return c


def _today() -> str:
    return datetime.date.today().isoformat()


def _streak(name: str, user_id: int = 1) -> int:
    """Consecutive days ending at today OR yesterday (so an in-progress streak
    still shows before you've logged today's check-in)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT date FROM habits WHERE name=? AND user_id=?", (name, user_id)
        ).fetchall()
    dates = {r["date"] for r in rows}
    today = datetime.date.today()
    start = today if today.isoformat() in dates else today - datetime.timedelta(days=1)
    if start.isoformat() not in dates:
        return 0
    n = 0
    d = start
    while d.isoformat() in dates:
        n += 1
        d -= datetime.timedelta(days=1)
    return n


def log_habit(name: str, user_id: int = 1) -> str:
    """Record today's check-in for the habit. Idempotent per day."""
    name = _clean_name(name)
    if not name:
        return "Error: habit name required, e.g. log_habit('morning run')"
    if len(name) > MAX_NAME:
        return f"Error: keep the habit name under {MAX_NAME} characters."
    today = _today()
    with _conn() as c:
        try:
            c.execute(
                "INSERT INTO habits (name, date, user_id) VALUES (?,?,?)",
                (name, today, user_id),
            )
            c.commit()
            added = True
        except sqlite3.IntegrityError:
            added = False
    streak_n = _streak(name, user_id)
    badge = "" if streak_n < 3 else ("🔥" if streak_n < 10 else "🔥🔥")
    when = "logged" if added else "already checked in"
    return f"{badge} Habit '{name}' {when} for {today} - streak: {streak_n} day{'s' if streak_n != 1 else ''}."


def list_habits(user_id: int = 1) -> list[dict]:
    with _conn() as c:
        names = [r["name"] for r in c.execute(
            "SELECT DISTINCT name FROM habits WHERE user_id=? ORDER BY name", (user_id,)).fetchall()]
    out = []
    for name in names:
        s = _streak(name, user_id)
        today_ok = name in list_habits_checked_today(user_id)
        out.append({"name": name, "streak": s, "checked_today": today_ok})
    return out


def list_habits_checked_today(user_id: int = 1) -> set[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT name FROM habits WHERE user_id=? AND date=?", (user_id, _today())
        ).fetchall()
    return {r["name"] for r in rows}


def delete_habit(name: str, user_id: int = 1) -> str:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM habits WHERE name=? AND user_id=?", (name, user_id)
        )
        c.commit()
    if cur.rowcount:
        return f"Removed habit '{name}' entirely (all history)."
    return f"No habit named '{name}'."


def habits_summary() -> str:
    """Short human-readable summary for the briefing / prompt."""
    items = list_habits(1)
    if not items:
        return "No habits tracked yet."
    lines = []
    for h in items:
        mark = "✅" if h["checked_today"] else "⬜"
        badge = "🔥" if h["streak"] >= 3 else ""
        lines.append(f"- {mark} {h['name']}: {h['streak']} day{'s' if h['streak'] != 1 else ''} {badge}".rstrip())
    return "\n".join(lines)


def _clean_name(name):
    import re
    return re.sub(r"\s+", " ", (name or "").strip())


if __name__ == "__main__":
    print(habits_summary())

def habits_block() -> str:
    """Short one-line summary appended to the system prompt each turn."""
    items = list_habits(1)
    if not items:
        return ""
    joined = ", ".join(
        f"{h['name']} {h['streak']}d{'✓' if h['checked_today'] else ''}" for h in items[:5]
    )
    return f"\n\nHABITS (daily check-ins): {joined}"
