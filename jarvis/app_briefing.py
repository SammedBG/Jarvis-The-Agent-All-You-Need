"""
app_briefing.py - the proactive morning briefing.

Once per day, at YOUR briefing time (default 08:00, change it on the Today
page), the agent writes a short message first: overdue items, today's plan
with times, one suggestion, a recent decision.

Rules of the road:
  - generation runs ONLY on the main script thread (LangGraph + sqlite are
    not thread-safe) - the ui.py fragment calls it, never the watcher;
  - the result is cached in the settings table for the rest of the day;
  - if the LLM fails (rate limit, no key) we fall back to the raw daily
    briefing, so a card ALWAYS appears - the ↻ button retries the LLM;
  - the watcher's desktop nudge fires only while nothing is written yet,
    so you never get a popup for a briefing you're already looking at.
"""
import sqlite3
from datetime import date, datetime, time as dtime

from .tasks import DB_PATH

DEFAULT_TIME = "08:00"
ENABLED_KEY = "briefing_enabled"
TIME_KEY = "briefing_time"

_PROMPT = (
    "Write my morning briefing for today. Use each tool at most ONCE, in this order, "
    "and never guess from memory:\n"
    "  1) daily_briefing\n"
    "  2) list_decisions(limit=5)\n"
    "  3) list_tasks(view='today')\n"
    "  4) list_habits()\n"
    "  5) check_email(limit=5)                          (skip gracefully if 'not configured')\n"
    "  6) one single web_search for a recent tech headline  (skip if it returns nothing useful)\n"
    "Do NOT retry a tool that failed or returned nothing, and do not loop.\n"
    "Then reply with a warm, short message (max 10 short lines, plain text, no "
    "headers, no markdown): 1) anything overdue, 2) what's due today with times, "
    "3) one practical suggestion for the day, 4) at most one recent decision worth "
    "remembering, 5) any important unread email, 6) one recent tech headline. "
    "Address the user directly, as if you noticed their day for them. "
    "Read-only tools only."
)

_notified = ""  # date whose desktop nudge already fired


# --------------------------------------------------------------------------
# settings (own short-lived connections: callable from fragments and threads)
# --------------------------------------------------------------------------

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), timeout=3)
    c.row_factory = sqlite3.Row
    return c


def get_setting(key: str, default: str = "") -> str:
    try:
        with _conn() as c:
            row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    except sqlite3.Error:
        return default


def set_setting(key: str, value: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "updated_at=excluded.updated_at",
            (key, value, datetime.now().isoformat(timespec="seconds")),
        )


def briefing_time() -> str:
    return get_setting(TIME_KEY, DEFAULT_TIME)


def enabled() -> bool:
    return get_setting(ENABLED_KEY, "1") == "1"


def _text_key() -> str:
    return f"briefing_{date.today().isoformat()}"


def today_text() -> str | None:
    return get_setting(_text_key()) or None


def clear_today() -> None:
    set_setting(_text_key(), "")


def _save_today(text: str) -> None:
    set_setting(_text_key(), text)
    # keep the settings table lean: drop every other day's briefing
    try:
        with _conn() as c:
            c.execute("DELETE FROM settings WHERE key LIKE 'briefing_2%' "
                      "AND key != ?", (_text_key(),))
    except sqlite3.Error:
        pass


# --------------------------------------------------------------------------
# timing
# --------------------------------------------------------------------------

def due(now: datetime | None = None) -> bool:
    """True when the configured time has passed and nothing is written yet."""
    now = now or datetime.now()
    t = briefing_time()
    if not enabled() or not t or today_text() is not None:
        return False
    try:
        dtime.fromisoformat(t)
    except ValueError:
        return False
    return now.strftime("%H:%M") >= t


def notify_due(now: datetime | None = None) -> bool:
    """Watcher hook: nudge the desktop ONCE, and only while no briefing
    exists yet (no popup for something you're already reading)."""
    global _notified
    now = now or datetime.now()
    today = now.date().isoformat()
    t = briefing_time()
    if not enabled() or not t or today_text() is not None:
        return False
    if now.strftime("%H:%M") < t or _notified == today:
        return False
    _notified = today
    return True


# --------------------------------------------------------------------------
# generation (main thread only)
# --------------------------------------------------------------------------

def _llm_briefing() -> str:
    """Ask the agent for the briefing. Raises on any problem."""
    from . import agent  # lazy: pages that only read settings don't need a key

    out = agent.ask_agent(_PROMPT, thread_id=f"briefing-{date.today().isoformat()}")
    reply = (out.get("reply") or "").strip()
    if out.get("error") or out.get("pending") or not reply:
        raise RuntimeError(str(out.get("error") or "empty reply / needs approval"))
    return reply


def generate() -> str:
    """Write today's briefing (LLM, with the raw plan as a guaranteed
    fallback) and cache it for the rest of the day."""
    text = ""
    try:
        text = _llm_briefing()
    except Exception:
        text = ""
    if not text:
        try:
            from .tasks import daily_briefing

            text = daily_briefing.invoke({})  # rate-limited? still a useful plan
        except Exception as e:
            text = f"Could not build today's briefing: {e}"
    _save_today(text)
    return text
