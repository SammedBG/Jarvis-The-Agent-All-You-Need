"""
app_pages/settings.py - settings that do NOT touch the .env file.

Models, daily token cap, voice, wake word, fast-path aliases only (no API keys).
API keys are never displayed here; only whether they're present is shown.
"""
import os, json
import streamlit as st

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
st.title(":material/settings: Settings")
st.caption("Tuning for JARVIS's brain. None of these read or write API keys.")

import jarvis.app_briefing as ab  # noqa: E402
from jarvis.app_briefing import get_setting, set_setting  # noqa: E402
import jarvis.desktop as desktop  # noqa: E402


# ---- Models / quota -------------------------------------------------------
with st.container(border=True):
    st.subheader("Models")
    st.caption("Env vars MODEL_COMPLEX/MODEL_SIMPLE override these on next boot; you may need to restart.")
    mc = st.text_input("Complex model", value=ab.get_setting("model_complex", "groq:openai/gpt-oss-120b"),
                       key="set_model_complex", help="used for planning/analysis")
    ms = st.text_input("Simple model", value=ab.get_setting("model_simple", "groq:openai/gpt-oss-20b"),
                       key="set_model_simple", help="used for quick chat/tool turns")
    cap = st.number_input("Daily token limit (Groq on-demand TPD)", min_value=1000, step=1000,
                          value=int(ab.get_setting("groq_daily_token_cap", "200000")),
                          key="set_daily_cap")
    st.caption("80% of this limit triggers the cheaper-model tier automatically.")

# ---- Voice ---------------------------------------------------------------
with st.container(border=True):
    st.subheader("Voice")
    cur_voice = ab.get_setting("voice_replies", "0") == "1"  # controlled by sidebar toggle (single ownership)
    v = cur_voice
    cur_ann = ab.get_setting("voice_announcements", "1") == "1"
    a = st.checkbox("Speak reminders & briefing aloud (system)", value=cur_ann, key="set_voice_announce")
    cur_wake = ab.get_setting("wake_word_enabled", "1") == "1"
    w = st.checkbox("Wake word active", value=cur_wake, key="set_wake_word")

# ---- fast path aliases ---------------------------------------------------
# USER-EDITABLE ONLY HERE: no agent tools exist for this; agent.get_aliases() reads it.
with st.container(border=True):
    st.subheader("Fast-path alias whitelist (editable)")
    st.caption("One entry per line:  `alias -> spec`  or  `alias = spec`. "
               "Specs are app names on PATH, desktop launchers, or full https URLs.\n"
               "These are NOT reachable through any agent tool \u2014 only this page edits them.")
    current_aliases = ab.get_setting("fast_path_aliases", "")
    if current_aliases and not current_aliases.strip():
        current_aliases = ""
    alias_text = st.text_area("Aliases",
                               value=current_aliases,
                               height=240, key="set_fast_path_aliases",
                               help="Example:\n"
                                    "  browser -> chrome.exe\n"
                                    "  whatsapp -> https://web.whatsapp.com\n"
                                    "  coolapp -> /usr/bin/coolapp")

    # live preview (no side effects)
    if alias_text.strip():
        try:
            from jarvis.desktop import _APP_ALIASES as BASE_ALIASES  # noqa: E402
            preview = 0
            for line in alias_text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "->" in line:
                    k, _, v = line.partition("->")
                elif "=" in line:
                    k, _, v = line.partition("=")
                else:
                    k, v = "", ""
                if k.strip() and v.strip():
                    preview += 1
            st.caption(f"Preview: {preview} override entries (base table loaded too, "
                       f"base entries: {len(BASE_ALIASES)})")
        except Exception as e:
            st.caption(f"Preview error: {e}")

# ---- save ---------------------------------------------------------------
# ---- Location (for "find nearby") ----------------------------------------
with st.container(border=True):
    st.subheader("Home location (for 'find nearby places')")
    cur_loc_raw = ab.get_setting("home_location", "")
    try:
        cur_loc = json.loads(cur_loc_raw) if cur_loc_raw else None
    except Exception:
        cur_loc = None
    if cur_loc:
        st.caption(f"Saved: {cur_loc.get('label')} ({round(cur_loc['lat'],2)}, "
                   f"{round(cur_loc['lon'],2)})")
    else:
        st.caption("No location saved — set one below.")
    st.caption("Tip: on a phone or PC with a GPS, copy your lat/lon from any map "
               "into the label field as 'label, lat, lon'.")
    loc_label = st.text_input("Address or city name", key="set_home_loc",
                              placeholder="e.g. Marine Drive, Mumbai")
    if st.button("Save location", key="set_save_loc", type="secondary"):
        from jarvis.places import save_location
        print(save_location(loc_label)) if False else None
        msg = save_location(loc_label)
        if msg.startswith("Could not") or msg.lower().startswith("i need"):
            st.error(msg)
        else:
            st.success(msg)
            st.rerun()

if st.button("Save settings", type="primary", icon=":material/save:", key="set_save"):
    from jarvis.desktop import validate_alias_text
    ok, errors, _ = validate_alias_text(alias_text)
    model_ok = (mc.strip() in ("groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b") and
                ms.strip() in ("groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b"))
    problems = [] if ok else list(errors)
    if not model_ok:
        problems.append("Both model fields must be one of: groq:openai/gpt-oss-120b or groq:openai/gpt-oss-20b")
    if problems:
        for e in problems:
            st.error(e, icon="\u26a0\ufe0f")
        st.error("Settings NOT saved.")
    else:
        ab.set_setting("model_complex", mc.strip())
        ab.set_setting("model_simple", ms.strip())
        ab.set_setting("groq_daily_token_cap", str(int(cap)))
        ab.set_setting("fast_path_aliases", alias_text.strip())
        ab.set_setting("voice_announcements", "1" if a else "0")
        ab.set_setting("wake_word_enabled", "1" if w else "0")
        st.toast("Settings saved.", icon="\U0001f527")

# ---- read-only alias-resolution demo/test -------------------------------
with st.expander("Alias resolution (demo)"):
    from jarvis.desktop import get_aliases as _ga
    test_name = st.text_input("Try an alias", key="set_alias_test", value="chrome")
    if test_name.strip():
        spec = _ga().get(test_name.strip().lower())
        if spec:
            st.success(f"{test_name!r} \\u2192 {spec}")
        else:
            st.error(f"{test_name!r} not in alias table (falls through; is it installed?)")
