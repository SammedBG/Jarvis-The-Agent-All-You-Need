"""
jarvis_desktop.py - Always-on JARVIS desktop overlay.

System tray app with a global hotkey. Press the hotkey, an overlay appears
on top of whatever you're doing, you speak, JARVIS answers out loud, then it
fades away. Your browser, editor, or game stays open underneath.

Runs beside (not instead of) `streamlit run ui.py` - same agent brain, same
memory, same tools, same voice replies.

Requirements:
    python -m pip install -r requirements.txt -r requirements-desktop.txt
    Linux only: sudo apt install -y libportaudio2

Run:
    .venv/bin/python jarvis_desktop.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import wave
from pathlib import Path

from dotenv import load_dotenv

try:
    import numpy as np
    import sounddevice as sd
    from PyQt6.QtWidgets import (
        QApplication, QSystemTrayIcon, QMenu, QWidget, QVBoxLayout,
        QLabel, QFrame, QHBoxLayout, QGraphicsDropShadowEffect,
    )
    from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QThread, QPoint
    from PyQt6.QtGui import QIcon, QKeySequence, QColor, QPainter, QLinearGradient, QBrush, QFont
except (ImportError, OSError) as exc:
    print(
        "Desktop voice dependencies are missing or their native DLLs failed to load. "
        "Install them in this virtual environment with: "
        ".venv\\Scripts\\python.exe -m pip install -r requirements-desktop.txt"
    )
    raise SystemExit(1) from exc

sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv(".env")

import jarvis.agent as agent  # ask_agent - the JARVIS brain
from jarvis import tts
import jarvis.app_briefing as app_briefing
import jarvis.app_reminders as app_reminders

# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SAMPLE_RATE = 16000
RECORD_SECONDS = 8
WAKE_PHRASE = "Hey JARVIS"
WAKE_THRESHOLD = 0.5
WAKE_CONFIRM_CHUNKS = 2
WAKE_CHUNK_SAMPLES = 1280  # 80 ms at 16 kHz
THREAD_ID = "desktop-jarvis"

HOTKEY = "<ctrl>+<alt>+j"   # global hotkey to summon JARVIS
OVERLAY_WIDTH = 560
OVERLAY_HEIGHT = 240
AUTO_HIDE_MS = 9000


# ---------------------------------------------------------------------------
# audio helpers
# ---------------------------------------------------------------------------

def _transcribe_wav(path: str) -> str:
    import requests
    r = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        files={"file": (Path(path).name, open(path, "rb"), "audio/wav")},
        data={"model": "whisper-large-v3-turbo"},
        timeout=90,
    )
    r.raise_for_status()
    return r.json().get("text", "").strip()


def _record(seconds: int = RECORD_SECONDS) -> str:
    recording = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                       channels=1, dtype="int16")
    sd.wait()
    tmp = tempfile.mktemp(suffix=".wav")
    with wave.open(tmp, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(recording.tobytes())
    return tmp


def _load_wake_model():
    """Load the local wake-word model. No microphone audio is sent while idle."""
    import openwakeword
    from openwakeword.model import Model
    from openwakeword.utils import download_models

    model_file = (
        Path(openwakeword.__file__).parent
        / "resources" / "models" / "hey_jarvis_v0.1.onnx"
    )
    if not model_file.is_file():
        download_models(["hey_jarvis_v0.1"])
    return Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")


def _open_wake_stream():
    return sd.InputStream(
        samplerate=SAMPLE_RATE,
        blocksize=WAKE_CHUNK_SAMPLES,
        channels=1,
        dtype="int16",
    )


def _speak(text: str) -> None:
    """Speak via system dispatcher (works from a terminal app). Linux + Windows."""
    try:
        from jarvis.tts import _mark_speaking
        _mark_speaking(text)
    except Exception:
        pass
    if sys.platform.startswith("win"):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(text[:140])
            engine.runAndWait()
        except Exception:
            pass
        return
    import shutil
    if shutil.which("spd-say"):
        import subprocess
        try:
            subprocess.Popen(["spd-say", text[:140]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


def _startup_greeting() -> str:
    """Speak a time-aware greeting on login and prime the briefing."""
    from datetime import datetime
    import jarvis.app_reminders as ar
    hour = datetime.now().hour
    greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    message = f"{greet}, sir. JARVIS online and standing by."
    try:
        import jarvis.app_briefing as ab
        if ab.get_setting("voice_announcements", "1") != "1":
            return message
    except Exception:
        pass
    ar._speak(message)
    return message


# ---------------------------------------------------------------------------
# worker: record -> transcribe -> ask agent -> speak
# ---------------------------------------------------------------------------

class JarvisWorker(QThread):
    status = pyqtSignal(str)
    result = pyqtSignal(str, str)   # user_text, jarvis_reply
    error = pyqtSignal(str)
    finished_speaking = pyqtSignal()

    def run(self) -> None:
        try:
            self.status.emit("Listening...")
            wav_path = _record()
            try:
                text = _transcribe_wav(wav_path)
            finally:
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass

            if not text:
                self.status.emit("Didn't catch that.")
                QTimer.singleShot(1500, self.finished_speaking.emit)
                return

            self.status.emit("Thinking...")
            result = agent.ask_agent(text, thread_id=THREAD_ID)
            reply = result.get("reply", "") or "I didn't get that."

            self.status.emit("Speaking...")
            _speak(reply)
            self.result.emit(text, reply)
        except Exception as e:
            self.status.emit("Voice command failed.")
            self.error.emit(str(e))
            print(f"[jarvis_desktop] {e}")


class WakeWordListener(QThread):
    """Continuously detect the wake phrase locally, then hand off one command."""
    status = pyqtSignal(str)
    wake_detected = pyqtSignal()
    error = pyqtSignal(str)

    def run(self) -> None:
        try:
            self.status.emit("Loading local wake-word listener...")
            model = _load_wake_model()
            consecutive = 0
            self.status.emit("Listening locally - say 'Hey JARVIS'")
            with _open_wake_stream() as stream:
                while not self.isInterruptionRequested():
                    audio, _overflowed = stream.read(WAKE_CHUNK_SAMPLES)
                    try:
                        if tts.is_speaking():
                            consecutive = 0
                            continue
                    except Exception:
                        pass
                    scores = model.predict(np.asarray(audio, dtype=np.int16).reshape(-1))
                    score = float(scores.get("hey_jarvis", 0.0))
                    consecutive = consecutive + 1 if score >= WAKE_THRESHOLD else 0
                    if consecutive >= WAKE_CONFIRM_CHUNKS:
                        # Close the continuous stream before command capture opens
                        # the microphone again.
                        break
            if consecutive >= WAKE_CONFIRM_CHUNKS:
                self.wake_detected.emit()
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# overlay window (floating, always on top)
# ---------------------------------------------------------------------------

class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool   # no taskbar entry
        )
        # Translucent frameless windows can fail UpdateLayeredWindow on Windows,
        # particularly with display scaling. The frame below is opaque.
        if not sys.platform.startswith("win"):
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(OVERLAY_WIDTH, OVERLAY_HEIGHT)

        # position: centered horizontally, near the top of the screen
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - OVERLAY_WIDTH) // 2
        y = int(screen.height() * 0.12)
        self.move(x, y)

        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        frame = QFrame(self)
        frame.setFixedSize(OVERLAY_WIDTH, OVERLAY_HEIGHT)
        frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1a2e, stop:1 #16213e);
                border: 1px solid #0f3460;
                border-radius: 20px;
            }
            QLabel#title {
                color: #e94560;
                font-size: 14pt;
                font-weight: bold;
                letter-spacing: 2px;
                background: transparent;
            }
            QLabel#status {
                color: #bbb;
                font-size: 11pt;
                background: transparent;
            }
            QLabel#result {
                color: #eaeaea;
                font-size: 12pt;
                background: transparent;
                padding: 8px;
            }
            QLabel#mic {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #e94560, stop:1 #c1124a);
                color: white;
                border-radius: 44px;
                font-size: 20pt;
                font-weight: bold;
                padding: 10px;
            }
        """)
        if not sys.platform.startswith("win"):
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(30)
            shadow.setColor(QColor(0, 0, 0, 180))
            frame.setGraphicsEffect(shadow)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        self.title = QLabel("JARVIS", objectName="title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.mic = QLabel("🎙 Say 'Hey JARVIS'", objectName="mic")
        self.mic.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status = QLabel("Starting hands-free voice...", objectName="status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.result_label = QLabel("", objectName="result")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.setWordWrap(True)

        layout.addWidget(self.title)
        layout.addWidget(self.mic)
        layout.addWidget(self.status)
        layout.addWidget(self.result_label)

        # main layout centers the frame
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(frame, alignment=Qt.AlignmentFlag.AlignCenter)

        self.worker = JarvisWorker()
        self.worker.status.connect(self.status.setText)
        self.worker.result.connect(self._show_result)
        self.worker.error.connect(self._show_error)
        self.worker.finished.connect(self._worker_finished)
        self.worker.finished_speaking.connect(self._auto_hide)
        self.wake_listener: WakeWordListener | None = None

    def start_wake_listener(self) -> None:
        if self.worker.isRunning() or (self.wake_listener and self.wake_listener.isRunning()):
            return
        self.mic.setText("🎙 Say 'Hey JARVIS'")
        listener = WakeWordListener(self)
        self.wake_listener = listener
        listener.status.connect(self.status.setText)
        listener.wake_detected.connect(self._on_wake_detected)
        listener.error.connect(self._wake_listener_error)
        listener.finished.connect(self._wake_listener_finished)
        listener.finished.connect(listener.deleteLater)
        listener.start()

    def _wake_listener_finished(self) -> None:
        self.wake_listener = None

    def stop_wake_listener(self) -> None:
        if self.wake_listener and self.wake_listener.isRunning():
            self.wake_listener.requestInterruption()
            self.wake_listener.wait(1500)

    def _on_wake_detected(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.status.setText("I heard you - say your command")
        self.mic.setText("🎙 Listening for your command...")
        QApplication.beep()
        self._start_command()

    def _wake_listener_error(self, detail: str) -> None:
        self.status.setText("Hands-free listener needs attention")
        self.result_label.setText(
            "Check microphone permission and openwakeword installation. "
            + (detail or "")[:160]
        )
        print(f"[jarvis_desktop] Wake-word listener failed: {detail}")

    def _start_command(self) -> None:
        if self.worker.isRunning():
            return
        self.result_label.setText("")
        self.status.setText("Listening for your command...")
        self.worker.start()

    def _show_result(self, user_text: str, reply: str) -> None:
        self.result_label.setText(f"You: {user_text}\nJARVIS: {reply}")
        self.status.setText("JARVIS completed the request")
        QTimer.singleShot(AUTO_HIDE_MS, self.hide)

    def _show_error(self, detail: str) -> None:
        self.status.setText("JARVIS couldn't complete that command")
        self.result_label.setText((detail or "Check microphone, GROQ_API_KEY, and network.")[:240])

    def _worker_finished(self) -> None:
        self.mic.setText("🎙 Say 'Hey JARVIS'")
        QTimer.singleShot(300, self.start_wake_listener)

    def _auto_hide(self) -> None:
        self.hide()

    def show_overlay(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.status.setText("JARVIS is hands-free - say 'Hey JARVIS'")
        self.result_label.setText("")


# ---------------------------------------------------------------------------
# system tray app
# ---------------------------------------------------------------------------

class JarvisApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # tray icon - draw a spark icon programmatically
        icon = self._make_icon()
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip("JARVIS - Desktop Assistant")

        menu = QMenu()
        show_action = menu.addAction("Show JARVIS")
        show_action.triggered.connect(self._show_overlay)
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_clicked)
        self.tray.show()

        self.overlay = Overlay()
        self.overlay.start_wake_listener()

        # global hotkey (best effort - may not grab on Wayland)
        self._setup_hotkey()

        # Show the voice surface immediately on launch instead of leaving new
        # users with only a tray icon and no visible indication that JARVIS ran.
        self.overlay.show_overlay()

        # start background watcher (reminders + morning briefing) so they
        # work even with no browser open
        app_reminders.ensure_watcher()

    def _make_icon(self) -> QIcon:
        from PyQt6.QtGui import QPixmap, QPen
        size = 64
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0, QColor("#e94560"))
        grad.setColorAt(1, QColor("#0f3460"))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.drawEllipse(
            round(size * 0.22), round(size * 0.22),
            round(size * 0.56), round(size * 0.56),
        )
        p.setPen(QPen(QColor("#ffffff"), 3))
        p.drawLine(round(size * 0.5), round(size * 0.18), round(size * 0.5), round(size * 0.82))
        p.drawLine(round(size * 0.18), round(size * 0.5), round(size * 0.82), round(size * 0.5))
        p.end()
        return QIcon(pm)

    def _setup_hotkey(self) -> None:
        try:
            from pynput import keyboard

            def on_activate():
                # QApplication must receive the call on the main thread
                QTimer.singleShot(0, self.overlay.show_overlay)

            with keyboard.GlobalHotKeys({HOTKEY: on_activate}) as h:
                self._hotkey_listener = h
                print(f"[jarvis_desktop] Global hotkey armed: {HOTKEY}")
        except Exception as e:
            print(f"[jarvis_desktop] Could not arm global hotkey ({e}).")
            print("    Click the tray icon instead, or run on X11 for global hotkeys.")

    def _show_overlay(self) -> None:
        self.overlay.show_overlay()

    def _on_tray_clicked(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_overlay()

    def _quit(self) -> None:
        self.overlay.stop_wake_listener()
        self.tray.hide()
        self.app.quit()

    def run(self) -> None:
        print("[jarvis_desktop] JARVIS is running in your system tray.")
        print(f"    Hotkey: {HOTKEY}   (or click the tray icon)")
        self.app.exec()


def main() -> None:
    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY missing in .env")
        sys.exit(1)

    app = JarvisApp()
    greeting = _startup_greeting()
    app.overlay.result_label.setText(greeting)
    app.run()


if __name__ == "__main__":
    main()
