import os
import sys
from types import SimpleNamespace

# make sure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
os.environ.setdefault("JARVIS_DB", "/tmp/opencode/tf.db")

from jarvis import agent
from jarvis.agent import (
    _CURRENT_TOOL_CONTEXT,
    _REQUESTED_GROUPS,
    _invoke_with_tool_routing_retry,
    _fast_command,
    _resolve_toolset,
    _select_groups,
    _tool_selection_context,
    play_spotify,
    request_tools,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


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


def test_pub_and_hotel_requests_select_nearby_places_tools():
    assert "places" in _select_groups("find pubs in Bengaluru")
    assert "places" in _select_groups("show hotels in Bengaluru")
    assert "places" in _select_groups("find bars in Bengaluru")


def test_nearby_place_request_returns_live_tool_result_without_model_guessing(monkeypatch):
    location = "Saved location: Home. Nearby searches use this saved point, not live GPS."
    live_result = "Source: osm live lookup at 12:00 (bar results only)."
    calls = {}
    monkeypatch.setattr(
        agent, "get_my_location", SimpleNamespace(invoke=lambda _args: location)
    )

    def find_places(args):
        calls.update(args)
        return live_result

    monkeypatch.setattr(agent, "find_places", SimpleNamespace(invoke=find_places))
    result = agent._fast_places_command("find the best pub near me")

    assert result["reply"] == live_result
    assert result["tools"] == ["get_my_location", "find_places"]
    assert calls["query"] == "find the best pub near me"
    assert calls["limit"] == 5


def test_nearest_pub_request_uses_direct_live_places_path(monkeypatch):
    location = "Saved location: Home. Nearby searches use this saved point, not live GPS."
    live_result = "Source: osm live lookup; [pub] exact category."
    monkeypatch.setattr(
        agent, "get_my_location", SimpleNamespace(invoke=lambda _args: location)
    )
    monkeypatch.setattr(
        agent, "find_places", SimpleNamespace(invoke=lambda _args: live_result)
    )

    result = agent._fast_places_command("find nearest best pub to go today")

    assert result is not None
    assert result["reply"] == live_result
    assert result["tools"] == ["get_my_location", "find_places"]


def test_current_layoff_query_uses_one_live_search_without_model_loop(monkeypatch):
    calls = []
    snippet = "1. Layoff tracker\n   URL: https://example.com\n   Updated today."

    def search(args):
        calls.append(args)
        return snippet

    monkeypatch.setattr(agent, "web_search", SimpleNamespace(invoke=search))
    result = agent._fast_current_news_search(
        "give me the today layoffs in tech world wide"
    )

    assert result["tools"] == ["web_search"]
    assert len(calls) == 1
    assert calls[0]["query"] == "give me the today layoffs in tech world wide"
    assert "Live web search" in result["reply"]
    assert snippet in result["reply"]


def test_requested_tool_group_remains_available_for_next_model_step():
    token = _REQUESTED_GROUPS.set(set())
    try:
        assert "Approved group 'desktop'" in request_tools.invoke({"group": "desktop"})
        available = {tool.name for tool in _resolve_toolset()}
        assert "open_app" in available
        assert "run_command" in available
    finally:
        _REQUESTED_GROUPS.reset(token)


def test_missing_model_tool_group_is_added_and_the_step_is_retried(monkeypatch):
    attempts = []

    class FakeBoundModel:
        def __init__(self, names):
            self.names = names

        def invoke(self, _messages):
            system_text = str(_messages[0].content)
            attempts.append((self.names, system_text))
            if "open_app" not in self.names and "This turn does not authorize open_app" not in system_text:
                raise ValueError(
                    "Tool call validation failed: attempted to call tool "
                    "'open_app' which was not in request.tools"
                )
            return "recovered"

    monkeypatch.setattr(
        agent,
        "_build_llm",
        lambda _model, tools: FakeBoundModel({tool.name for tool in tools}),
    )
    groups_token = _REQUESTED_GROUPS.set({"webdocs"})
    context_token = _CURRENT_TOOL_CONTEXT.set("what is the entry fee for the park")
    try:
        result = _invoke_with_tool_routing_retry(
            "groq:openai/gpt-oss-20b", [SystemMessage(content="System")], _resolve_toolset()
        )
        assert result == "recovered"
        assert len(attempts) == 2
        assert "open_app" not in attempts[0][0]
        assert "open_app" not in attempts[1][0]
        assert "does not authorize open_app" in attempts[1][1]
    finally:
        _CURRENT_TOOL_CONTEXT.reset(context_token)
        _REQUESTED_GROUPS.reset(groups_token)


def test_routing_retry_expands_group_when_the_user_requested_it(monkeypatch):
    attempts = []

    class FakeBoundModel:
        def __init__(self, names):
            self.names = names

        def invoke(self, _messages):
            attempts.append(self.names)
            if "open_app" not in self.names:
                raise ValueError(
                    "Tool call validation failed: attempted to call tool "
                    "'open_app' which was not in request.tools"
                )
            return "opened"

    monkeypatch.setattr(
        agent,
        "_build_llm",
        lambda _model, tools: FakeBoundModel({tool.name for tool in tools}),
    )
    groups_token = _REQUESTED_GROUPS.set(set())
    context_token = _CURRENT_TOOL_CONTEXT.set("open calculator")
    try:
        core_tools = agent._tools_by_name(agent.TOOL_GROUPS["core"])
        result = _invoke_with_tool_routing_retry(
            "groq:openai/gpt-oss-20b", [SystemMessage(content="System")], core_tools
        )
        assert result == "opened"
        assert len(attempts) == 2
        assert "open_app" not in attempts[0]
        assert "open_app" in attempts[1]
    finally:
        _CURRENT_TOOL_CONTEXT.reset(context_token)
        _REQUESTED_GROUPS.reset(groups_token)


def test_fetch_webpage_rejects_private_addresses(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("127.0.0.1", 0))],
    )
    result = agent.fetch_webpage.invoke({"url": "http://localhost/private"})
    assert "private and local" in result


def test_fetch_webpage_returns_readable_public_page_text(monkeypatch):
    import requests

    class FakeResponse:
        status_code = 200
        encoding = "utf-8"
        headers = {"Content-Type": "text/html; charset=utf-8"}

        @staticmethod
        def raise_for_status():
            pass

        @staticmethod
        def iter_content(_size):
            return [b"<html><script>ignore</script><p>Adult entry costs 100.</p></html>"]

        @staticmethod
        def close():
            pass

    monkeypatch.setattr(
        agent.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 0))],
    )
    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: FakeResponse())
    result = agent.fetch_webpage.invoke({"url": "https://example.com/tickets"})
    assert result == "Adult entry costs 100."


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
