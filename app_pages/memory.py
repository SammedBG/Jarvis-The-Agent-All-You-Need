"""
app_pages/memory.py - long-term memory manager: facts, rules, decision log.
"""
import html

import streamlit as st

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
st.title(":material/psychology: Memory")

import jarvis.memory as long_memory  # noqa: E402
import jarvis.tasks as tasks  # noqa: E402
from jarvis.app_data import bust, decisions_df, memories_df, rules_df  # noqa: E402

if flash := st.session_state.pop("memory_flash", None):
    st.toast(flash, icon="🧠")

tabs = st.tabs(["Facts (memory)", "Rules (what not to do)", "Decisions"])

tab_facts, tab_rules, tab_decisions = tabs[0], tabs[1], tabs[2]

# -------------------------------------------------------------- FACTS --------
with tab_facts:
    st.caption("Things the agent knows about you. Edit or delete below.")

    qf = st.text_input("Search facts", label_visibility="collapsed",
                       placeholder="Search facts\u2026", key="mem_fact_q")
    with st.form("add_fact", clear_on_submit=True):
        f1, f2 = st.columns([5, 1])
        new_fact = f1.text_input("New fact", label_visibility="collapsed",
                                 placeholder="e.g. I prefer dark mode in every app")
        added = f2.form_submit_button("Remember", type="primary", icon=":material/add:")
    if added and new_fact.strip():
        ok, msg = long_memory.add_fact(new_fact.strip())
        bust()
        if not ok:
            st.warning(msg, icon="⚠️")
        else:
            st.session_state.memory_flash = "Remembered."
            st.rerun()

    facts = long_memory.list_facts_detailed()
    if qf.strip():
        ql = qf.strip().lower()
        facts = [f for f in facts if ql in f["text"].lower()]

    if not facts:
        st.info("Nothing stored yet.")
    else:
        for f in facts:
            with st.container(border=True):
                c1, c2, c3 = st.columns([10, 1, 1])
                c1.markdown(f"**`{f['id']}`** \u2014 {html.escape(f['text'])}")
                c1.caption(f"Source: {f['source']}  \u00b7  created {f['created'] or '?'}"
                           + (f"  \u00b7  from untrusted content: {f['origin'][:60]}" if f.get("origin") else ""))
                # Edit with confirmation-free quick edit
                edit_key = f"fact_edit_{f['id']}"
                if st.session_state.get(edit_key):
                    val = st.text_area("Edit fact", value=f["text"], key=f"fact_editor_{f['id']}", height=60)
                    ec1, ec2 = st.columns(2)
                    if ec1.button("Save", key=f"fact_save_{f['id']}", type="primary"):
                        msg = long_memory.update_fact_text(f["id"], val)
                        bust()
                        st.session_state.memory_flash = msg
                        st.session_state.pop(edit_key, None)
                        st.rerun()
                    if ec2.button("Cancel", key=f"fact_cancel_{f['id']}"):
                        st.session_state.pop(edit_key, None)
                        st.rerun()
                else:
                    if c2.button(":material/edit:", key=f"editfact_{f['id']}", help="Edit"):
                        st.session_state[edit_key] = True
                        st.rerun()
                    if c3.button(":material/delete:", key=f"delfact_{f['id']}", help="Delete"):
                        st.session_state[f"confirm_fact_{f['id']}"] = True
                if st.session_state.get(f"confirm_fact_{f['id']}"):
                    st.warning("Really delete? Cannot undo.")
                    cca, ccb = st.columns(2)
                    if cca.button("Yes, delete", key=f"del_fact_y_{f['id']}", type="primary"):
                        long_memory.delete_fact(f["id"])
                        bust()
                        st.rerun()
                    if ccb.button("Cancel", key=f"del_fact_n_{f['id']}"):
                        del st.session_state[f"confirm_fact_{f['id']}"]
                        st.rerun()

# -------------------------------------------------------------- RULES --------
with tab_rules:
    st.caption("Standing instructions applied to every conversation.")

    qr = st.text_input("Search rules", label_visibility="collapsed", placeholder="Search rules\u2026",
                       key="mem_rule_q")
    with st.form("add_rule", clear_on_submit=True):
        r1, r2 = st.columns([5, 1])
        new_rule = r1.text_input("New rule", label_visibility="collapsed",
                                 placeholder="e.g. never suggest meeting before 9am")
        added = r2.form_submit_button("Add rule", type="primary", icon=":material/add:")
    if added and new_rule.strip():
        from jarvis import tasks
        msg = tasks.add_rule.invoke({"text": new_rule.strip()})
        if msg.startswith("Error"):
            st.error(msg)
        else:
            bust()
            st.session_state.memory_flash = "Rule saved."
            st.rerun()

    rules = tasks.list_rules_detailed()
    if qr.strip():
        ql = qr.strip().lower()
        rules = [r for r in rules if ql in (r["text"] or "").lower()]

    if not rules:
        st.info("No rules yet.")
    else:
        for r in rules:
            with st.container(border=True):
                c1, c2, c3 = st.columns([10, 1, 1])
                c1.markdown(f"**`{int(r['id'])}`** \u2014 {html.escape(str(r['text']))}")
                c1.caption(f"Source: {r.get('source','unknown')} \u00b7 active={int(r.get('active',1))} \u00b7 created {r.get('created_at','?')}"
                           + (f"  \u00b7  from external content: {r['origin'][:60]}" if r.get('origin') else ""))
                edit_key = f"rule_edit_{r['id']}"
                if st.session_state.get(edit_key):
                    val = st.text_area("Edit rule", value=str(r["text"]), key=f"rule_editor_{r['id']}", height=60)
                    ec1, _ = st.columns(2)
                    if ec1.button("Save", key=f"rule_save_{r['id']}", type="primary"):
                        from jarvis import tasks
                        tasks.update_rule_text(int(r["id"]), val)
                        bust()
                        st.session_state.memory_flash = f"Rule #{r['id']} updated."
                        st.session_state.pop(edit_key, None)
                        st.rerun()
                    if st.button("Cancel", key=f"rule_cancel_{r['id']}"):
                        st.session_state.pop(edit_key, None)
                        st.rerun()
                else:
                    if c2.button(":material/edit:", key=f"editrule_{r['id']}", help="Edit"):
                        st.session_state[edit_key] = True
                        st.rerun()
                    if c3.button(":material/delete:", key=f"delrule_{r['id']}", help="Remove rule"):
                        st.session_state[f"confirm_rule_{r['id']}"] = True
                if st.session_state.get(f"confirm_rule_{r['id']}"):
                    st.warning("Remove this rule? Cannot undo.")
                    cca, ccb = st.columns(2)
                    if cca.button("Yes, delete", key=f"del_rule_y_{r['id']}", type="primary"):
                        from jarvis import tasks
                        tasks.remove_rule.invoke({"rule": f"#{int(r['id'])}"})
                        bust()
                        st.rerun()
                    if ccb.button("Cancel", key=f"del_rule_c_{r['id']}"):
                        del st.session_state[f"confirm_rule_{r['id']}"]
                        st.rerun()

# ----------------------------------------------------------- decisions -------
with tab_decisions:
    st.caption("Every commitment the agent recorded: promises, deadlines, purchases.")
    dec = decisions_df(200)
    if dec.empty:
        st.info("No decisions logged yet.")
    else:
        st.dataframe(
            dec.rename(columns={"id": "#", "text": "Decision", "created_at": "When"}),
            hide_index=True,
            alt="Chronological log of recorded decisions",
        )
        st.caption("Decisions are the agent's commitment memory - it checks this "
                   "before acting on anything it promised.")