""" api/e2e_entry.py — backend entrypoint used by the local end-to-end test
harness. It re-exports `app` from api.main but installs a fake agent so no
real Groq key / network is required. It does NOT modify jarvis/agent.py logic."""
from __future__ import annotations

import os
import sys
import time
from collections import deque
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("JARVIS_DB", "/tmp/jarvis_e2e.db")
os.environ.setdefault("AGNET_TASKS_DB", "/tmp/jarvis_e2e.db")
os.environ.setdefault("GROQ_API_KEY", "dummy")

# ensure schema/hash tables etc.
import jarvis.agent as agent_mod  # noqa: E402
import jarvis.tasks as tasks_mod  # noqa: E402
from argon2 import PasswordHasher as _PH  # noqa: E402
tasks_mod._conn
# create auth schema (idempotent)
import api.auth as auth_mod  # noqa: E402
auth_mod._ensure_schema()
# seed one owner so login flows work
try:
    if not tasks_mod._conn.execute("SELECT 1 FROM auth_users WHERE is_owner=1").fetchone():
        tasks_mod._conn.execute(
            "INSERT OR IGNORE INTO auth_users (username, password_hash, created_at, is_owner) VALUES (?,?,?,1)",
            ("owner", _PH().hash("supersecret1234"), "2026-01-01T00:00:00"),
        )
        tasks_mod._conn.commit()
except Exception:
    pass

# ---- fake agent / model ----
def _fake_ask_agent_stream(*args, **kwargs):
    text = kwargs.get("text", "") or (args[0] if args else "") or ""
    thread_id = kwargs.get("thread_id") or (args[1] if len(args) > 1 else "ui-main")
    resume = kwargs.get("resume")
    low = text.lower()
    if resume is not None:
        if resume.get("approved"):
            yield {"type": "delta", "text": "approved reply"}
            yield {"type": "answer", "text": "approved reply"}
        else:
            yield {"type": "delta", "text": "declined reply"}
            yield {"type": "answer", "text": "declined reply"}
        return
    if "slow" in low:
        for i in range(40):
            time.sleep(0.1)
            yield {"type": "delta", "text": "tok "}
        yield {"type": "answer", "text": "done slow"}
        return
    if "run the command" in low:
        yield {"type": "tool_calls", "run_id": "1",
               "calls": [{"name": "run_command", "args": {"command": "ls", "exact command sent": "ls"}}]}
        yield {"type": "tool_result", "name": "run_command", "text": "ok"}
        yield {"type": "pending", "actions": [
            {"name": "run_command", "args": {"command": "ls"}, "why": "risk", "origin": "user"}
        ]}
        return
    if "errortest" in low:
        yield {"type": "delta", "text": "oops "}
        yield {"type": "error", "kind": "error", "message": "Error: raw bogus detail foo bar 429"}
        return
    yield {"type": "delta", "text": "hel"}
    yield {"type": "delta", "text": "lo"}
    yield {"type": "tool_calls", "run_id": "2",
           "calls": [{"name": "get_my_location", "args": {}}]}
    yield {"type": "tool_result", "name": "get_my_location", "text": "Saved location: nowhere (0.0, 0.0)."}
    yield {"type": "delta", "text": " world"}
    yield {"type": "answer", "text": "hello world"}


def _fake_ask_agent(*args, **kwargs):
    thread_id = kwargs.get("thread_id", "ui-main")
    resume = kwargs.get("resume")
    if resume is not None:
        return {"reply": ("approved reply" if resume.get("approved") else "declined"),
                "tools": [], "error": None, "pending": None}
    return {"reply": "hello world", "tools": [], "error": None, "pending": None}


agent_mod.ask_agent = _fake_ask_agent
agent_mod.ask_agent_stream = _fake_ask_agent_stream

# also patch the chat route module-level reference if already loaded
try:
    import api.routes.chat
    api.routes.chat.ask_agent_stream = _fake_ask_agent_stream
except Exception:
    pass

from api.main import app  # noqa: E402
PY