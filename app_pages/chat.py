"""
app_pages/chat.py - Claude-style chat window for your agent, with live streaming.

Part of the multi-page app - run it through the entry point:

    streamlit run ui.py

What's new vs the old version
  - the answer streams in token by token (no frozen spinner)
  - tool calls appear live as a "Thought for N seconds" timeline with steps
  - voice: click the mic, speak, your words are transcribed (Groq Whisper)
  - files: attach a .txt/.md/.pdf - it lands in docs/ and is indexed
  - the look is a real theme now (.streamlit/config.toml), light + dark,
    following your system setting - no custom CSS

Behaviour (unchanged)
  - same agent, tools, memory and approvals as the terminal version
  - risky actions show an Approve / Decline card
  - conversations survive page refresh (the id is kept in the URL: ?t=...)
  - rate-limit messages show the real wait time, with a Retry button
"""
import base64
import html
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Layout-only CSS for the Claude-style look: hide Streamlit's Deploy chrome,
# center the greeting, brand the sidebar wordmark, and keep the chat column
# narrow (the entry point uses the wide layout for the dashboard pages).
from ui_theme import inject_theme
inject_theme(760)

try:
    import jarvis.agent as agent  # builds the graph and opens the memory database (once per process)
except (Exception, SystemExit) as e:  # e.g. missing GROQ_API_KEY raises SystemExit
    st.error(f"Could not start the agent: {e}")
    st.stop()

from jarvis.app_briefing import get_setting, set_setting
from jarvis import app_briefing
from jarvis import app_data
from jarvis.conversations import recent_conversations, search_conversations
from jarvis.tasks import latest_usage
from jarvis.tts import player_html, speak


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def config_for(tid: str) -> dict:
    return {"configurable": {"thread_id": tid}}


def load_history(tid: str) -> list:
    """Rebuild the visible chat from the saved conversation (survives refresh).
    A message of yours that never got an answer (for example a rate-limit error)
    is hidden when you simply sent another message right after it."""
    out = []
    pending_image = None  # a screenshot from the last turn, re-attached below
    try:
        state = agent.graph.get_state(config_for(tid))
        for m in state.values.get("messages", []):
            if m.type == "human":
                out.append({"role": "user", "content": agent.to_text(m.content)})
            elif m.type == "tool":
                text = agent.to_text(m.content).strip()
                if text.startswith("SCREENSHOT:"):
                    pending_image = text.split("\n", 1)[0].split(":", 1)[1].strip()
            elif m.type == "ai" and not getattr(m, "tool_calls", None):
                text = agent.to_text(m.content).strip()
                if text:
                    msg = {"role": "assistant", "content": text, "tools": []}
                    if pending_image:
                        msg["image"] = pending_image
                        pending_image = None
                    out.append(msg)
    except Exception:
        pass
    return [m for i, m in enumerate(out)
            if not (m["role"] == "user" and i + 1 < len(out) and out[i + 1]["role"] == "user")]


@st.cache_data(show_spinner=False)
def conversation_title(thread_id: str, checkpoint_id: str) -> str:
    """First up to 5 words of what you said — short, no-orphan, unique-ish."""
    for m in load_history(thread_id):
        if m["role"] == "user":
            words = m["content"].split()
            text = " ".join(words[:5])
            if len(words) > 5:
                text = text + "…"
            return text[:40] or "(untitled)"
    return ""


def _desktop_confirmation(actions: list[tuple[str, dict]]) -> str:
    """Short spoken line confirming what desktop actions just happened."""
    parts: list[str] = []
    for name, args in actions:
        app = str(args.get("app", "")).strip()
        pct = str(args.get("percent", "")).strip()
        if name == "take_screenshot":
            parts.append("Screenshot taken, sir.")
        elif name == "open_app":
            parts.append(f"Opened {app}, sir." if app else "Opened it, sir.")
        elif name == "close_app":
            parts.append(f"Closed {app}, sir." if app else "Closed it, sir.")
        elif name == "set_volume":
            parts.append(f"Volume set to {pct}, sir." if pct else "Volume set, sir.")
        elif name == "set_brightness":
            parts.append(f"Brightness set to {pct}, sir." if pct else "Brightness set, sir.")
        elif name == "run_command":
            parts.append("Command complete, sir.")
    return " ".join(parts)


def first_name() -> str:
    """A name from long-term memory, if the agent has one ('The user's name is Ravi')."""
    try:
        for _, text in agent.long_memory.list_facts():
            m = re.search(r"\bname is ([A-Z][A-Za-z]{1,20})", text)
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""


def greeting_text() -> str:
    hour = datetime.now().hour
    base = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    name = first_name()
    return f"{base}, {name}" if name else base


def new_chat() -> None:
    st.query_params["t"] = f"ui-{datetime.now():%Y%m%d-%H%M%S}"
    st.rerun()


def transcribe(audio) -> str:
    """Speech -> text using Groq's Whisper endpoint (the key is already in .env)."""
    import requests

    data = audio.getvalue() if hasattr(audio, "getvalue") else audio.read()
    r = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY', '')}"},
        files={"file": ("speech.wav", data, "audio/wav")},
        data={"model": "whisper-large-v3-turbo"},
        timeout=90,
    )
    r.raise_for_status()
    return r.json().get("text", "").strip()


def save_uploads(files) -> list[str]:
    """Copy attached files into docs/ (safe names only). Returns the names."""
    from rag import DOCS_DIR

    DOCS_DIR.mkdir(exist_ok=True)
    names = []
    for f in files:
        name = Path(f.name).name  # no directory parts, ever
        (DOCS_DIR / name).write_bytes(f.getvalue())
        names.append(name)
    return names


# --------------------------------------------------------------------------
# the live turn: stream the answer, show tool calls as a step timeline
# --------------------------------------------------------------------------

_ICON = {
    "calculator": "calculate", "get_current_time": "schedule", "web_search": "language",
    "search_docs": "search", "list_docs": "description", "read_doc": "draft",
    "save_note": "edit_note", "list_notes": "sticky_note_2", "read_note": "sticky_note_2",
    "remember": "psychology", "list_memories": "psychology", "forget": "delete",
    "add_task": "add_task", "list_tasks": "checklist", "complete_task": "task_alt",
    "cancel_task": "cancel", "update_task": "edit", "add_rule": "gavel",
    "list_rules": "gavel", "remove_rule": "gavel", "log_decision": "history",
    "list_decisions": "history", "daily_briefing": "calendar_today",
    "check_email": "mail", "log_habit": "add_task", "list_habits": "checklist",
    "habit_streak": "local_fire_department", "delete_habit": "delete", "system_status": "monitor_heart",
    "open_app": "rocket_launch", "close_app": "close", "set_volume": "volume_up",
    "set_brightness": "brightness_medium", "take_screenshot": "screenshot",
    "find_places": "place", "get_my_location": "my_location", "save_location": "save_alt",
    "run_command": "terminal",
}

# desktop tools whose execution gets a spoken confirmation (JARVIS-style)
_DESKTOP_TOOLS = {"take_screenshot", "open_app", "close_app",
                  "set_volume", "set_brightness", "run_command"}

_TYPING = '<span class="typing-spark">✳</span>'  # pulsing spark (see CSS above)


def stream_assistant(tid: str, prompt: str | None = None, resume: dict | None = None) -> None:
    """Run one agent turn inside an assistant chat bubble, rendering tool steps
    live and streaming the answer text as it arrives."""
    started = time.time()
    buf = ""            # text of the current model call (preamble may be discarded)
    steps: list[str] = []
    final = ""
    pending = None
    error = None
    shot: str | None = None  # screenshot path to keep visible after the rerun
    desktop_actions: list[tuple[str, dict]] = []  # (tool name, args) for spoken confirmations

    with st.chat_message("assistant", avatar="✳"):
        answer_slot = st.empty()  # created first, so the answer sits below the timeline
        answer_slot.markdown(_TYPING, unsafe_allow_html=True)  # pulsing spark until text arrives
        state_slot = st.empty()   # idle/listening/thinking/speaking badge
        state_slot.caption("JARVIS is thinking\u2026")
        with st.status(":shimmer[Thinking]", type="compact") as think:
            open_steps: list = []  # step statuses waiting for their tool result
            for ev in agent.ask_agent_stream(prompt or "", tid, resume=resume):
                kind = ev["type"]
                if kind == "delta":
                    buf += ev["text"]
                    if buf:
                        answer_slot.markdown(buf)  # first token replaces the spark
                elif kind == "discard":  # that text was tool-call preamble, not an answer
                    buf = ""
                    answer_slot.markdown(_TYPING, unsafe_allow_html=True)  # still working
                    state_slot.caption("JARVIS is thinking\u2026")
                elif kind == "tool_calls":
                    for call in ev["calls"]:
                        name = call["name"]
                        steps.append(f"{name}({call['args']})")
                        if (not ev.get("fast")) and name in _DESKTOP_TOOLS:
                            desktop_actions.append((name, call.get("args") or {}))
                        icon = _ICON.get(name, "settings")
                        step = st.status(f":material/{icon}: {name}", type="step")
                        arg_preview = ", ".join(f"{k}={v!r}" for k, v in call["args"].items())
                        if arg_preview:
                            step.caption(arg_preview[:300])
                        open_steps.append(step)
                    state_slot.caption("JARVIS is thinking\u2026 running tools.")
                elif kind == "tool_result":
                    step = open_steps.pop(0) if open_steps else None
                    text = (ev["text"] or "").strip()
                    if step is not None:
                        if text.startswith("SCREENSHOT:"):
                            line, _, rest = text.partition("\n")
                            path = line.split(":", 1)[1].strip()
                            shot = path  # kept in the message so it survives the rerun
                            try:
                                step.image(path, caption=rest.strip() or None)
                            except Exception:
                                step.text(text)
                        elif text:
                            step.code(text)
                        step.update(state="complete")
                elif kind == "answer":
                    final = ev["text"]
                    buf = final
                    answer_slot.markdown(final)
                    state_slot.caption("JARVIS is speaking\u2026")
                elif kind == "pending":
                    pending = ev["actions"]
                    state_slot.caption("JARVIS is waiting for your approval.")
                elif kind == "error":
                    error = ev
                    state_slot.caption("JARVIS stopped.")
            for step in open_steps:  # safety: never leave a step spinning
                step.update(state="complete")
            secs = int(time.time() - started)
            if pending:
                think.update(label="Waiting for your approval", state="complete")
            elif error:
                think.update(label="Stopped", state="error")
            elif final or buf:
                think.update(label=f"Thought for {secs} second{'s' if secs != 1 else ''}",
                             state="complete")
            else:
                think.update(label="Done", state="complete")
        if not (final or buf):
            answer_slot.empty()  # never leave the typing spark behind (error/pending)
            state_slot.empty()

        if error:
            kind = error.get("kind")
            if kind == "rate_limit":
                st.warning(error["message"])
            else:
                # never surface raw API errors in chat; log to activity page
                try:
                    from jarvis.tasks import log_tool_activity
                    log_tool_activity("chat", {"turn": "error", "kind": kind},
                                      error.get("message", str(error)), status="error")
                except Exception:
                    pass
                st.error("Something went wrong. Retry")
        if steps:
            with st.expander(f"Tools used ({len(steps)})"):
                for s in steps:
                    st.code(s)

    if pending:
        st.session_state.messages.append(
            {"role": "assistant", "content": "*(waiting for your approval)*", "tools": steps})
        st.session_state.pending = pending
        st.session_state.pending_tools = steps
    else:
        if error:
            content = error["message"]  # show the real reason (e.g. rate limit + wait time)
        else:
            content = final or buf or "(no reply)"
        msg = {"role": "assistant", "content": content,
               "tools": steps, "error": error.get("kind") if error else None,
               "image": shot}
        # usage chip: pull this turn's token numbers from the log
        try:
            rows = latest_usage(thread_id=tid)
            if rows and not error:
                msg["usage"] = {
                    "route": rows[0].get("route", "") or "",
                    "prompt": sum(int(r.get("prompt_tokens") or 0) for r in rows),
                    "completion": sum(int(r.get("completion_tokens") or 0) for r in rows),
                    "latency_ms": sum(int(r.get("latency_ms") or 0) for r in rows),
                    "calls": len(rows),
                }
        except Exception:
            pass
        if not error and st.session_state.get("voice_replies"):
            # synth now, play after this turn's st.rerun() (see the history loop)
            confirmation = _desktop_confirmation(desktop_actions)
            spoken = content + (" " + confirmation if confirmation else "")
            try:
                audio = speak(spoken)
            except Exception:
                audio = None
            if audio:
                msg["audio"] = base64.b64encode(audio[0]).decode("ascii")
                msg["audio_fmt"] = audio[1]
                st.session_state.voice_play_pending = True
        st.session_state.messages.append(msg)


# --------------------------------------------------------------------------
# page state: which conversation are we in?
# --------------------------------------------------------------------------

tid = st.query_params.get("t", "ui-main")
if st.session_state.get("tid") != tid:
    st.session_state.tid = tid
    st.session_state.messages = load_history(tid)
    waiting = agent.get_pending(config_for(tid))  # an approval left open earlier
    st.session_state.pending = waiting.get("actions") if waiting else None
    st.session_state.pending_tools = []

# --------------------------------------------------------------------------
# attachments: save files into docs/, transcribe voice
# --------------------------------------------------------------------------


def process_attachments(files, audio) -> tuple[str, str]:
    """Returns (words_to_append, files_note). Shows its own step timeline."""
    words, note = "", ""
    if files:
        with st.status("Saving your documents", type="step") as s:
            try:
                names = save_uploads(files)
                st.caption(f"Added to docs/: {', '.join(names)}")
                from rag import build_index

                stats = build_index()
                st.caption(f"Indexed into {stats['chunks']} chunks - ask me about them.")
                note = f"(The user also added {', '.join(names)} to your documents.)"
            except Exception as e:
                st.error(f"Could not save/index the file: {e}")
                s.update(state="error")
    if audio is not None:
        with st.status("Transcribing your voice", type="step") as s:
            try:
                said = transcribe(audio)
                s.update(label="Transcribed", state="complete")
                st.caption(f"🎤 {said}")
                words = said
            except Exception as e:
                s.update(label="Transcription failed", state="error")
                st.error(f"Voice input failed: {e}")
    return words, note


# --------------------------------------------------------------------------
# daily briefing card on chat home (placement: below greeting, above composer)
# --------------------------------------------------------------------------


def _task_rows_for_section(kind: str) -> list[dict]:
    """Return pending tasks for one of overdue/today/week (no LLM)."""
    from datetime import date, timedelta
    try:
        df = app_data.tasks_df("pending")
    except Exception:
        return []
    if df is None or df.empty:
        return []
    today_iso = date.today().isoformat()
    week_end = (date.today() + timedelta(days=7)).isoformat()
    rows = []
    for _, r in df.iterrows():
        due = str(r.get("due") or "")
        if kind == "overdue" and due and due < today_iso:
            ok = True
        elif kind == "today" and due == today_iso:
            ok = True
        elif kind == "week" and due and today_iso < due <= week_end:
            ok = True
        else:
            ok = False
        if ok:
            rows.append(r.to_dict())
    return rows


def _short_priority_dot(priority: str) -> str:
    p = (priority or "").lower()
    if p in ("high", "urgent"):
        return '<span style="color:#ef4444;font-size:.65rem;">&#9679;</span> '
    return ""


def _mark_task_done(tid_task: int) -> bool:
    try:
        from jarvis import app_reminders
        app_reminders.mark_done(tid_task)
    except Exception:
        pass
    try:
        # tasks.complete_task canonical tool
        import jarvis.tasks as tasks_mod
        tasks_mod.complete_task.invoke({"id": tid_task})
    except Exception:
        return False
    app_data.bust()
    return True


def _snooze_task(tid_task: int, mins: int) -> None:
    from datetime import timedelta, datetime as _dt
    try:
        from jarvis import app_reminders
        app_reminders.snooze(tid_task, mins)
    except Exception:
        pass
    try:
        import jarvis.tasks as tasks_mod
        # interpret as a due_time nudge
        tasks_mod.snooze_task.invoke({"id": tid_task, "minutes": mins}) if hasattr(tasks_mod, "snooze_task") else None
    except Exception:
        pass
    app_data.bust()


def render_chat_daily_briefing() -> None:
    """Render the Daily briefing card on the Chat home (below greeting, above
    composer). Collapsed by default, cached tools only, no auto LLM call."""
    try:
        counts = app_data.task_counts()
    except Exception:
        counts = {"today": 0, "overdue": 0, "done_7d": 0}
    today_n = int(counts.get("today", 0) or 0)
    overdue_n = int(counts.get("overdue", 0) or 0)
    done7 = int(counts.get("done_7d", 0) or 0)

    dismissed = app_briefing.get_setting("briefing_dismissed_date", "")
    if dismissed == str(__import__("datetime").date.today()):
        return  # dismissed for today

    with st.container(border=True):
        st.markdown("**Daily briefing**")
        hc1, hc2, hc3, hc4 = st.columns([3, 1.6, 1.6, 1.8], vertical_alignment="center")
        HC_DATE = datetime.now().strftime("%A, %d %b").replace(" 0", " ")
        hc1.caption(HC_DATE)
        hc1.caption(f"{today_n} due today \u00b7 {overdue_n} overdue")

        # action: play spoken 2-3 sentence version (does not read full text)
        def _play():
            parts = [greeting_text()]
            parts.append(f"You have {today_n} task{'s' if today_n != 1 else ''} due today")
            if overdue_n:
                parts.append(f"and {overdue_n} overdue")
            parts.append("Check the Today page for full details.")
            try:
                try:
                    from jarvis.tts import speak
                    audio = speak(". ".join(parts))
                except Exception:
                    audio = None
                if audio:
                    st.session_state.voice_play_pending = True
                    import base64
                    st.session_state["_briefing_audio"] = base64.b64encode(audio[0]).decode("ascii")
                    st.session_state["_briefing_audio_fmt"] = audio[1]
            except Exception:
                pass
            from jarvis.tts import player_html
            pass
        if hc2.button("Play briefing \U0001F50A", help="Read short spoken briefing",
                     width="stretch"):
            _play()
            st.rerun()
        if hc3.button("Refresh", help="Rebuild briefing from current data",
                     width="stretch"):
            try:
                app_briefing.clear_today()
                text = app_briefing.generate()
                st.toast("Briefing refreshed" if text else "Failed", icon="\U0001F305")
            except Exception as e:
                st.error("Could not rebuild the briefing. Retry")  # never raw error
            st.cache_data.clear()
            st.rerun()
        if hc4.button("Dismiss for today", help="Hide until tomorrow",
                     width="stretch"):
            from datetime import date as _d
            app_briefing.set_setting("briefing_dismissed_date", _d.today().isoformat())
            st.rerun()

        # audio player for short briefing
        _ba = st.session_state.get("_briefing_audio")
        if _ba:
            st.markdown(
                player_html(base64.b64decode(_ba),
                            st.session_state.get("_briefing_audio_fmt", "wav"), autoplay=True),
                unsafe_allow_html=True)

        # collapsed by default showing only the summary line above
        with st.expander("", expanded=False):
            # sections only if non-empty
            ov = _task_rows_for_section("overdue")
            td = _task_rows_for_section("today")
            wk = _task_rows_for_section("week")
            if not (ov or td or wk):
                st.caption("Nothing due today")  # friendly one-liner + auto-collapse
                if True:
                    pass
            if ov:
                st.markdown("**Overdue**")
                for r in ov:
                    _task_row(r)
            if td:
                st.markdown("**Due today**")
                for r in td:
                    _task_row(r)
            if wk:
                st.markdown("**Next 7 days**")
                for r in wk:
                    _task_row(r)
            if done7 > 0:
                st.caption(f"Completed in the last 7 days: {done7}")


def _task_row(r: dict) -> None:
    """One task row: checkbox (marks done), title, time, snooze menu."""
    cbox, titlecol, timecol, snz = st.columns([0.6, 5, 2, 2.2], vertical_alignment="center")
    dot = _short_priority_dot(r.get("priority", "")) if False else _short_priority_dot(r.get("priority", ""))
    rid = int(r.get("id", 0) or 0)
    done = cbox.checkbox("done", key=f"dbc_done_{rid}", value=False, label_visibility="collapsed")
    if done:
        _mark_task_done(rid)
        st.rerun()
    title = str(r.get("title", "")).replace("[normal]", "").strip()
    titlecol.markdown(f"{dot}{title}", unsafe_allow_html=True)
    ttime = r.get("due_time") or r.get("due") or ""
    timecol.caption(ttime if str(ttime).strip() else "anytime")
    opt = snz.selectbox("snooze", ["Snooze", "15 min" , "1 hour", "tomorrow"],
                        key=f"dbc_snz_{rid}", label_visibility="collapsed")
    if opt == "15 min":
        _snooze_task(rid, 15); st.rerun()
    elif opt == "1 hour":
        _snooze_task(rid, 60); st.rerun()
    elif opt == "tomorrow":
        _snooze_task(rid, 24 * 60); st.rerun()


# --------------------------------------------------------------------------
# empty chat: Claude-style greeting + input card in the middle of the page
# --------------------------------------------------------------------------

home = not st.session_state.messages and not st.session_state.pending
prompt = None

if home:
    if st.session_state.pop("home_reset", False):  # clear last turn's input before widgets appear
        for k in ("home_msg", "home_files", "home_audio"):
            st.session_state.pop(k, None)
    st.markdown(
        f'<div class="home-title"><span class="spark">✳</span> {html.escape(greeting_text())}</div>',
        unsafe_allow_html=True)
    # greeting first, daily briefing card below (collapsed by default), above composer
    render_chat_daily_briefing()
    with st.container(border=True):
        c1, c2, c3 = st.columns([0.7, 9, 1], vertical_alignment="center")
        if c1.button("", icon=":material/add:", key="home_attach", width="stretch",
                     help="Attach documents or dictate"):
            st.session_state.show_attach = not st.session_state.get("show_attach", False)
        c2.text_input("Message", label_visibility="collapsed",
                      placeholder="How can I help you today?", key="home_msg",
                      on_change=lambda: st.session_state.update(home_go=True))
        clicked = c3.button("", icon=":material/arrow_upward:", type="primary",
                            key="home_send", width="stretch")
        if st.session_state.get("show_attach"):
            st.file_uploader("Documents", label_visibility="collapsed",
                             accept_multiple_files=True, type=["txt", "md", "pdf"],
                             key="home_files")
            st.caption("Tip: attach any file above, then press send \u2014 the mic below "
                       "always works.")
        st.audio_input("🎤 Speak to JARVIS  (records \u2192 transcribes into your message)",
                       label_visibility="visible", width="stretch", key="home_audio")
        st.caption("Voice notes: record, then tap Send (Enter) above \u2014 JARVIS speaks "
                   "the reply back if 'Read replies aloud' is on.")
    st.markdown('<div class="home-hint">Enter to send · + to attach · talk or type</div>',
                unsafe_allow_html=True)

    chips = ["Plan my day", "Nearest veg restaurant nearby",
             "Add a task", "What can you do?"]
    def _chip_click(val: str) -> None:
        st.session_state.home_msg = val
        st.session_state.home_go = True
    sc = st.columns(4)
    for ci, chip in enumerate(chips):
        with sc[ci]:
            st.button(chip, key=f"chip_{ci}", width="stretch",
                     on_click=_chip_click, args=(chip,))
    if (clicked or st.session_state.pop("home_go", False)) and not prompt:
        text = (st.session_state.get("home_msg") or "").strip()
        spoken, files_note = process_attachments(
            st.session_state.get("home_files") or [], st.session_state.get("home_audio"))
        text = f"{text} {spoken}".strip()
        if text:
            prompt = text
        elif files_note:
            prompt = f"[documents attached only] {files_note}"
        if prompt:
            st.session_state.home_reset = True

# --------------------------------------------------------------------------
# chat history
# --------------------------------------------------------------------------

# The newest spoken answer autoplays exactly once (right after the turn's
# st.rerun(), while the user's interaction already unlocked audio playback);
# older players stay manual so every rerun doesn't blast them again.
_audio_idx = [i for i, m in enumerate(st.session_state.messages) if m.get("audio")]
_autoplay_idx = (_audio_idx[-1]
                 if _audio_idx and st.session_state.pop("voice_play_pending", False)
                 else None)

for i, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"], avatar="✳" if m["role"] == "assistant" else None):
        if m.get("error") == "rate_limit":
            st.warning(m["content"])
        else:
            if m["role"] == "user":
                st.markdown(f'<div class="user-bubble">{m["content"]}</div>',
                            unsafe_allow_html=True)
            else:
                st.markdown(m["content"])
        u = m.get("usage")
        if u:
            rt = u.get("route","") or "-"
            p = int(u.get("prompt") or 0)
            c = int(u.get("completion") or 0)
            lat = int(u.get("latency_ms") or 0)
            calls = int(u.get("calls") or 1)
            chips = [f"`{rt}`", f"{p}+{c} tok", f"{lat}ms"]
            if calls > 1: chips.append(f"{calls} calls")
            st.caption(" \u00b7 ".join(chips))
        if m.get("image"):
            try:
                st.image(m["image"])
            except Exception:
                st.caption(f"(screenshot: {m['image']} - file missing)")
        if m.get("audio"):
            st.markdown(player_html(base64.b64decode(m["audio"]),
                                    m.get("audio_fmt", "wav"),
                                    autoplay=(i == _autoplay_idx)),
                        unsafe_allow_html=True)
        if m.get("tools"):
            with st.expander(f"Tools used ({len(m['tools'])})"):
                for t in m["tools"]:
                    st.code(t)

# --------------------------------------------------------------------------
# approval card
# --------------------------------------------------------------------------

if st.session_state.pending:
    st.markdown('<div class="approve-card">', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("#### I need your approval first")
        for a in st.session_state.pending:
            st.markdown(f"**{a['name']}**")
            st.code(str(a["args"]))
            st.caption(f"Reason: {a['why']}")
            if a.get("origin"):
                st.caption(f"*Source of request:* `{a['origin']}`")
        st.caption(":warning: Nothing will run until you click **Approve**.")
        feedback = st.text_input("If you decline, tell me what to change (optional)",
                                 key="feedback")
        col1, col2 = st.columns(2)
        approve = col1.button("Approve", type="primary", key="approve")
        decline = col2.button("Decline", key="decline")

    st.markdown('</div>', unsafe_allow_html=True)

    if approve or decline:
        if decline:
            try:
                from jarvis.tasks import log_tool_activity
                for a in st.session_state.pending or []:
                    log_tool_activity(a["name"], a.get("args"), "User declined.", status="declined")
            except Exception:
                pass
        decision = {"approved": True} if approve else {"approved": False, "feedback": feedback.strip()}
        st.session_state.pending = None
        st.session_state.messages = [m for m in st.session_state.messages
                                     if m.get("content") != "*(waiting for your approval)*"]
        with st.spinner("Working..."):
            stream_assistant(tid, resume=decision)
        st.rerun()

# --------------------------------------------------------------------------
# message box (only once the conversation has started)
# --------------------------------------------------------------------------

# After a rate limit: one click re-sends the message that failed
retry_text = None
msgs = st.session_state.messages
if (not st.session_state.pending and len(msgs) >= 2 and msgs[-1].get("error") is not None
        and msgs[-2]["role"] == "user"):
    if st.button("Retry my last message", icon=":material/replay:", key="retry"):
        retry_text = msgs[-2]["content"]
        st.session_state.messages = msgs[:-2]

prompt = prompt or retry_text
files_note = ""
# mic hint is kept inside the composer (st.audio_input label), not after the conversation.
if not home:
    submission = st.chat_input(
        "How can I help you today?",
        accept_file=True,
        file_type=["txt", "md", "pdf"],
        accept_audio=True,
        submit_mode="stop",
        disabled=bool(st.session_state.pending),
    )
    if submission is not None:
        text = submission if isinstance(submission, str) else (submission.text or "").strip()
        files = [] if isinstance(submission, str) else list(submission.files or [])
        audio = None if isinstance(submission, str) else submission.audio
        spoken, files_note = process_attachments(files, audio)
        text = f"{text} {spoken}".strip()
        if text:
            prompt = text
        elif files_note:
            prompt = f"[documents attached only] {files_note}"

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(f'<div class="user-bubble">{prompt}</div>', unsafe_allow_html=True)
    stream_assistant(tid, prompt=prompt)
    st.rerun()
