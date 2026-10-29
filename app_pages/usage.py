"""
app_pages/usage.py - token & latency log.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from jarvis.tasks import daily_usage


st.title(":material/insights: Usage")
st.caption("Tokens, latency, and route calls from the jarvis.db usage log. "
           "Per-turn totals reflect the real Groq-reported prompt/completion tokens.")

days = st.slider("Range (days)", 1, 30, 14, key="usage_days")
rows = daily_usage(days)

if not rows:
    st.info("No usage recorded yet. Chat a turn and come back - each LLM call is logged.")
    st.stop()

df = pd.DataFrame(rows)
calls = int(df["calls"].sum())
p = int(df["prompt_tokens"].sum())
c = int(df["completion_tokens"].sum())
st.caption(f"{len(df)} (day, model, route) buckets, {calls} LLM calls, "
           f"{p:,} prompt + {c:,} completion tokens.")
st.subheader("Tokens per day")
daily = (df.groupby("day").agg(p=("prompt_tokens", "sum"), c=("completion_tokens", "sum"),
         calls=("calls", "sum"), lat=("latency_ms", "sum")).reset_index())
st.bar_chart(daily, x="day", y=["p", "c"], height=320)
st.subheader("By model and route")
pivot = (df.groupby(["model", "route"])
           .agg(calls=("calls", "sum"), prompt=("prompt_tokens", "sum"),
                completion=("completion_tokens", "sum")).reset_index())
st.dataframe(pivot, use_container_width=True, hide_index=True)
st.subheader("Recent buckets")
st.dataframe(df, use_container_width=True, hide_index=True)