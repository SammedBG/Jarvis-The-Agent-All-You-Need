"""
app_pages/activity.py - Every tool call the agent made (auditable) PLUS
everything that ran on the fast path. Arguments and results are secret-redacted.
"""
import streamlit as st

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
st.title(":material/receipt_long: Activity log")
st.caption("Every tool call, when it ran, what it got, and why it was approved/declined. "
           "Secrets are redacted before storage.")

from jarvis.tasks import list_activity, round_coord_str
from datetime import date, timedelta

col_tool, col_status, col_range = st.columns([3, 2, 3])
tools_opts = sorted({r["tool"] for r in list_activity(limit=1000)})
tool_filter = col_tool.multiselect("Tool", tools_opts, default=None)
status_filter = col_status.multiselect("Status", ["ran", "approved", "declined", "error"],
                                      default=None)
days_back = col_range.slider("Last N days", 1, 60, 14)
since = (date.today() - timedelta(days=int(days_back))).isoformat()

rows = list_activity(limit=500,
                     tool=(tool_filter[0] if tool_filter and len(tool_filter)==1 else None),
                     status=(status_filter[0] if status_filter and len(status_filter)==1 else None),
                     since=since)

if tool_filter and len(tool_filter) > 1:
    rows = [r for r in rows if r["tool"] in tool_filter]
if status_filter and len(status_filter) > 1:
    rows = [r for r in rows if (r["status"] or "") in status_filter]

st.caption(f"{len(rows)} entries shown.")

if rows:
    for r in rows:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 9])
            c1.markdown(f"**{int(r['id'])}** · {r['ts']}  \n`{r['tool']}`")
            c2.markdown(f"`{r.get('status','ran')}`  \n{r.get('route','')}")
            _a = round_coord_str(str(r.get('args')))
            _b = round_coord_str(str(r.get('result')))
            c3.caption(f"**args:** {_a}\n**result:** {_b}")
else:
    st.info("No activity recorded yet. Tool calls (chat, desktop overlay, wake word) "
            "are logged automatically through the wrapper.")