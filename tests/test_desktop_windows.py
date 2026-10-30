import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JARVIS_DB", os.path.join(os.environ.get("TEMP", "."), "jarvis-test-windows.db"))

from jarvis import desktop


def test_windows_known_apps_resolve_without_launching(monkeypatch):
    monkeypatch.setattr(desktop, "IS_WINDOWS", True)
    monkeypatch.setattr(desktop.shutil, "which", lambda _name: None)
    monkeypatch.setattr(desktop.Path, "is_file", lambda _self: False)

    assert desktop._windows_app_command("calculator") == ["calc.exe"]
    assert desktop._windows_app_command("Chrome") is None
    assert desktop._windows_app_command("VS Code") is None


def test_windows_app_aliases_are_resolved_and_launcher_called(monkeypatch):
    monkeypatch.setattr(desktop, "IS_WINDOWS", True)
    monkeypatch.setattr(desktop.shutil, "which", lambda name: {
        "chrome.exe": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "code": r"C:\Users\test\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    }.get(name))
    launched = []
    monkeypatch.setattr(desktop, "_launch", lambda argv, label: launched.append((argv, label)) or "launched")

    assert desktop.open_app.invoke({"app": "Chrome"}) == "launched"
    assert launched[-1][0] == [r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
    assert desktop.open_app.invoke({"app": "VS Code"}) == "launched"
    assert launched[-1][0] == [r"C:\Users\test\AppData\Local\Programs\Microsoft VS Code\Code.exe"]


def test_windows_missing_app_reports_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop, "IS_WINDOWS", True)
    monkeypatch.setattr(desktop.shutil, "which", lambda _name: None)
    monkeypatch.setattr(desktop.Path, "is_file", lambda _self: False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "common"))

    result = desktop.open_app.invoke({"app": "Chrome"})
    assert "Could not find 'Chrome'" in result


def test_windows_finds_installed_app_from_start_menu(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop, "IS_WINDOWS", True)
    monkeypatch.setattr(desktop.shutil, "which", lambda _name: None)
    programs = tmp_path / "Microsoft/Windows/Start Menu/Programs"
    programs.mkdir(parents=True)
    shortcut = programs / "Spotify.lnk"
    shortcut.touch()
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "common"))
    launched = []
    monkeypatch.setattr(desktop, "_launch", lambda argv, label: launched.append((argv, label)) or "launched")

    assert desktop.open_app.invoke({"app": "Spotify"}) == "launched"
    assert launched == [([str(shortcut)], "Spotify")]


def test_websites_are_not_default_application_aliases():
    assert "spotify" not in desktop._APP_ALIASES
    assert "whatsapp" not in desktop._APP_ALIASES
    assert "youtube" not in desktop._APP_ALIASES


def test_spotify_track_uri_opens_installed_windows_app(monkeypatch):
    monkeypatch.setattr(desktop, "IS_WINDOWS", True)
    monkeypatch.setattr(desktop, "_windows_app_command", lambda _name: [r"C:\Spotify\Spotify.exe"])
    opened = []
    monkeypatch.setattr(desktop.os, "startfile", opened.append, raising=False)

    result = desktop.open_app.invoke({"app": "spotify:track:0xlWd9o8yjKpJ02WJy79kZ"})
    assert result == "Sent the track to the Spotify desktop app."
    assert opened == ["spotify:track:0xlWd9o8yjKpJ02WJy79kZ"]


def test_spotify_track_uri_does_not_fall_back_to_web(monkeypatch):
    monkeypatch.setattr(desktop, "IS_WINDOWS", True)
    monkeypatch.setattr(desktop, "_windows_app_command", lambda _name: None)
    opened = []
    monkeypatch.setattr(desktop.os, "startfile", opened.append, raising=False)

    result = desktop.open_app.invoke({"app": "spotify:track:0xlWd9o8yjKpJ02WJy79kZ"})
    assert "not installed" in result
    assert "did not open the web player" in result
    assert opened == []


def test_spotify_track_uri_launches_linux_desktop_client(monkeypatch):
    monkeypatch.setattr(desktop, "IS_WINDOWS", False)
    monkeypatch.setattr(desktop, "IS_LINUX", True)
    monkeypatch.setattr(desktop.shutil, "which", lambda name: "/usr/bin/spotify" if name == "spotify" else None)
    launched = []
    monkeypatch.setattr(desktop, "_launch", lambda argv, label: launched.append((argv, label)) or "launched")

    assert desktop.open_app.invoke({"app": "spotify:track:abc123"}) == "launched"
    assert launched == [(["/usr/bin/spotify", "spotify:track:abc123"], "Spotify")]
