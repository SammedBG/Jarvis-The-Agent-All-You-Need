"""
ui.py - entry point of the multi-page app.

    streamlit run ui.py
"""
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st
from ui_theme import inject_theme

st.set_page_config(
    page_title="JARVIS",
    page_icon="✳",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

# Background reminder watcher
from jarvis import app_reminders  # noqa: E402

app_reminders.ensure_watcher()

# --------------------------------------------------------------------------
# Navigation (st.navigation renders sidebar menu + runs page)
# --------------------------------------------------------------------------

nav = st.navigation(
    {
        "": [
            st.Page("app_pages/chat.py", title="Chat", icon=":material/chat:", default=True),
            st.Page("app_pages/today.py", title="Today", icon=":material/calendar_today:"),
            st.Page("app_pages/tasks.py", title="Tasks", icon=":material/checklist:"),
            st.Page("app_pages/settings.py", title="Settings", icon=":material/settings:"),
        ],
        "Your data": [
            st.Page("app_pages/memory.py", title="Memory", icon=":material/psychology:"),
            st.Page("app_pages/activity.py", title="Activity", icon=":material/receipt_long:"),
            st.Page("app_pages/documents.py", title="Documents", icon=":material/description:"),
            st.Page("app_pages/usage.py", title="Usage", icon=":material/insights:"),
        ],
    },
    position="sidebar",
)

# --------------------------------------------------------------------------
# sidebar helpers (conversation data lives in jarvis.conversations)
# --------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from jarvis.conversations import recent_conversations, search_conversations  # noqa: E402
    from jarvis.tasks import latest_usage  # noqa: E402
    from jarvis import agent  # noqa: E402
    from jarvis.app_briefing import get_setting, set_setting  # noqa: E402
except Exception as exc:  # log and show a small sidebar warning, never crash
    import logging  # noqa: PLC0415

    logging.getLogger("jarvis.ui").warning("sidebar imports failed: %s", exc)
    recent_conversations = None
    search_conversations = None
    latest_usage = None
    agent = None


_THREAD_RE = re.compile(r"^ui-(\d{8})-(\d{6})$")


def _render_recents(tid: str) -> None:
    """Render recents grouped Today / Yesterday / Earlier via regex on thread id."""
    if not recent_conversations:
        return
    recents = recent_conversations()
    if not recents:
        return
    today = date.today()
    yesterday = today - timedelta(days=1)
    today_r, yesterday_r, earlier_r = [], [], []
    for thread_id, title in recents:
        m = _THREAD_RE.match(thread_id)
        if not m:
            earlier_r.append((thread_id, title))
            continue
        y, mo, d = int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8])
        dt = date(y, mo, d)
        if dt == today:
            today_r.append((thread_id, title))
        elif dt == yesterday:
            yesterday_r.append((thread_id, title))
        else:
            earlier_r.append((thread_id, title))

    def _group(label: str, items: list) -> None:
        if not items:
            return
        st.markdown(f'<div class="side-sub-label">{label}</div>', unsafe_allow_html=True)
        for thread_id, title in items[:5]:
            selected = thread_id == tid
            if st.button(("●  " if selected else "   ") + title,
                         key=f"recent_{thread_id}", width="stretch",
                         type="primary" if selected else "secondary"):
                st.query_params["t"] = thread_id
                st.rerun()

    _group("Today", today_r)
    _group("Yesterday", yesterday_r)
    _group("Earlier", earlier_r)


@st.cache_data(ttl=10)
def _today_token_usage() -> int:
    """Sum of prompt + completion tokens used today, from one SQL query."""
    if latest_usage is None:
        return 0
    try:
        rows = latest_usage(limit=10000)
    except Exception:
        return 0
    today_prefix = date.today().isoformat()
    return sum(
        (r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0)
        for r in rows
        if str(r.get("ts", "")).startswith(today_prefix)
    )


# --------------------------------------------------------------------------
# sidebar chrome
# --------------------------------------------------------------------------

with st.sidebar:
    st.markdown('<div class="side-brand"><span class="spark">✳</span> JARVIS</div>',
                unsafe_allow_html=True)

    if st.button("New chat", icon=":material/add:", width="stretch", key="new_chat"):
        st.query_params["t"] = f"ui-{datetime.now():%Y%m%d-%H%M%S}"
        st.session_state.messages = []
        st.session_state.pending = None
        st.rerun()

    st.markdown('<div class="side-label">Search chats</div>', unsafe_allow_html=True)
    sq = st.text_input("Search conversations", label_visibility="collapsed",
                       placeholder="Search conversations…", key="chat_search_q")
    if sq.strip() and search_conversations:
        hits = search_conversations(sq)
        if hits:
            for h in hits[:8]:
                ht = h["thread_id"]
                if st.button(f"• {h['snippet'][:50]}", key=f"sh_{hash(ht+sq)}",
                             width="stretch"):
                    st.query_params["t"] = ht
                    st.rerun()
        else:
            st.caption("No matches.")

    _render_recents(st.query_params.get("t", "ui-main"))

    st.divider()

    st.markdown('<div class="side-label">Today · Quota</div>', unsafe_allow_html=True)
    _qused = _today_token_usage()
    _qlimit = int(os.getenv("GROQ_DAILY_TOKEN_CAP", "200000"))
    qtxt = "%dk / %dk tokens" % (round(_qused / 1000), round(_qlimit / 1000))
    st.progress(min(1.0, _qused / _qlimit or .001), text=qtxt)

    _MODEL_LABELS = {
        "groq:openai/gpt-oss-120b": "JARVIS 120B",
        "groq:openai/gpt-oss-20b": "JARVIS 20B",
    }
    _model_name = agent.MODEL_NAME if agent else "groq:openai/gpt-oss-20b"
    st.caption(_MODEL_LABELS.get(_model_name, _model_name.split("/")[-1].replace("-", " ").title()))

    if "voice_replies" not in st.session_state:
        st.session_state.voice_replies = get_setting("voice_replies", "0") == "1"

    def _save_voice() -> None:
        set_setting("voice_replies", "1" if st.session_state.voice_replies else "0")

    st.toggle("Read replies aloud", key="voice_replies", on_change=_save_voice,
              help="Speaks every new answer with a neural voice")

    if st.session_state.get("voice_play_pending") or st.session_state.get("voice_playing"):
        if st.button("Stop", key="voice_stop", width="stretch",
                     icon=":material/stop:", help="Cut the currently playing answer."):
            st.html('<script>document.querySelectorAll(".jrvis-audio").forEach(a => { a.pause(); a.currentTime=0; a.src=""; });</script>')
            st.session_state.voice_play_pending = False
            try:
                from jarvis.tts import _clear_speaking
                _clear_speaking()
            except Exception:
                pass
            st.toast("Stopped", icon="🔇")


# --------------------------------------------------------------------------
# reminders fragment
# --------------------------------------------------------------------------

@st.fragment(run_every=15)
def reminder_watch() -> None:
    due = app_reminders.due_now()
    seen = st.session_state.setdefault("reminders_seen", set())
    for r in due:
        k = app_reminders._key(r)
        if k not in seen:
            seen.add(k)
            st.toast(f"{r['title']} - it's time", icon="\U0001F514")
    if due:
        acted = None
        with st.container(border=True):
            st.markdown("**\U0001F514 Due now**")
            for r in due:
                c0, c1, c2, c3 = st.columns([8, 2, 2, 2], vertical_alignment="center")
                c0.markdown(f"{r['title']} &nbsp; `{r['due_time']}`")
                if c1.button("\u2705 Done", key=f"rem_done_{r['id']}",
                             help="Mark done"):
                    app_reminders.mark_done(r["id"])
                    acted = True
                if c2.button("+10 min", key=f"rem_snooze10_{r['id']}",
                             help="Snooze by 10 minutes"):
                    app_reminders.snooze(r["id"], 10)
                    acted = True
                if c3.button("+1 h", key=f"rem_snooze60_{r['id']}",
                             help="Snooze by an hour"):
                    app_reminders.snooze(r["id"], 60)
                    acted = True
        if acted:
            st.cache_data.clear()
            st.rerun()


reminder_watch()

nav.run()
