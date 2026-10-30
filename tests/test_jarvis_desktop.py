import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("JARVIS_DB", os.path.join(os.environ.get("TEMP", "."), "jarvis-desktop-test.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis import desktop
import jarvis_desktop


def test_desktop_voice_worker_transcribes_routes_and_speaks_without_live_audio(monkeypatch, tmp_path):
    # Simulate a heard command, but never access the real microphone or launch Chrome.
    monkeypatch.setattr(jarvis_desktop, "_record", lambda: str(tmp_path / "voice.wav"))
    monkeypatch.setattr(jarvis_desktop, "_transcribe_wav", lambda _path: "open chrome")
    monkeypatch.setattr(jarvis_desktop, "_speak", lambda text: spoken.append(text))
    monkeypatch.setattr(desktop, "IS_WINDOWS", True)
    monkeypatch.setattr(
        desktop.shutil,
        "which",
        lambda name: r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if name == "chrome.exe" else None,
    )
    launched = []
    monkeypatch.setattr(
        desktop, "_launch",
        lambda argv, label: launched.append((argv, label)) or f"Launched {label}.",
    )
    spoken = []
    results = []
    worker = jarvis_desktop.JarvisWorker()
    worker.result.connect(lambda user_text, reply: results.append((user_text, reply)))

    worker.run()

    assert results == [("open chrome", "Launched google-chrome.")]
    assert spoken == ["Launched google-chrome."]
    assert len(launched) == 1
    assert launched[0][0] == [r"C:\Program Files\Google\Chrome\Application\chrome.exe"]


def test_overlay_starts_visible_and_shows_ready_status():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    overlay = jarvis_desktop.Overlay()
    overlay.show_overlay()
    assert overlay.isVisible()
    assert "JARVIS online" in overlay.status.text()
    if sys.platform.startswith("win"):
        from PyQt6.QtCore import Qt
        assert not overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    overlay.close()
