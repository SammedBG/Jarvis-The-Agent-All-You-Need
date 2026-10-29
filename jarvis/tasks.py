"""
Personal task / rule / decision manager backed by SQLite (tasks.db).

  users + sessions live here too (see auth.py) so one file = one backup
  tasks     - what TO do: title, due date, priority, status  (per user)
  rules     - what NOT to do: standing constraints           (per user)
  decisions - journal of choices / cancellations             (per user)

Multi-user: every read/write is filtered by the CURRENT_USER context var.
The terminal CLI runs as user 1 (the first/admin account); the server sets
the real user per request in its auth layer.

Exposed as LangChain tools in agent.py.
"""
import os
import contextvars
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from langchain_core.tools import tool

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("JARVIS_DB", os.environ.get("AGNET_TASKS_DB", BASE_DIR / "jarvis.db")))

PRIORITIES = ("low", "normal", "high", "urgent")

# --------------------------------------------------------------------------
# current user (set by server.py per request; default = terminal owner)
# --------------------------------------------------------------------------

CURRENT_USER: contextvars.ContextVar[int] = contextvars.ContextVar("agnet_user", default=1)


def current_user() -> int:
    return CURRENT_USER.get()


def set_user(user_id: int) -> contextvars.Token:
    return CURRENT_USER.set(int(user_id))


_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute("PRAGMA journal_mode=WAL")
_conn.execute("PRAGMA busy_timeout=5000")
_conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT NOT NULL,
        details     TEXT NOT NULL DEFAULT '',
        due         TEXT,                    -- ISO date YYYY-MM-DD or NULL
        priority    TEXT NOT NULL DEFAULT 'normal',
        status      TEXT NOT NULL DEFAULT 'pending',  -- pending | done | cancelled
        created_at  TEXT NOT NULL,
        closed_at   TEXT,                    -- when completed or cancelled
        user_id     INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS rules (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        text        TEXT NOT NULL,
        active      INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        user_id     INTEGER NOT NULL DEFAULT 1,
        source      TEXT NOT NULL DEFAULT 'unknown',
        origin      TEXT
    );
    CREATE TABLE IF NOT EXISTS decisions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        text        TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        user_id     INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS settings (
        key         TEXT PRIMARY KEY,
        value       TEXT,
        updated_at  TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id, status, due);
    CREATE INDEX IF NOT EXISTS idx_rules_user ON rules(user_id, active);
    CREATE INDEX IF NOT EXISTS idx_decisions_user ON decisions(user_id, id);
    CREATE TABLE IF NOT EXISTS usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        user_id INTEGER NOT NULL DEFAULT 1,
        model TEXT NOT NULL,
        route TEXT NOT NULL DEFAULT 'complex',
        thread_id TEXT,
        prompt_tokens INTEGER NOT NULL DEFAULT 0,
        completion_tokens INTEGER NOT NULL DEFAULT 0,
        total_tokens INTEGER NOT NULL DEFAULT 0,
        latency_ms INTEGER NOT NULL DEFAULT 0,
        endpoint TEXT,
        status TEXT NOT NULL DEFAULT 'ok',
        error TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts);
    CREATE INDEX IF NOT EXISTS idx_usage_user ON usage(user_id, route);
    CREATE TABLE IF NOT EXISTS activity_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          TEXT NOT NULL,
        user_id     INTEGER NOT NULL DEFAULT 1,
        tool        TEXT NOT NULL,
        args        TEXT,
        result      TEXT,
        status      TEXT NOT NULL DEFAULT 'ran',
        route       TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_activity_user_ts ON activity_log(user_id, ts);
    """
)


def _migrate() -> None:
    """Add user_id to tables created by v1 (pre-accounts) and claim old rows."""
    for table in ("tasks", "rules", "decisions"):
        cols = [r[1] for r in _conn.execute(f"PRAGMA table_info({table})")]
        if "user_id" not in cols:
            _conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1")
        _conn.execute(f"UPDATE {table} SET user_id=1 WHERE user_id IS NULL")
    _rcols = [r[1] for r in _conn.execute("PRAGMA table_info(rules)")]
    if "source" not in _rcols:
        try: _conn.execute("ALTER TABLE rules ADD COLUMN source TEXT NOT NULL DEFAULT 'unknown'")
        except sqlite3.Error: pass
    if "origin" not in _rcols:
        try: _conn.execute("ALTER TABLE rules ADD COLUMN origin TEXT")
        except sqlite3.Error: pass
    _rcols = [r[1] for r in _conn.execute("PRAGMA table_info(rules)")]
    if "source" not in _rcols:
        try: _conn.execute("ALTER TABLE rules ADD COLUMN source TEXT NOT NULL DEFAULT 'unknown'")
        except sqlite3.Error: pass
    if "origin" not in _rcols:
        try: _conn.execute("ALTER TABLE rules ADD COLUMN origin TEXT")
        except sqlite3.Error: pass
    # reminders: 'remind me at 4 pm' needs a time next to the date,
    # and 'every day' needs a repeat rule + an optional snooze
    cols = [r[1] for r in _conn.execute("PRAGMA table_info(tasks)")]
    for col in ("due_time", "repeat", "snoozed_until"):
        if col not in cols:
            _conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} TEXT")
    _conn.commit()
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_due_status ON tasks(user_id, due, status)")
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_time ON tasks(due, due_time)")
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_rules_user_active ON rules(user_id, active)")
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_user_created ON decisions(user_id, created_at)")
    _conn.commit()


_migrate()

# Conversation search index (populated by agent at the end of each turn).
try:
    _conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversation_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT,
            user_id   INTEGER NOT NULL DEFAULT 1,
            text      TEXT NOT NULL,
            ts        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_convlog_thread ON conversation_log(thread_id, id);
        CREATE VIRTUAL TABLE IF NOT EXISTS conversation_fts
            USING fts5(content, content='conversation_log', content_rowid='id');
    """)
    # keep FTS5 in sync with conversation_log via triggers (idempotent)
    _conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS trg_convlog_ai AFTER INSERT ON conversation_log BEGIN
            INSERT INTO conversation_fts(rowid, content) VALUES (NEW.id, NEW.text);
        END;
        CREATE TRIGGER IF NOT EXISTS trg_convlog_ad AFTER DELETE ON conversation_log BEGIN
            INSERT INTO conversation_fts(conversation_fts, rowid) VALUES ('delete', OLD.id);
        END;
        CREATE TRIGGER IF NOT EXISTS trg_convlog_au AFTER UPDATE ON conversation_log BEGIN
            INSERT INTO conversation_fts(conversation_fts, rowid) VALUES ('delete', OLD.id);
            INSERT INTO conversation_fts(rowid, content) VALUES (NEW.id, NEW.text);
        END;
    """)
    _conn.commit()
except sqlite3.Error:
    pass


def log_conversation(thread_id: str | None, text: str, user_id: int = 1) -> None:
    """Append a turn summary (user+assistant text) for search."""
    text = (text or "").strip()
    if not text:
        return
    try:
        cur = _conn.execute(
            "INSERT INTO conversation_log (thread_id, user_id, text, ts) VALUES (?,?,?,?)",
            (str(thread_id) if thread_id else None, int(user_id), text[:4000],
             datetime.now().isoformat(timespec="seconds")),
        )
        _conn.commit()
    except sqlite3.Error:
        pass


def prune_checkpoints(keep_per_thread: int = 50) -> int:
    """Delete checkpoints beyond the last `keep_per_thread` per thread.

    Runs once per process. Returns number removed. Acts on the jarvis.db
    checkpoints table written by the LangGraph SqliteSaver.
    """
    # Skip threads holding a pending approval so we don't orphan an open conversation.
    _pending_threads = set()
    try:
        from jarvis import agent as _agent_mod
        for (_tid,) in _conn.execute("SELECT DISTINCT thread_id FROM checkpoints").fetchall():
            try:
                _cfg = {"configurable": {"thread_id": _tid}}
                if _agent_mod.get_pending(_cfg):
                    _pending_threads.add(_tid)
            except Exception:
                pass
    except Exception:
        _pending_threads = set()

    # conversation_log cap: off by default (only ON if AGNET_CONV_LOG_CAP is set)
    try:
        _cap = int(os.environ.get("AGNET_CONV_LOG_CAP", "0") or "0")
    except (TypeError, ValueError):
        _cap = 0
    if _cap and _cap > 0:
        try:
            existing = _conn.execute("SELECT COUNT(*) FROM conversation_log").fetchone()[0]
            if existing > _cap:
                # FTS external content handles its own rows via triggers (delete+insert)
                _conn.execute(
                    "DELETE FROM conversation_log WHERE id NOT IN "
                    "(SELECT id FROM conversation_log ORDER BY id DESC LIMIT ?)", (_cap,))
                _conn.commit()
        except sqlite3.Error:
            pass

    # checkpoints: keep last N per thread, skip pending threads
    removed = 0
    try:
        cur = _conn.execute("SELECT DISTINCT thread_id FROM checkpoints")
        threads = [r[0] for r in cur.fetchall()]
    except sqlite3.Error:
        return removed
    for tid in threads:
        if tid in _pending_threads:
            continue
        try:
            cur = _conn.execute(
                "SELECT checkpoint_id FROM checkpoints WHERE thread_id=? ORDER BY checkpoint_id DESC LIMIT ?",
                (tid, keep_per_thread),
            )
            keep = {r[0] for r in cur.fetchall()}
            if not keep:
                continue
            cur = _conn.execute(
                "DELETE FROM checkpoints WHERE thread_id=? AND checkpoint_id NOT IN "
                "(" + ",".join("?" for _ in keep) + ")",
                [tid, *keep],
            )
            removed += cur.rowcount
            # writes table has a foreign-ish thread id; prune matching rows too
            _conn.execute("DELETE FROM writes WHERE thread_id=? AND checkpoint_id NOT IN "
                          "(" + ",".join("?" for _ in keep) + ")", [tid, *keep])
            _conn.commit()
        except sqlite3.Error:
            _conn.rollback()
    try:
        _conn.execute("INSERT INTO conversation_fts(conversation_fts) VALUES('rebuild')")
        _conn.commit()
    except sqlite3.Error:
        pass
    try:
        _conn.execute("PRAGMA optimize")
        _conn.commit()
    except sqlite3.Error:
        pass
    return removed


_MAINTAINED = False


def ensure_maintained() -> None:
    global _MAINTAINED
    if _MAINTAINED:
        return
    _MAINTAINED = True
    prune_checkpoints()



_migrate()

# migration for usage table added in Step 1 (status, error)
try:
    _cols = [r[1] for r in _conn.execute("PRAGMA table_info(usage)").fetchall()]
    if _cols and "status" not in _cols:
        _conn.execute("ALTER TABLE usage ADD COLUMN status TEXT NOT NULL DEFAULT 'ok'")
    if _cols and "error" not in _cols:
        _conn.execute("ALTER TABLE usage ADD COLUMN error TEXT")
    _conn.commit()
except sqlite3.Error:
    pass


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _today() -> date:
    return date.today()


def parse_due(value: str) -> str | None:
    """'2026-11-15', 'today', 'tomorrow', 'friday' -> ISO date. '' -> None."""
    v = (value or "").strip().lower()
    if not v or v in {"none", "null", "no due date", "someday"}:
        return None
    if v == "today":
        return _today().isoformat()
    if v == "tomorrow":
        return (_today() + timedelta(days=1)).isoformat()
    if v == "next week":
        return (_today() + timedelta(days=7)).isoformat()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %B %Y", "%B %d", "%d %b"):
        try:
            d = datetime.strptime(v, fmt)
            y = d.year if "%Y" in fmt else _today().year
            return date(y, d.month, d.day).isoformat()
        except ValueError:
            continue
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if v in weekdays:
        cur = _today()
        delta = (weekdays.index(v) - cur.weekday()) % 7 or 7
        return (cur + timedelta(days=delta)).isoformat()
    return v  # unknown format: return as-is so the model sees the problem


def _to24(h: int, ap: str) -> int | None:
    if not 1 <= h <= 12:
        return None
    if ap == "pm" and h != 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    return h


def parse_time(value: str) -> str | None:
    """Find a clock time in free text: '2:12 pm'->'14:12', '09:00'->'09:00',
    'at 4 pm'->'16:00', 'noon'->'12:00', 'midnight'->'00:00'. None if no time."""
    v = (value or "").strip().lower()
    if not v:
        return None
    if "midnight" in v:
        return "00:00"
    if "noon" in v:
        return "12:00"
    m = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", v)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
        if ap:
            h = _to24(h, ap)
            if h is None:
                return None
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return None
        return f"{h:02d}:{mi:02d}"
    m = re.search(r"\b(\d{1,2})\s*(am|pm)\b", v)
    if m:
        h = _to24(int(m.group(1)), m.group(2))
        return f"{h:02d}:00" if h is not None else None
    return None


def split_when(value: str) -> tuple[str, str | None]:
    """Pull the clock time out of a due string, keeping the date part.
    'today at 2:12 pm' -> ('today', '14:12'); 'friday' -> ('friday', None)."""
    v = (value or "").strip()
    tm = parse_time(v)
    if not tm:
        return v, None
    rest = re.sub(r"\b(?:at\s+)?\d{1,2}:\d{2}\s*(?:am|pm)?\b", " ", v, flags=re.I)
    rest = re.sub(r"\b(?:at\s+)?\d{1,2}\s*(?:am|pm)\b", " ", rest, flags=re.I)
    rest = re.sub(r"\b(?:at\s+)?(?:noon|midnight)\b", " ", rest, flags=re.I)
    rest = re.sub(r"^\s*at\s+|\s+at\s*$", " ", rest, flags=re.I)
    return " ".join(rest.split()), tm


def human_time(t: str | None) -> str:
    """'14:12' -> '2:12 pm' (pass-through when it isn't a clock time)."""
    if not t:
        return ""
    try:
        h, m = int(t[:2]), int(t[3:5])
    except (ValueError, IndexError):
        return t
    return f"{h % 12 or 12}:{m:02d} {'am' if h < 12 else 'pm'}"


REPEATS = ("hourly", "daily", "weekdays", "weekly", "monthly")


def parse_repeat(value: str) -> str:
    """Free text -> canonical repeat rule ('' = once).
    'every day'->'daily', 'weekdays'->'weekdays', 'every 2 hours'->'every:2h',
    'every 3 days'->'every:3d', 'every 2 weeks'->'every:2w'."""
    v = (value or "").strip().lower()
    if not v or v in {"none", "never", "once", "no", "off"}:
        return ""
    if v in REPEATS or re.fullmatch(r"every:\d+[hdwm]", v):
        return v  # canonical values pass through untouched
    m = re.match(r"every\s+(\d+)\s*(hour|hours|h)\b", v)
    if m:
        return f"every:{m.group(1)}h"
    m = re.match(r"every\s+(\d+)\s*(day|days|d)\b", v)
    if m:
        n = int(m.group(1))
        return "daily" if n == 1 else f"every:{n}d"
    m = re.match(r"every\s+(\d+)\s*(week|weeks|w)\b", v)
    if m:
        n = int(m.group(1))
        return "weekly" if n == 1 else f"every:{n}w"
    m = re.match(r"every\s+(\d+)\s*(month|months|m)\b", v)
    if m:
        return "monthly" if int(m.group(1)) == 1 else f"every:{m.group(1)}m"
    if re.match(r"every\s+(hour|1\s*hour)\b", v):
        return "hourly"
    if re.match(r"every\s+(day|1\s*day)\b", v):
        return "daily"
    if re.match(r"every\s+(week|1\s*week)\b", v):
        return "weekly"
    if re.match(r"every\s+(month|1\s*month)\b", v):
        return "monthly"
    if re.match(r"every\s+(morning|night|evening|afternoon|tonight)\b", v):
        return "daily"  # "every morning" = every day at that time
    if re.search(r"weekday|workday|monday.{0,6}friday", v):
        return "weekdays"
    return ""  # unknown -> treat as once (safe)


def _advance(due: str | None, tm: str | None, repeat: str) -> tuple[str | None, str | None]:
    """One step to the next occurrence of a repeating task."""
    import calendar as _cal

    base = date.fromisoformat(due) if due else _today()
    m = re.fullmatch(r"every:(\d+)h", repeat)
    if repeat == "hourly" or m:
        n = int(m.group(1)) if m else 1
        try:
            dt = datetime.combine(base, datetime.strptime(tm or "00:00", "%H:%M").time())
        except ValueError:
            dt = datetime.combine(base, datetime.min.time())
        dt += timedelta(hours=n)
        return dt.date().isoformat(), dt.strftime("%H:%M")
    if repeat == "weekdays":
        d = base + timedelta(days=1)
        while d.weekday() >= 5:  # skip saturday / sunday
            d += timedelta(days=1)
        return d.isoformat(), tm
    if repeat == "weekly" or (m := re.fullmatch(r"every:(\d+)w", repeat)):
        n = int(m.group(1)) if m else 1
        return (base + timedelta(days=7 * n)).isoformat(), tm
    if repeat == "monthly" or (m := re.fullmatch(r"every:(\d+)m", repeat)):
        n = int(m.group(1)) if m else 1
        y, mo = divmod(base.month - 1 + n, 12)
        y, mo = base.year + y, mo + 1
        return date(y, mo, min(base.day, _cal.monthrange(y, mo)[1])).isoformat(), tm
    m = re.fullmatch(r"every:(\d+)d", repeat)
    if repeat == "daily" or m:
        n = int(m.group(1)) if m else 1
        return (base + timedelta(days=n)).isoformat(), tm
    return due, tm


def _roll_forward(due: str | None, tm: str | None, repeat: str) -> tuple[str | None, str | None]:
    """Advance until the next occurrence is in the future (a reminder missed
    for three days should land on the next real slot, not fire instantly)."""
    now = datetime.now()
    today = now.date()
    hm = now.strftime("%H:%M")
    for _ in range(400):
        due, tm = _advance(due, tm, repeat)
        if not due:
            break
        d = date.fromisoformat(due)
        if d > today or (d == today and (tm or "00:00") > hm):
            break
    return due, tm


def _fmt_due(due: str | None) -> str:
    if not due:
        return "no due date"
    try:
        d = date.fromisoformat(due)
    except ValueError:
        return due
    delta = (d - _today()).days
    if delta == 0:
        return "due today"
    if delta == 1:
        return "due tomorrow"
    if delta < 0:
        return f"due {due} ({-delta} day(s) overdue)"
    return f"due {due} (in {delta} days)"


def _line(row: sqlite3.Row) -> str:
    pri = row["priority"].upper() if row["priority"] != "normal" else "normal"
    head = f"#{row['id']} [{pri}] {row['title']}"
    if row["status"] == "done":
        return f"{head} - DONE ({row['closed_at'][:10]})"
    if row["status"] == "cancelled":
        return f"{head} - CANCELLED ({row['closed_at'][:10]})"
    extra = _fmt_due(row["due"])
    if row["due"] and row["due_time"]:
        extra += f" at {human_time(row['due_time'])}"
    if row["repeat"]:
        extra += f" · repeats {row['repeat']}"
    if row["details"]:
        extra += f" | {row['details']}"
    return f"{head} - {extra}"


def rules_block(user_id: int | None = None) -> str:
    """Standing rules text injected into the system prompt — user's hard
    constraints that the assistant must follow on every reply."""
    if user_id is None:
        try:
            user_id = current_user()
        except Exception:
            user_id = 1
    rows = _conn.execute(
        "SELECT id, text FROM rules WHERE active=1 AND user_id=? ORDER BY id DESC LIMIT 5",
        (user_id,),
    ).fetchall()
    if not rows:
        return ""
    return ("\n\nSTANDING RULES (the user's do-not / always constraints - "
            "enforce them on every reply; never bypass them, and never suggest "
            "changing one unless asked):\n"
            + "\n".join(f"- {r['text']}" for r in rows))


def _find(view: str) -> list[sqlite3.Row]:
    """Current user's pending tasks filtered by view."""
    today = _today().isoformat()
    week = (_today() + timedelta(days=7)).isoformat()
    rows = _conn.execute(
        "SELECT * FROM tasks WHERE status='pending' AND user_id=?", (current_user(),)
    ).fetchall()
    if view == "overdue":
        rows = [r for r in rows if r["due"] and r["due"] < today]
    elif view == "today":
        rows = [r for r in rows if r["due"] == today]
    elif view == "week":
        rows = [r for r in rows if r["due"] and today <= r["due"] <= week]
    elif view == "upcoming":
        rows = [r for r in rows if r["due"] and r["due"] > today]
    elif view == "nodue":
        rows = [r for r in rows if not r["due"]]
    _RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    return sorted(rows, key=lambda r: (r["due"] or "9999-99-99",
                                       _RANK.get(r["priority"], 2)))


def _match(query: str) -> list[sqlite3.Row]:
    """Resolve '#3', '3' or a title fragment against this user's tasks."""
    q = (query or "").strip().lstrip("#")
    if q.isdigit():
        row = _conn.execute(
            "SELECT * FROM tasks WHERE id=? AND user_id=?", (int(q), current_user())
        ).fetchone()
        return [row] if row else []
    return _conn.execute(
        "SELECT * FROM tasks WHERE status='pending' AND user_id=? AND lower(title) LIKE ? "
        "ORDER BY id DESC",
        (current_user(), f"%{q.lower()}%"),
    ).fetchall()


def _one(query: str) -> tuple[sqlite3.Row | None, str]:
    """Exactly one match, or an error message listing the candidates."""
    hits = _match(query)
    if not hits:
        return None, f"No task matches '{query}'. Use list_tasks to see what exists."
    if len(hits) > 1:
        return None, ("Ambiguous, " + str(len(hits)) + " tasks match. Say which one by id: "
                      + ", ".join(f"#{r['id']} {r['title']}" for r in hits[:6]))
    return hits[0], ""


# --------------------------------------------------------------------------
# TOOLS - tasks
# --------------------------------------------------------------------------

@tool
def add_task(title: str, due: str = "", priority: str = "normal", details: str = "",
             repeat: str = "") -> str:
    """Add a to-do task."""
    priority = priority.strip().lower()
    if priority not in PRIORITIES:
        return f"Error: priority must be one of {', '.join(PRIORITIES)}."
    date_part, tm = split_when(due)
    rep = parse_repeat(repeat)
    if date_part.lower().startswith("every "):
        # 'every day at 8am' passed as due: take the rule, keep the time
        rep = rep or parse_repeat(date_part)
        date_part = "today"
    iso = parse_due(date_part)
    if iso and iso[0].isdigit():
        try:
            date.fromisoformat(iso)
        except ValueError:
            return f"Error: '{due}' is not a valid date. Use YYYY-MM-DD, e.g. '2026-11-15'."
    if not tm:
        tm = parse_time(title)  # 'remind me to take pill ... at 2:12 pm'
    if tm and not iso:
        # a bare time means today if it hasn't passed yet, otherwise tomorrow
        iso = (_today() if tm >= datetime.now().strftime("%H:%M")
               else _today() + timedelta(days=1)).isoformat()
    cur = _conn.execute(
        "INSERT INTO tasks (title, details, due, due_time, priority, repeat, "
        "created_at, user_id) VALUES (?,?,?,?,?,?,?,?)",
        (title.strip(), details.strip(), iso, tm, priority, rep or None,
         datetime.now().isoformat(timespec="seconds"), current_user()),
    )
    _conn.commit()
    when = _fmt_due(iso) + (f" at {human_time(tm)}" if tm else "")
    if rep:
        when += f", repeats {rep}"
    return (f"Saved task #{cur.lastrowid}: {title.strip()} "
            f"({when}, priority {priority}).")


@tool
def list_tasks(view: str = "all") -> str:
    """List your tasks."""
    view = view.strip().lower()
    if view in {"done", "cancelled"}:
        rows = _conn.execute(
            "SELECT * FROM tasks WHERE status=? AND user_id=? ORDER BY closed_at DESC LIMIT 20",
            (view, current_user()),
        ).fetchall()
        if not rows:
            return f"No {view} tasks."
        return f"Last {len(rows)} {view} tasks:\n" + "\n".join(f"- {_line(r)}" for r in rows)
    if view not in {"today", "overdue", "week", "upcoming", "nodue", "all"}:
        return "Error: view must be today, overdue, week, upcoming, nodue, all, done or cancelled."
    rows = _find(view)
    if not rows:
        return f"Nothing pending for '{view}'."
    return f"{len(rows)} task(s) - {view}:\n" + "\n".join(f"- {_line(r)}" for r in rows)


@tool
def complete_task(task: str) -> str:
    """Mark a task as done."""
    row, err = _one(task)
    if not row:
        return err
    if row["status"] != "pending":
        return f"Task #{row['id']} is already {row['status']}."
    if row["repeat"]:
        new_due, new_time = _roll_forward(row["due"], row["due_time"], row["repeat"])
        _conn.execute(
            "UPDATE tasks SET due=?, due_time=?, snoozed_until=NULL "
            "WHERE id=? AND user_id=?",
            (new_due, new_time, row["id"], current_user()),
        )
        _conn.commit()
        nxt = f"{new_due or 'no date'}" + (f" at {human_time(new_time)}" if new_time else "")
        return (f"Done: #{row['id']} {row['title']} - repeats ({row['repeat']}), "
                f"next due {nxt}.")
    _conn.execute(
        "UPDATE tasks SET status='done', closed_at=? WHERE id=? AND user_id=?",
        (datetime.now().isoformat(timespec="seconds"), row["id"], current_user()),
    )
    _conn.commit()
    return f"Done: #{row['id']} {row['title']}."


@tool
def cancel_task(task: str, reason: str = "") -> str:
    """Cancel a task the user will NOT do."""
    row, err = _one(task)
    if not row:
        return err
    if row["status"] != "pending":
        return f"Task #{row['id']} is already {row['status']}."
    now = datetime.now().isoformat(timespec="seconds")
    _conn.execute(
        "UPDATE tasks SET status='cancelled', closed_at=? WHERE id=? AND user_id=?",
        (now, row["id"], current_user()),
    )
    if reason.strip():
        _conn.execute(
            "INSERT INTO decisions (text, created_at, user_id) VALUES (?,?,?)",
            (f"Cancelled '{row['title']}': {reason.strip()}", now, current_user()),
        )
    _conn.commit()
    return f"Cancelled #{row['id']} {row['title']}." + (" Reason logged." if reason.strip() else "")


@tool
def snooze_task(task: str, minutes: int = 10) -> str:
    """Push a reminder back by `minutes` (1-1020, i."""
    row, err = _one(task)
    if not row:
        return err
    if row["status"] != "pending":
        return f"Task #{row['id']} is already {row['status']}."
    try:
        mins = max(1, min(int(minutes), 1020))
    except (TypeError, ValueError):
        return "Error: minutes must be a number, e.g. 10."
    until = (datetime.now() + timedelta(minutes=mins)).isoformat(timespec="seconds")
    _conn.execute("UPDATE tasks SET snoozed_until=? WHERE id=? AND user_id=?",
                  (until, row["id"], current_user()))
    _conn.commit()
    return (f"Snoozed #{row['id']} {row['title']} until "
            f"{datetime.fromisoformat(until):%H:%M} ({mins} min from now).")


@tool
def update_task(task: str, due: str = "", priority: str = "", title: str = "",
                details: str = "", repeat: str = "") -> str:
    """Change an existing task (id '#3' or title fragment)."""
    row, err = _one(task)
    if not row:
        return err
    fields, args = [], []
    if due.strip():
        if due.strip().lower() == "none":
            fields += ["due=NULL", "due_time=NULL"]
        else:
            date_part, tm = split_when(due)
            iso = parse_due(date_part)
            try:
                date.fromisoformat(iso)
            except ValueError:
                return f"Error: '{due}' is not a valid date. Use YYYY-MM-DD."
            fields += ["due=?", "due_time=?"]
            args += [iso, tm]
    if repeat.strip():
        fields.append("repeat=?")
        args.append(parse_repeat(repeat) or None)
    if priority.strip():
        p = priority.strip().lower()
        if p not in PRIORITIES:
            return f"Error: priority must be one of {', '.join(PRIORITIES)}."
        fields.append("priority=?")
        args.append(p)
    if title.strip():
        fields.append("title=?")
        args.append(title.strip())
    if details.strip():
        fields.append("details=?")
        args.append(details.strip())
    if not fields:
        return "Error: nothing to change."
    args += [row["id"], current_user()]
    _conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id=? AND user_id=?", args)
    _conn.commit()
    row = _conn.execute("SELECT * FROM tasks WHERE id=?", (row["id"],)).fetchone()
    return f"Updated #{row['id']}: {_line(row)}"


# --------------------------------------------------------------------------
# TOOLS - rules ("what not to do")
# --------------------------------------------------------------------------

@tool
def add_rule(text: str) -> str:
    """Save a standing rule the assistant must always respect, e."""
    src = "agent"
    origin = None
    try:
        from .agent import _UNTRUSTED_SEEN, _UNTRUSTED_ORIGIN
        if _UNTRUSTED_SEEN.get():
            src = "agent:external-content"
            origin = _UNTRUSTED_ORIGIN.get()
    except Exception:
        pass
    cur = _conn.execute(
        "INSERT INTO rules (text, created_at, user_id, source, origin) VALUES (?,?,?,?,?)",
        (text.strip(), datetime.now().isoformat(timespec="seconds"), current_user(), src, origin),
    )
    _conn.commit()
    return f"Rule #{cur.lastrowid} saved: {text.strip()}"


@tool
def list_rules() -> str:
    """List all active rules (the user's standing do-not / always constraints)."""
    rows = _conn.execute(
        "SELECT * FROM rules WHERE active=1 AND user_id=? ORDER BY id", (current_user(),)
    ).fetchall()
    if not rows:
        return "No rules saved yet."
    return "\n".join(f"#{r['id']}: {r['text']}" for r in rows)


@tool
def remove_rule(rule: str) -> str:
    """Deactivate a rule by id ('#2') or text fragment."""
    q = (rule or "").strip().lstrip("#")
    rows = (_conn.execute(
        "SELECT * FROM rules WHERE id=? AND user_id=?", (int(q), current_user())
    ).fetchall()
        if q.isdigit()
        else _conn.execute(
            "SELECT * FROM rules WHERE active=1 AND user_id=? AND lower(text) LIKE ?",
            (current_user(), f"%{q.lower()}%"),
        ).fetchall())
    if not rows:
        return f"No rule matches '{rule}'."
    if len(rows) > 1:
        return "Ambiguous, matches: " + ", ".join(f"#{r['id']}" for r in rows) + ". Use the id."
    _conn.execute("UPDATE rules SET active=0 WHERE id=? AND user_id=?",
                  (rows[0]["id"], current_user()))
    _conn.commit()
    return f"Rule #{rows[0]['id']} removed: {rows[0]['text']}"


# --------------------------------------------------------------------------
# TOOLS - decision log
# --------------------------------------------------------------------------

@tool
def log_decision(text: str) -> str:
    """Record an important choice, promise or 'we decided NOT to ."""
    cur = _conn.execute(
        "INSERT INTO decisions (text, created_at, user_id) VALUES (?,?,?)",
        (text.strip(), datetime.now().isoformat(timespec="seconds"), current_user()),
    )
    _conn.commit()
    return f"Logged as decision #{cur.lastrowid}."


@tool
def list_decisions(limit: int = 10) -> str:
    """Show the most recent decisions / rejections the user logged."""
    rows = _conn.execute(
        "SELECT * FROM decisions WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (current_user(), max(1, min(int(limit), 50))),
    ).fetchall()
    if not rows:
        return "The decision log is empty."
    return "\n".join(f"#{r['id']} [{r['created_at'][:10]}] {r['text']}" for r in rows)


# --------------------------------------------------------------------------
# briefing
# --------------------------------------------------------------------------

@tool
def daily_briefing() -> str:
    """The full daily plan: overdue + due today + upcoming tasks, your rules and
    recent decisions. Use for 'what should I do today', 'give me my briefing'."""
    uid = current_user()
    today = _today()
    iso = today.isoformat()
    rows = _conn.execute(
        "SELECT * FROM tasks WHERE status='pending' AND user_id=?", (uid,)
    ).fetchall()
    overdue = sorted([r for r in rows if r["due"] and r["due"] < iso], key=lambda r: r["due"])
    due_today = sorted([r for r in rows if r["due"] == iso], key=lambda r: r["priority"])
    week = (today + timedelta(days=7)).isoformat()
    soon = sorted([r for r in rows if r["due"] and iso < r["due"] <= week], key=lambda r: r["due"])
    nodue = [r for r in rows if not r["due"]]
    rules = _conn.execute(
        "SELECT * FROM rules WHERE active=1 AND user_id=? ORDER BY id", (uid,)
    ).fetchall()
    decisions = _conn.execute(
        "SELECT * FROM decisions WHERE user_id=? ORDER BY id DESC LIMIT 3", (uid,)
    ).fetchall()
    done_week = _conn.execute(
        "SELECT COUNT(*) c FROM tasks WHERE status='done' AND user_id=? AND closed_at >= ?",
        (uid, (today - timedelta(days=7)).isoformat()),
    ).fetchone()["c"]

    out = [f"Daily briefing - {today:%A, %d %B %Y}"]
    out.append(f"\nOVERDUE ({len(overdue)}):")
    out += [f"  - {_line(r)}" for r in overdue] or ["  none"]
    out.append(f"\nDUE TODAY ({len(due_today)}):")
    out += [f"  - {_line(r)}" for r in due_today] or ["  none"]
    out.append(f"\nNEXT 7 DAYS ({len(soon)}):")
    out += [f"  - {_line(r)}" for r in soon] or ["  none"]
    if nodue:
        out.append(f"\nNO DATE ({len(nodue)}):")
        out += [f"  - {_line(r)}" for r in nodue[:5]]
    out.append(f"\nYOUR RULES ({len(rules)}):")
    out += [f"  - {r['text']}" for r in rules] or ["  none"]
    if decisions:
        out.append("\nRECENT DECISIONS:")
        out += [f"  - {r['text']}" for r in decisions]
    if done_week:
        out.append(f"\nCompleted in the last 7 days: {done_week} task(s).")
    return "\n".join(out)


def log_usage(model: str, prompt_tokens: int = 0, completion_tokens: int = 0,
              latency_ms: int = 0, route: str = "complex", thread_id: str | None = None,
              user_id: int | None = None, status: str = "ok", error: str | None = None) -> None:
    """Record one LLM call's token usage (best-effort, never raises)."""
    try:
        uid = int(user_id) if user_id is not None else current_user()
    except Exception:
        uid = 1
    try:
        _conn.execute(
            "INSERT INTO usage (ts, user_id, model, route, thread_id, "
            "prompt_tokens, completion_tokens, total_tokens, latency_ms, endpoint, "
            "status, error) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), uid, model, route, thread_id,
             int(prompt_tokens or 0), int(completion_tokens or 0),
             int(prompt_tokens or 0) + int(completion_tokens or 0), int(latency_ms or 0),
             "call_model", status, (error[:300] if isinstance(error, str) else None)),
        )
        _conn.commit()
    except sqlite3.Error:
        pass


def latest_usage(thread_id: str | None = None, limit: int = 4) -> list[dict]:
    """Most-recent usage rows (latest first). If thread_id given, only that thread."""
    sql = "SELECT * FROM usage"
    args: tuple = ()
    if thread_id:
        sql += " WHERE thread_id=?"
        args = (thread_id,)
    sql += " ORDER BY id DESC LIMIT ?"
    args = args + (int(limit),)
    rows = _conn.execute(sql, args).fetchall()
    cols = [c[1] for c in _conn.execute("PRAGMA table_info(usage)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]
    cutoff = (datetime.now().date() - timedelta(days=days)).isoformat()
    rows = _conn.execute(
        "SELECT substr(ts,1,10) AS day, model, route, "
        "COUNT(*) n, SUM(prompt_tokens) p, SUM(completion_tokens) c, "
        "SUM(latency_ms) l FROM usage WHERE ts >= ? "
        "GROUP BY day, model, route ORDER BY day DESC, model",
        (cutoff,),
    ).fetchall()
    return [{"day": r["day"], "model": r["model"], "route": r["route"], "calls": r["n"],
             "prompt_tokens": r["p"] or 0, "completion_tokens": r["c"] or 0,
             "latency_ms": r["l"] or 0} for r in rows]


def update_rule_text(rule_id: int, new_text: str, user_id: int | None = None) -> str:
    """UI-only: change a rule's text. Does not go through add_rule provenance."""
    if user_id is None:
        user_id = current_user()
    new_text = new_text.strip()
    if not new_text:
        return "Error: text cannot be empty."
    row = _conn.execute(
        "SELECT text FROM rules WHERE id=? AND user_id=?", (int(rule_id), user_id)
    ).fetchone()
    if not row:
        return f"Error: rule #{rule_id} not found."
    _conn.execute("UPDATE rules SET text=? WHERE id=? AND user_id=?",
                  (new_text, int(rule_id), user_id))
    _conn.commit()
    return f"Updated rule #{rule_id}."


def list_rules_detailed(user_id: int | None = None) -> list[dict]:
    """Rules with metadata, for the Memory page CRUD (UI only)."""
    if user_id is None:
        user_id = current_user()
    rows = _conn.execute(
        "SELECT id, text, active, created_at, source, origin FROM rules "
        "WHERE user_id=? ORDER BY id DESC", (user_id,)
    ).fetchall()
    return [dict(r) for r in rows]



def _redact(text: str) -> str:
    text = (text or "")
    import re as _re
    text = _re.sub(r'(?is)gsk_[A-Za-z0-9_\-]{12,}', 'gsk_<redacted>', text)
    text = _re.sub(r'(?is)sk-[A-Za-z0-9]{16,}', 'sk_<redacted>', text)
    text = _re.sub(r'(?i)(api[_-]?key|password|app\s*password|secret|token|authorization)\s*[:=]\s*"?[^"\s,]+"?',
                  lambda m: m.group(1) + ': <redacted>', text)
    # round obvious coord precision (lat/lon only, displayed again safely in UI)
    text = re.sub(r"(-?\d+\.\d{3,})(?=[^\d])", lambda m: f"{float(m.group(1)):.2f}", text)
    return text[:300]



def round_coord_str(s: str) -> str:
    """Round any 4+ decimal numeric substring to 2 decimals (for UI display)."""
    s = s or ""
    return re.sub(r"(-?\d+\.\d{3,})", lambda m: f"{float(m.group(1)):.2f}", s)


def log_tool_activity(name, args=None, result="", status="ran",
                     thread_id=None, user_id=None) -> None:
    import json
    try:
        uid = int(user_id) if user_id is not None else current_user()
    except Exception:
        uid = 1
    try:
        arg_text = _redact(json.dumps(args or {}, default=str))
        res_text = _redact("" if result is None else str(result))
        _conn.execute(
            "INSERT INTO activity_log (ts, user_id, tool, args, result, status, route) "
            "VALUES (?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), uid, str(name),
             arg_text, res_text, status or "ran", "complex"),
        )
        _conn.commit()
    except sqlite3.Error:
        pass


def list_activity(limit: int = 50, tool=None, status=None, since=None) -> list[dict]:
    sql = "SELECT id, ts, tool, args, result, status, route FROM activity_log WHERE 1=1"
    a = []
    if tool:
        sql += " AND tool=?"; a.append(tool)
    if status:
        sql += " AND status=?"; a.append(status)
    if since:
        sql += " AND ts >= ?"; a.append(since)
    limit = max(1, min(int(limit), 1000))
    sql += " ORDER BY id DESC LIMIT ?"; a.append(limit)
    try:
        return [dict(r) for r in _conn.execute(sql, a).fetchall()]
    except sqlite3.Error:
        return []


def update_rule_text(rule_id, new_text, user_id=None):
    if user_id is None:
        user_id = current_user()
    new_text = (new_text or "").strip()
    if not new_text:
        return "Error: text cannot be empty."
    row = _conn.execute("SELECT text FROM rules WHERE id=? AND user_id=?", (int(rule_id), user_id)).fetchone()
    if not row:
        return f"Error: rule #{rule_id} not found."
    _conn.execute("UPDATE rules SET text=? WHERE id=? AND user_id=?", (new_text, int(rule_id), user_id))
    _conn.commit()
    return f"Updated rule #{rule_id}."


def list_rules_detailed(user_id=None):
    if user_id is None:
        user_id = current_user()
    rows = _conn.execute(
        "SELECT id, text, active, created_at, source, origin FROM rules WHERE user_id=? ORDER BY id DESC",
        (user_id,)).fetchall()
    return [dict(r) for r in rows]



TASK_TOOLS = [
    add_task, list_tasks, complete_task, cancel_task, update_task, snooze_task,
    add_rule, list_rules, remove_rule,
    log_decision, list_decisions, daily_briefing,
]


# One-time startup maintenance: index once, optimize, prune old checkpoints.
try:
    ensure_maintained()
except Exception:
    pass


if __name__ == "__main__":
    print(daily_briefing.invoke({}))

daily_usage = latest_usage
