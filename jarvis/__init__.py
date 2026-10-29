"""JARVIS brain package: agent, tools, task/memory stores, voice, desktop control, briefings.

Public API (import any of these, e.g. `from jarvis import agent, tasks`)
---------------------------------------------------------------------------
jarvis.agent           - LangGraph agent, ask_agent / ask_agent_stream, to_text
jarvis.desktop         - desktop control tools (system_status, open_app, ...)
jarvis.tasks           - task/rule/decision manager + settings table
jarvis.memory          - long-term facts about the user (as `long_memory`)
jarvis.tts             - text-to-speech + player_html
jarvis.app_briefing    - morning briefing + generic settings helper
jarvis.app_reminders   - background watcher (reminders + briefing nudge)
jarvis.app_data        - cached read-only loaders for dashboard pages
"""
from . import desktop
from . import tasks
from . import memory as long_memory
from . import tts
from . import app_briefing
from . import app_reminders
from . import app_data
from . import agent

__all__ = [
    "agent", "desktop", "tasks", "memory", "long_memory", "tts",
    "app_briefing", "app_reminders", "app_data",
]
