"""
app_reminders.py - background watcher that pops DESKTOP reminders.

When you say "remind me to take pill today at 2:12 pm" the task keeps a
`due` (date) and a `due_time` (HH:MM). This module starts ONE daemon thread
(once per Streamlit process) that checks every POLL_SECONDS whether any
pending task's time has arrived, and fires a system notification via
notify-send - even if the browser tab is in the background.

The in-app half (toast + warning banner in the open page) lives in ui.py as
a fragment that calls due_now() on a timer.

AGNET_NO_DESKTOP_NOTIFY=1 silences the system popups (used by tests).
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime

from . import app_briefing
from .tasks import DB_PATH

POLL_SECONDS = 15

_LOCK = threading.Lock()
_STARTED = False
_NOTIFIED: set[tuple] = set()  # (id, due, time, snooze) keys already popped


def due_now() -> list[dict]:
    """Pending tasks whose date+time has arrived (including earlier ones the
    user hasn't done yet). Snoozed tasks stay away until their snooze expires.
    Safe to call from any thread / any session."""
    now = datetime.now()
    today = now.date().isoformat()
    hhmm = now.strftime("%H:%M")
    until = now.isoformat(timespec="seconds")
    conn = sqlite3.connect(str(DB_PATH), timeout=3)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, title, due, due_time, snoozed_until FROM tasks "
            "WHERE status='pending' AND due IS NOT NULL AND due_time IS NOT NULL "
            "AND due <= ? AND (due < ? OR due_time <= ?) "
            "AND (snoozed_until IS NULL OR snoozed_until <= ?)",
            (today, today, hhmm, until),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    # all-day tasks (due_time NULL) never come back from the query above
    return sorted((dict(r) for r in rows), key=lambda r: (r["due"], r["due_time"]))


def _key(r: dict) -> tuple:
    """Notification identity: the SAME task fires again after a snooze or a
    roll-forward (new date/time), but never twice for one occurrence."""
    return (r["id"], r["due"], r["due_time"], r.get("snoozed_until") or "")


def mark_done(task_id: int) -> None:
    """Complete from the banner (repeating tasks roll to the next slot)."""
    from .tasks import complete_task

    complete_task.invoke({"task": f"#{int(task_id)}"})


def snooze(task_id: int, minutes: int) -> None:
    from .tasks import snooze_task

    snooze_task.invoke({"task": f"#{int(task_id)}", "minutes": int(minutes)})


def _desktop(title: str, body: str) -> None:
    if os.environ.get("AGNET_NO_DESKTOP_NOTIFY"):
        return
    if sys.platform.startswith("win"):
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast("My Agent", f"{title}\n{body}", duration=5, threaded=True)
            return
        except Exception:
            pass
    if not shutil.which("notify-send"):
        return
    try:
        subprocess.Popen(
            ["notify-send", "--app-name=My Agent", "-u", "normal",
             "\u23f0 " + title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass  # no display / notification daemon - the in-app banner still works


def _speak(text: str) -> None:
    """Speak one short line out loud. Never fatal. Works on Linux and Windows."""
    if os.environ.get("AGNET_NO_VOICE"):
        return
    if app_briefing.get_setting("voice_announcements", "1") != "1":
        return
    # Mark a lock file so wake_word can pause listening while we talk.
    try:
        from .tts import _mark_speaking, _clear_speaking
        _mark_speaking(text)
        clear_after = False  # rely on lock expiry; spd-say dispatches async
    except Exception:
        clear_after = False
    try:
        if sys.platform.startswith("win"):
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.say(text[:140])
                engine.runAndWait()
                return
            except Exception:
                pass
        if shutil.which("spd-say") is None:
            return
        try:
            subprocess.Popen(["spd-say", text[:120]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
    finally:
        if clear_after:
            try:
                from .tts import _clear_speaking
                _clear_speaking()
            except Exception:
                pass


def _loop() -> None:
    while True:
        try:
            for r in due_now():
                k = _key(r)
                if k in _NOTIFIED:
                    continue
                _NOTIFIED.add(k)
                _desktop(r["title"],
                         f"Due {r['due']} at {r['due_time']} - "
                         "open My Agent to mark it done or snooze.")
                _speak(f"Reminder: {r['title'][:80]}, due now.")
            if app_briefing.notify_due():
                _desktop("Morning briefing",
                         "Open My Agent - your agent wrote you a briefing.")
                _speak("Morning briefing ready, sir.")
        except Exception:
            pass  # never let the watcher die (db locked, etc.)
        time.sleep(POLL_SECONDS)


def ensure_watcher() -> None:
    """Start the background thread once per process (idempotent)."""
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
        threading.Thread(target=_loop, daemon=True, name="reminders").start()
