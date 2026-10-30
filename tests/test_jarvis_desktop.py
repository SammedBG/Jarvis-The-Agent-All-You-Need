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
    assert "hands-free" in overlay.status.text().lower()
    assert "Hey JARVIS" in overlay.mic.text()
    assert not hasattr(overlay.mic, "pressed")
    if sys.platform.startswith("win"):
        from PyQt6.QtCore import Qt
        assert not overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    overlay.close()


def test_wake_listener_signals_only_after_local_phrase_confirmation(monkeypatch):
    class FakeStream:
        closed = False
        reads = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.closed = True

        def read(self, _size):
            self.reads += 1
            return ([0] * jarvis_desktop.WAKE_CHUNK_SAMPLES, False)

    class FakeModel:
        def __init__(self):
            self.scores = iter((0.8, 0.9))

        def predict(self, _audio):
            return {"hey_jarvis": next(self.scores)}

    stream = FakeStream()
    monkeypatch.setattr(jarvis_desktop, "_load_wake_model", FakeModel)
    monkeypatch.setattr(jarvis_desktop, "_open_wake_stream", lambda: stream)
    monkeypatch.setattr(jarvis_desktop.tts, "is_speaking", lambda: False)
    listener = jarvis_desktop.WakeWordListener()
    detections = []
    listener.wake_detected.connect(lambda: detections.append(stream.closed))

    listener.run()

    assert stream.reads == 2
    assert detections == [True]


def test_wake_detection_starts_command_capture_without_a_button_click(monkeypatch):
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    overlay = jarvis_desktop.Overlay()
    started = []
    monkeypatch.setattr(overlay.worker, "start", lambda: started.append(True))
    monkeypatch.setattr(QApplication, "beep", lambda: None)

    overlay._on_wake_detected()

    assert started == [True]
    assert "Listening for your command" in overlay.status.text()
    assert "Hey JARVIS" in overlay.mic.text() or "command" in overlay.mic.text()
    overlay.close()
