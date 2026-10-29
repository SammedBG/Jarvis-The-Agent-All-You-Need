"""
app_pages/tasks.py - full task board: filter, edit inline, complete/cancel.
"""
import streamlit as st

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ui_theme import inject_theme
inject_theme(1100)
st.title(":material/checklist: Tasks")

import jarvis.tasks as tasks  # noqa: E402
from jarvis.app_data import bust, tasks_df  # noqa: E402

if flash := st.session_state.pop("task_flash", None):
    st.toast(flash, icon="✅")

VIEWS = {
    "Today": "pending",
    "Overdue": "pending",
    "Next 7 days": "pending",
    "Upcoming": "pending",
    "No date": "pending",
    "All pending": "pending",
    "Done": "done",
    "Cancelled": "cancelled",
}
view = st.segmented_control("View", list(VIEWS), default="All pending", key="task_view")
status = VIEWS[view]
df = tasks_df(status)

# Narrow the view with plain Python (portable, no SQL dialect surprises)
from datetime import date, timedelta  # noqa: E402

today = date.today().isoformat()
week = (date.today() + timedelta(days=7)).isoformat()
if view == "Today":
    df = df[df["due"] == today]
elif view == "Overdue":
    df = df[(df["due"] != "") & (df["due"] < today)]
elif view == "Next 7 days":
    df = df[(df["due"] > today) & (df["due"] <= week)]
elif view == "Upcoming":
    df = df[df["due"] > today]

if df.empty:
    st.info("Nothing here. Add a task below or ask the agent.")
else:
    editable = status == "pending"
    cols = ["id", "title", "due", "priority", "repeat", "details"]
    board = df[cols].copy()
    # one editable cell: "2026-10-27 14:12" (date + optional reminder time)
    board["due"] = (df["due"].fillna("") + " " + df["due_time"].fillna("")).str.strip()
    if editable:
        board["actions"] = [["\U0001F7E2 Done", "\u23F9 Cancel"]] * len(df)

    repeat_opts = sorted(set(tasks.REPEATS) | set(board["repeat"].astype(str)))
    cfg = {
        "id": st.column_config.NumberColumn("ID", width="small", format="%.0f"),
        "title": st.column_config.TextColumn("Task", width="large", required=True),
        "due": st.column_config.TextColumn(
            "Due", width="medium",
            help="Date, optionally with a reminder time: 2026-11-01, friday, "
                 "'today 14:30', 'friday 9:00 am'. Empty = no date."),
        "priority": st.column_config.SelectboxColumn("Priority", options=tasks.PRIORITIES,
                                                     width="small"),
        "repeat": st.column_config.SelectboxColumn(
            "Repeat", options=repeat_opts, width="small",
            help="'' = once. Completing a repeating task rolls it to the next "
                 "occurrence (daily / weekdays / weekly / monthly / hourly)."),
        "details": st.column_config.TextColumn("Details", width="medium"),
    }
    if editable:
        cfg["actions"] = st.column_config.ButtonColumn(
            "Actions", width="small", key="task_action")

    edited = st.data_editor(
        board,
        hide_index=True,
        disabled=["id"] if editable else cols,
        key="task_editor",
        alt="Task board - edit title, due date and priority directly",
        column_config=cfg,
    )

    if editable:
        # Row actions (done / cancel) fired this run?
        click = st.session_state.get("task_action")
        if click is not None and hasattr(click, "row"):
            tid = int(df.iloc[click.row]["id"])
            if "Done" in str(click.label):
                tasks.complete_task.invoke({"task": f"#{tid}"})
            elif "Cancel" in str(click.label):
                tasks.cancel_task.invoke({"task": f"#{tid}",
                                          "reason": "Cancelled from the task board"})
            st.session_state.pop("task_editor", None)  # drop stale cell edits
            bust()
            st.rerun()

        # Persist inline edits
        if not edited[cols[1:]].equals(board[cols[1:]]):
            if st.button("Save changes", type="primary", icon=":material/save:",
                         key="save_task_edits"):
                if (edited["title"].astype(str).str.strip() == "").any():
                    st.error("A task title cannot be empty.")
                else:
                    # split "2026-10-27 14:12" back into date + reminder time
                    parsed = []  # (id, title, due, due_time, priority, repeat, details)
                    bad = None
                    for _, row in edited.iterrows():
                        date_part, tm = tasks.split_when(str(row["due"]).strip())
                        iso = tasks.parse_due(date_part) if date_part else None
                        if iso:
                            try:
                                date.fromisoformat(iso)
                            except ValueError:
                                bad = f"'{date_part}' is not a valid date."
                                break
                        rep = tasks.parse_repeat(str(row.get("repeat") or ""))
                        parsed.append((int(row["id"]), str(row["title"]).strip(),
                                       iso, tm, str(row["priority"]), rep or None,
                                       str(row["details"] or "")))
                    if bad:
                        st.error(bad)
                    else:
                        import sqlite3

                        from jarvis.tasks import DB_PATH, current_user

                        conn = sqlite3.connect(str(DB_PATH), timeout=3)
                        try:
                            for tid, title, iso, tm, pri, rep, det in parsed:
                                conn.execute(
                                    "UPDATE tasks SET title=?, due=?, due_time=?, "
                                    "priority=?, repeat=?, details=? "
                                    "WHERE id=? AND user_id=?",
                                    (title, iso, tm, pri, rep, det, tid, current_user()),
                                )
                            conn.commit()
                        finally:
                            conn.close()
                        st.session_state.pop("task_editor", None)  # edits are now the base
                        bust()
                        st.rerun()

# --- add task -----------------------------------------------------------------
with st.expander("New task", expanded=False):
    with st.form("board_add", clear_on_submit=True):
        a1, a2, a3 = st.columns([4, 2, 2])
        title = a1.text_input("Task", label_visibility="collapsed", placeholder="What needs doing?")
        due = a2.text_input("Due", label_visibility="collapsed",
                            placeholder="today 14:30 / friday / 2026-11-01")
        priority = a3.selectbox("Priority", tasks.PRIORITIES, index=1, label_visibility="collapsed")
        added = st.form_submit_button("Add task", type="primary", icon=":material/add:")
    if added and title.strip():
        msg = tasks.add_task.invoke({"title": title.strip(), "due": due.strip(),
                                     "priority": priority})
        if msg.startswith("Error"):
            st.error(msg)
        else:
            bust()
            st.session_state.task_flash = msg
            st.rerun()
