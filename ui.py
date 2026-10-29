"""
ui.py - entry point of the multi-page app.

    streamlit run ui.py

Navigation only: it sets up the page config, the shared chrome-hiding CSS,
and the sidebar navigation, then runs the selected page from app_pages/.
"""
import os
from datetime import date, datetime, timedelta

import streamlit as st
from ui_theme import inject_theme

st.set_page_config(
    page_title="JARVIS",
    page_icon="✳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Shared theme (one injection)
inject_theme()

# Background reminder watcher
from jarvis import app_briefing  # noqa: E402
from jarvis import app_reminders  # noqa: E402
from jarvis.app_briefing import get_setting, set_setting

app_reminders.ensure_watcher()

# --------------------------------------------------------------------------
# Navigation pages (rendered in sidebar)
# --------------------------------------------------------------------------

NAV_PAGES = [
    st.Page("app_pages/chat.py", title="Chat", icon=":material/chat:", default=True),
    st.Page("app_pages/today.py", title="Today", icon=":material/calendar_today:"),
    st.Page("app_pages/tasks.py", title="Tasks", icon=":material/checklist:"),
    st.Page("app_pages/settings.py", title="Settings", icon=":material/settings:"),
]
NAV_DATA_PAGES = [
    st.Page("app_pages/memory.py", title="Memory", icon=":material/psychology:"),
    st.Page("app_pages/activity.py", title="Activity", icon=":material/receipt_long:"),
    st.Page("app_pages/documents.py", title="Documents", icon=":material/description:"),
    st.Page("app_pages/usage.py", title="Usage", icon=":material/insights:"),
]

nav = st.navigation(
    {
        "": NAV_PAGES,
        "Your data": NAV_DATA_PAGES,
    },
    position="sidebar",
)

# --------------------------------------------------------------------------
# sidebar helpers
# --------------------------------------------------------------------------

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from app_pages.chat import recent_conversations, search_conversations
    from jarvis.tasks import latest_usage
    from jarvis import agent
except Exception:
    recent_conversations = None
    search_conversations = None
    latest_usage = None
    agent = None


def _render_recents(tid: str) -> None:
    """Render recents grouped Today / Yesterday / Earlier."""
    if not recent_conversations:
        return
    recents = recent_conversations()
    if not recents:
        return
    today = date.today()
    yesterday = today - timedelta(days=1)
    today_r, yesterday_r, earlier_r = [], [], []
    for thread_id, title in recents:
        try:
            dt_str = thread_id.split("-")[1] if "-" in thread_id else ""
            dt = datetime.strptime(dt_str, "%Y%m%d-%H%M%S").date()
        except Exception:
            dt = today - timedelta(days=999)
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


# --------------------------------------------------------------------------
# sidebar chrome (renders after nav groups)
# --------------------------------------------------------------------------

with st.sidebar:
    # Brand at top of sidebar chrome
    st.markdown('<div class="side-brand"><span class="spark">✳</span> JARVIS</div>',
                unsafe_allow_html=True)

    # New chat
    if st.button("+ New chat", icon=":material/add:", width="stretch", key="new_chat"):
        st.query_params["t"] = f"ui-{datetime.now():%Y%m%d-%H%M%S}"
        st.session_state.messages = []
        st.session_state.pending = None
        st.rerun()

    # Search chats
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

    # Recents grouped Today / Yesterday / Earlier
    _render_recents(st.query_params.get("t", "ui-main"))

    st.divider()

    # Quota bar
    st.markdown('<div class="side-label">Today · Quota</div>', unsafe_allow_html=True)
    _today_prefix = datetime.now().strftime("%Y-%m-%d")
    _qused = 0
    if latest_usage:
        try:
            _qrows = latest_usage(limit=10000)
            _qrows_today = [r for r in _qrows if str(r.get("ts", "")).startswith(_today_prefix)]
            _qused = sum((r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0)
                          for r in _qrows_today)
        except Exception:
            _qused = 0
    _qlimit = int(os.getenv("GROQ_DAILY_TOKEN_CAP", "200000"))
    qtxt = "%dk / %dk tokens" % (round(_qused / 1000), round(_qlimit / 1000))
    st.progress(min(1.0, _qused / _qlimit or .001), text=qtxt)

    # Friendly model name
    _MODEL_LABELS = {
        "groq:openai/gpt-oss-120b": "JARVIS 120B",
        "groq:openai/gpt-oss-20b": "JARVIS 20B",
    }
    _model_name = agent.MODEL_NAME if agent else "groq:openai/gpt-oss-20b"
    st.caption(_MODEL_LABELS.get(_model_name, _model_name.split("/")[-1].replace("-", " ").title()))

    # Voice toggle
    if "voice_replies" not in st.session_state:
        st.session_state.voice_replies = get_setting("voice_replies", "0") == "1"

    def _save_voice() -> None:
        set_setting("voice_replies", "1" if st.session_state.voice_replies else "0")

    st.toggle("Read replies aloud", key="voice_replies", on_change=_save_voice,
              help="Speaks every new answer with a neural voice")

    # Stop button: only while speech is playing
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
# reminders / briefing fragments
# --------------------------------------------------------------------------

@st.fragment(run_every=15)
def briefing_watch() -> None:
    """Proactive half: ... (skip on Chat home, handled by app_pages/chat.py)"""
    if (st.query_params.get("t", "").startswith("ui-")
            and not (st.session_state.get("messages") or [])):
        return
    text = app_briefing.today_text()
    if text is None and app_briefing.due():
        with st.status("\U0001F305 Writing your morning briefing...") as brief:
            text = app_briefing.generate()
            brief.update(label="\U0001F305 Morning briefing ready", state="complete")
    if text and not st.session_state.get("briefing_hidden"):
        with st.container(border=True):
            h1, h2, h3 = st.columns([9, 1, 1], vertical_alignment="center")
            h1.markdown("**\U0001F305 Morning briefing**")
            if h2.button("\u21bb", key="briefing_regen",
                         help="Write it again (e.g. after a rate limit)"):
                app_briefing.clear_today()
                st.rerun()
            if h3.button("\u2715", key="briefing_hide", help="Hide for today"):
                st.session_state.briefing_hidden = True
                st.rerun()
            st.markdown(text)


@st.fragment(run_every=15)
def reminder_watch() -> None:
    """In-app half: toast + banner for newly-due tasks."""
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
briefing_watch()
