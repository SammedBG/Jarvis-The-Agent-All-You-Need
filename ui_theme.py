"""ui_theme.py - single source of truth for styling."""
import streamlit as st


def _one_tag(css: str) -> str:
    return "<style>\n" + css.strip() + "\n</style>"


_BASE_CSS = """
[data-testid="stAppDeployButton"], [data-testid="stDecoration"] { display: none !important; }
.block-container { max-width: 860px; }
.home-title { text-align: center; font-family: Georgia, "Times New Roman", serif;
  font-size: 2.5rem; margin: 8vh 0 1.5rem; color: var(--text-color, #ECEAE2); }
.home-title .spark { color: var(--primary-color, #D97757); }
.home-hint { text-align: center; color: var(--text-color, #A09E94); opacity: .7;
  font-size: .8rem; margin-top: .8rem; }
.side-brand { font-family: Georgia, "Times New Roman", serif; font-size: 1.3rem;
  margin: .1rem 0 .9rem; color: var(--text-color, #ECEAE2); }
.side-brand .spark { color: var(--primary-color, #D97757); }
.side-label { font-size: .72rem; letter-spacing: .05em; text-transform: uppercase;
  color: var(--text-color, #A09E94); opacity: .75; margin: 1.1rem 0 .2rem; }
[data-testid="stSidebar"] .stButton > button { text-align: left; }
[data-testid="stChatMessage"] > *:not([data-testid="stChatMessageContent"]) { display: none !important; }
[data-testid="stChatMessage"] { column-gap: 0 !important; }
.typing-spark { display: inline-block; color: var(--primary-color, #D97757);
  font-size: 1.5rem; line-height: 1.3;
  animation: typing-pulse 1.2s ease-in-out infinite; }
@keyframes typing-pulse {
  0%, 100% { opacity: .3; transform: scale(.85) rotate(0deg); }
  50%      { opacity: 1;  transform: scale(1.15) rotate(180deg); }
}
.st-key-home_attach, .st-key-home_send { align-self: center; }
.st-key-home_attach button, .st-key-home_send button { height: 2.9rem; border-radius: .7rem; }
.st-key-home_msg input { height: 2.9rem; }
.st-key-home_audio { margin-top: .4rem; }
.st-key-home_audio label { font-size: .85rem; opacity: .85; }
.st-key-home_audio audio { height: 2.5rem; }
.st-key-home_audio button { border-radius: .6rem; }
@media (max-width: 640px) { .st-key-home_audio { margin-bottom: .3rem; } }
"""

_EXTRA_CSS = """
/* approve cards + user bubble + code blocks */
.approve-card { border: 1px solid rgba(255,95,86,.6);
  background: rgba(255,95,86,.06);
  border-radius: 12px; padding: .75rem 1rem 1rem; margin-top: .6rem; }
.user-bubble { background: rgba(233,117,86,0.12); border: 1px solid rgba(233,117,86,0.3);
  border-radius: 16px 16px 6px 16px; padding: .5rem .8rem;
  margin-left: auto; max-width: 80%; }
.user-bubble p { margin: 0; }
/* remove full-width dark strip behind user chat messages */
.stChatMessage { background: transparent !important; }
.sugg-chip button { background: var(--c-panel); border: 1px solid var(--c-edge);
  color: var(--c-text); border-radius: var(--r-pill); padding: .45rem .9rem; font-size: .85rem; }
.sugg-chip button:hover { background: var(--c-edge); border-color: var(--c-accent); }
[data-testid="stCodeBlock"] { background: #090c16 !important; border-radius: 12px;
  border: 1px solid var(--c-edge); }
[data-testid="stCodeBlock"] button { min-height: 44px; min-width: 44px; border-radius: var(--r-sm); }
[data-testid="stChatInputContainer"] { border-radius: 1.2rem !important;
  box-shadow: 0 8px 24px rgba(0,0,0,.35); }
[data-testid="stChatInputContainer"] input { font-size: 16px; }
@media (max-width: 480px) { .block-container { padding: .6rem; } }
@media (max-width: 768px) { .st-key-home_send button, .st-key-home_attach button,
  .st-key-home_msg input, .st-key-home_audio { height: 2.4rem; } }
.block-container code { font-size: .85rem; line-height: 1.5; }
/* briefing card action buttons: prevent text truncation */
.st-key-home_send button, .st-key-home_attach button { min-width: 44px; }
/* voice recording bar: cleaner dots, better height */
.stAudio [data-testid="stAudioInput"] { margin-top: .2rem; }
.stAudio audio { width: 100%; height: 2.4rem; }
/* home suggestion chips */
.st-key-chip_row button { border-radius: 20px; font-size: .85rem; min-height: 2.2rem; }
/* tighter spacing between home card sections */
.block-container > div:first-child { margin-bottom: 1rem; }
"""


def inject_theme(max_width=None) -> None:
    css = _BASE_CSS + _EXTRA_CSS
    if max_width is not None:
        css = css.replace(".block-container { max-width: 860px; }",
                          ".block-container { max-width: %dpx; }" % max_width, 1)
    st.html(_one_tag(css))
