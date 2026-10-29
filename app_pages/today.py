"""
app_pages/today.py - the daily dashboard: KPIs, briefing, quick add, rules.
"""
from datetime import date, time

import streamlit as st

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
st.title(":material/calendar_today: Today")
st.caption(f"{date.today():%A, %d %B %Y}")

import jarvis.tasks as tasks  # noqa: E402
from jarvis.app_data import bust, decisions_df, rules_df, task_counts, tasks_df  # noqa: E402
from jarvis import habits  # noqa: E402

if flash := st.session_state.pop("today_flash", None):
    st.toast(flash, icon="✅")

c = task_counts()

# --- KPI row (wraps on narrow screens) --------------------------------------
with st.container(horizontal=True):
    st.metric("Overdue", c["overdue"], border=True)
    st.metric("Due today", c["today"], border=True)
    st.metric("Next 7 days", c["week"], border=True)
    st.metric("No date", c["nodue"], border=True)
    st.metric("Done (7 days)", c["done_7d"],
              chart_data=c["series"]["done"], chart_type="bar", border=True)

if c["overdue"]:
    st.warning(f"{c['overdue']} task(s) are overdue - clear them first.")

# --- today's tasks with one-click done / cancel ------------------------------
today_df = tasks_df("pending")
today_df = today_df[today_df["due"] == date.today().isoformat()]
if not today_df.empty:
    view = today_df.assign(
        when=today_df["due_time"].fillna(""),
        actions=[["\U0001F7E2 Done", "\u23F9 Cancel"]] * len(today_df),
    )[["title", "when", "priority", "details", "actions"]]
    st.subheader("On your plate today")
    st.dataframe(view, hide_index=True,
                 alt="Tasks due today with times and done/cancel actions",
                 column_config={
                     "when": st.column_config.TextColumn(
                         "Time", width="small", help="Reminder time (empty = all day)"),
                     "actions": st.column_config.ButtonColumn(
                         "Actions", width="small", key="today_action")})
    click = st.session_state.get("today_action")
    if click:
        tid = int(today_df.iloc[click.row]["id"])
        if "Done" in click.label:
            tasks.complete_task.invoke({"task": f"#{tid}"})
        else:
            tasks.cancel_task.invoke({"task": f"#{tid}", "reason": "Cancelled from the Today page"})
        bust()
        st.rerun()

# --- quick add ----------------------------------------------------------------
with st.expander("Quick add a task", expanded=today_df.empty):
    with st.form("quick_add", clear_on_submit=True):
        q1, q2, q3 = st.columns([4, 2, 2])
        title = q1.text_input("Task", label_visibility="collapsed", placeholder="What needs doing?")
        due = q2.text_input("Due", label_visibility="collapsed",
                            placeholder="today 14:30 / friday / 2026-11-01")
        priority = q3.selectbox("Priority", tasks.PRIORITIES, index=1, label_visibility="collapsed")
        added = st.form_submit_button("Add task", type="primary", icon=":material/add:")
    if added and title.strip():
        msg = tasks.add_task.invoke({"title": title.strip(), "due": due.strip(),
                                     "priority": priority})
        if msg.startswith("Error"):
            st.error(msg)
        else:
            bust()
            st.session_state.today_flash = msg
            st.rerun()

# --- briefing + rules + recent decisions -------------------------------------
b1, b2 = st.columns(2)
with b1:
    with st.container(border=True):
        st.markdown("**Daily plan** (raw tool output)")
        st.code(tasks.daily_briefing.invoke({}), language=None)
with b2:
    with st.container(border=True):
        st.markdown("**Your rules**")
        rdf = rules_df()
        if rdf.empty:
            st.caption("No rules yet. Tell the agent: \"never suggest ...\"")
        else:
            st.dataframe(rdf[["id", "text"]], hide_index=True, alt="Active standing rules",
                         column_config={"id": "Rule #"})
    dec = decisions_df(5)
    if not dec.empty:
        with st.container(border=True):
            st.markdown("**Recent decisions**")
            for _, r in dec.iterrows():
                st.caption(f"#{r['id']} · {r['text']}")

# --- habits (daily check-ins) ------------------------------------------------
with st.expander("Habits — check in today", expanded=False):
    h_items = habits.list_habits()
    if not h_items:
        st.caption("No habits yet. Tell JARVIS: 'log habit morning run', "
                    "or type a new one below.")
    else:
        hcols = st.columns(min(3, len(h_items)))
        for idx, h in enumerate(h_items):
            with hcols[idx % len(hcols)]:
                mark = "✅" if h["checked_today"] else "⬜"
                badge = "  🔥" if h["streak"] >= 3 else ""
                st.markdown(f"**{mark} {h['name']}**  \n{h['streak']} d{badge}")
                if not h["checked_today"]:
                    if st.button(f"Log", key=f"loghabit_{h['name']}",
                                 use_container_width=True):
                        res = habits.log_habit(h["name"])
                        st.toast(res)
                        st.rerun()
    newh = st.text_input("New habit", key="newhabit_input",
                          placeholder="e.g. morning run, B12 tablet")
    if newh and st.button("Add habit", key="addhabit_btn"):
        habits.log_habit(newh.strip())
        st.rerun()

# --- morning briefing card (TODAY page; no LLM at page load) ----------------
with st.container(border=True):
    st.markdown("**\U0001F305 Morning briefing**")
    import jarvis.app_briefing as app_briefing  # noqa: E402
    import jarvis.tts as tts  # noqa: E402
    cached = app_briefing.today_text()
    if cached:
        st.markdown(cached)
        pb1, pb2 = st.columns([1, 3])
        if pb1.button("Play", icon=":material/play_arrow:", key="briefing_play", width="stretch",
                      help="Read the briefing aloud"):
            got = tts.speak(cached)
            if got:
                st.markdown(tts.player_html(*got, autoplay=True), unsafe_allow_html=True)
        pb2.caption("Cached for today. Press ↻ on the top-right of any page, "
                    "or “Regenerate\u201d here:")
        if st.button("\u21bb Regenerate briefing", key="briefing_regenerate"):
            app_briefing.clear_today()
            st.rerun()
    elif app_briefing.due():
        st.caption("No briefing written yet — auto-generates at your briefing time, "
                   "or press the button below.")
        if st.button("Generate now", key="briefing_gen_now", type="primary"):
            with st.status("Writing…"):
                text = app_briefing.generate()
            if text:
                got = tts.speak(text)
                if got:
                    st.markdown(tts.player_html(*got, autoplay=True), unsafe_allow_html=True)
            st.rerun()
    else:
        st.caption("Briefing is disabled. Enable it below.")

# --- morning briefing settings -------------------------------------------------
import jarvis.app_briefing as app_briefing  # noqa: E402

with st.expander("\U0001F305 Morning briefing settings", expanded=False):
    st.caption("At this time the agent writes you a short briefing (overdue "
               "items, today's plan with times, one suggestion) and a desktop "
               "notification tells you it's ready.")
    s1, s2, s3 = st.columns([3, 2, 2])
    is_on = app_briefing.enabled()
    try:
        cur_time = time.fromisoformat(app_briefing.briefing_time())
    except ValueError:
        cur_time = time(8, 0)
    bt = s1.time_input("Briefing time", value=cur_time, key="briefing_time_input",
                       disabled=not is_on, label_visibility="collapsed")
    ben = s2.checkbox("Enabled", value=is_on, key="briefing_enabled_input",
                      label_visibility="collapsed")
    if s3.button("Save briefing time", type="primary", icon=":material/save:",
                 key="briefing_save"):
        app_briefing.set_setting(app_briefing.ENABLED_KEY, "1" if ben else "0")
        if ben:
            app_briefing.set_setting(app_briefing.TIME_KEY, bt.strftime("%H:%M"))
        st.toast(f"Morning briefing: {'on at ' + bt.strftime('%H:%M') if ben else 'off'}",
                 icon="\U0001F305")

    a1, a2 = st.columns([3, 1])
    cur_ann = app_briefing.get_setting("voice_announcements", "1") == "1"
    ann = a1.checkbox("Speak reminders & briefing aloud", value=cur_ann,
                      key="voice_announcements_input",
                      help="The watcher speaks each new reminder and the "
                           "morning-briefing nudge out loud (system voice).")
    if ann != cur_ann:
        app_briefing.set_setting("voice_announcements", "1" if ann else "0")
        st.toast(f"Voice announcements: {'on' if ann else 'off'}")
