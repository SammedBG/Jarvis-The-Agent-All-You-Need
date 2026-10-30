import os
import sys

# make sure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
os.environ.setdefault("JARVIS_DB", "/tmp/opencode/tf.db")

from jarvis import agent
from jarvis.agent import (
    _CURRENT_TOOL_CONTEXT,
    _REQUESTED_GROUPS,
    _fast_command,
    _resolve_toolset,
    _select_groups,
    _tool_selection_context,
    play_spotify,
    request_tools,
)
from langchain_core.messages import AIMessage, HumanMessage


FAST = {
    "mute", "system status", "open chrome", "Set volume to 40",
    "take screenshot", "unmute",
}
NOT_FAST = {
    "open ~/.ssh", "open ../../etc/passwd", "open file.sh", "open C:\\",
    "open a.exe", "open chrome; ls", "open chrome and delete my notes",
    "volume 400",
}


def test_whitelisted_runs():
    assert _fast_command("mute") is not None
    assert _fast_command("system status") is not None
    r = _fast_command("volume 400")
    assert r is not None and "range" in r["reply"]


def test_sensitive_and_multi_intent_fall_through():
    for q in NOT_FAST - {"volume 400"}:
        assert _fast_command(q) is None, q


def test_run_command_and_close_app_never_fast():
    assert _fast_command("run command ls -la") is None
    assert _fast_command("close chrome") is None


def test_followup_answer_keeps_desktop_tools_available():
    messages = [
        HumanMessage(content="play song on spotify"),
        AIMessage(content="Sure! Which song would you like to play?"),
        HumanMessage(content="tere liye"),
    ]
    context = _tool_selection_context(messages, "tere liye")
    assert "play song on spotify" in context
    assert "desktop" in _select_groups(context)

    token = _CURRENT_TOOL_CONTEXT.set(context)
    try:
        available = {tool.name for tool in _resolve_toolset()}
        assert "run_command" in available
        assert "open_app" in available
    finally:
        _CURRENT_TOOL_CONTEXT.reset(token)


def test_requested_tool_group_remains_available_for_next_model_step():
    token = _REQUESTED_GROUPS.set(set())
    try:
        assert "Approved group 'desktop'" in request_tools.invoke({"group": "desktop"})
        available = {tool.name for tool in _resolve_toolset()}
        assert "open_app" in available
        assert "run_command" in available
    finally:
        _REQUESTED_GROUPS.reset(token)


def test_spotify_request_searches_track_then_hands_uri_to_local_app(monkeypatch):
    calls = {}

    class FakeSearch:
        @staticmethod
        def invoke(args):
            calls["query"] = args["query"]
            return "1. Tere Liye\n   URL: https://open.spotify.com/track/0xlWd9o8yjKpJ02WJy79kZ?si=abc\n"

    class FakeApp:
        @staticmethod
        def invoke(args):
            calls["app"] = args["app"]
            return "Sent the track to the Spotify desktop app."

    monkeypatch.setattr(agent, "web_search", FakeSearch())
    monkeypatch.setattr(agent.desktop, "open_app", FakeApp())
    monkeypatch.setattr(agent.desktop, "IS_WINDOWS", True)
    monkeypatch.setattr(agent.desktop, "_windows_app_command", lambda _name: ["spotify.exe"])

    reply = play_spotify.invoke({"song": "Tere Liye"})
    assert "Opening 'Tere Liye' in the Spotify desktop app" in reply
    assert calls["query"] == 'site:open.spotify.com/track "Tere Liye"'
    assert calls["app"] == "spotify:track:0xlWd9o8yjKpJ02WJy79kZ"


def test_spotify_request_never_searches_when_local_app_is_missing(monkeypatch):
    class FakeSearch:
        def invoke(self, _args):
            raise AssertionError("must not search/fall back when Spotify is missing")

    monkeypatch.setattr(agent, "web_search", FakeSearch())
    monkeypatch.setattr(agent.desktop, "IS_WINDOWS", True)
    monkeypatch.setattr(agent.desktop, "_windows_app_command", lambda _name: None)
    reply = play_spotify.invoke({"song": "Tere Liye"})
    assert "Spotify desktop app was not found" in reply


def test_spotify_tool_is_bound_for_music_requests():
    token = _CURRENT_TOOL_CONTEXT.set("play some music using Spotify")
    try:
        available = {tool.name for tool in _resolve_toolset()}
        assert "play_spotify" in available
    finally:
        _CURRENT_TOOL_CONTEXT.reset(token)


if __name__ == "__main__":
    test_whitelisted_runs()
    test_sensitive_and_multi_intent_fall_through()
    test_run_command_and_close_app_never_fast()
    print("test_fast_path OK")
