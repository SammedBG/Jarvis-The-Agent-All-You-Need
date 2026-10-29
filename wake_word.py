"""
wake_word.py - Always-listening "Hey Jarvis" wake word for the desktop.

Runs as a SEPARATE background process next to `streamlit run ui.py`.
It listens to your microphone **locally** (openWakeWord, no cloud wake
detection), and **only after the wake word fires** is a single 5-second clip sent
to Groq Whisper and then to the agent. Approvals (run_command, close_app)
stay click-only.

Dependencies (choose one):
    .venv/bin/pip install sounddevice numpy openwakeword       # preferred
    sudo apt install alsa-utils                                # optional std fallback
    # openwakeword pulls onnxruntime + downloads a model on first use.

Commands:
    python wake_word.py                       # listen
    python wake_word.py --self-test           # 5s record + transcribe
    python wake_word.py --enable / --disable / --status / --list
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv
load_dotenv(".env")
import jarvis.agent as agent
from jarvis import tts, app_briefing

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SAMPLE_RATE = 16000
WAKE_ROUND = 0.5        # detection threshold
WAKE_CONFIRM = 2        # chunks above threshold before triggering
THREAD_ID = "voice-wake"
WAKE_PHRASE = "hey_jarvis"   # matches openWakeWord's "hey_jarvis" model


def _enabled() -> bool:
    if os.environ.get("AGNET_NO_WAKE_WORD"):
        return False
    try:
        return app_briefing.get_setting("wake_word_enabled", "1") == "1"
    except Exception:
        return True


def _set_enabled(v: bool) -> None:
    try:
        app_briefing.set_setting("wake_word_enabled", "1" if v else "0")
        print(f"wake_word enabled = {v}")
    except Exception as e:
        print("Could not persist toggle:", e)


def get_oww_model():
    try:
        import openwakeword
        from openwakeword.model import Model
    except ImportError:
        return None
    try:
        return Model()
    except Exception as e:
        print(f"[wake_word] openwakeword load failed: {e}")
        return None


def record(seconds: int, out_path: str) -> bool:
    """Record N seconds using sounddevice if available, else arecord."""
    # 1. sounddevice preferred
    try:
        import numpy as np
        import sounddevice as sd
        rec = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                     channels=1, dtype="int16")
        sd.wait()
        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
            wf.writeframes(rec.tobytes())
        return os.path.exists(out_path) and os.path.getsize(out_path) > 44
    except Exception:
        pass
    # 2. arecord fallback (no portaudio needed)
    if shutil.which("arecord"):
        try:
            subprocess.run(
                ["arecord", "-D", "default", "-q", "-d", str(seconds),
                 "-r", str(SAMPLE_RATE), "-f", "S16_LE", "-c", "1",
                 "-t", "wav", out_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=int(seconds) + 2)
            return os.path.exists(out_path) and os.path.getsize(out_path) > 44
        except Exception:
            pass
    return False


def transcribe(wav_path: str) -> str:
    if not GROQ_API_KEY:
        return ""
    try:
        with open(wav_path, "rb") as f:
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": (Path(wav_path).name, f, "audio/wav")},
                data={"model": "whisper-large-v3-turbo"}, timeout=60)
        response.raise_for_status()
        return (response.json().get("text") or "").strip()
    except Exception as e:
        print("[wake_word] transcribe failed:", e)
        return ""


def _speak_terminal(text: str) -> None:
    """System TTS (works without Streamlit)."""
    if shutil.which("spd-say"):
        subprocess.Popen(["spd-say", text[:140]],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print("    (install speech-dispatcher to hear spoken replies)")


def handle_command(phrase: str) -> None:
    lower = phrase.lower()
    for wake in ("hey jarvis", "okay jarvis", "ok jarvis", "jarvis"):
        if wake in lower:
            lower = lower.replace(wake, "", 1).strip(" ,.!?")
            break
    cmd = lower.strip()
    if not cmd:
        tmp = tempfile.mktemp(suffix=".wav")
        print("   [cmd] listening...")
        if record(RECORD_COMMAND_SECONDS, tmp):
            cmd = transcribe(tmp)
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if not cmd:
        print("[wake_word] Nothing understood.")
        return
    print(f"[wake_word] You said: {cmd}")
    result = agent.ask_agent(cmd, thread_id=THREAD_ID)
    reply = result.get("reply", "") or ""
    if reply:
        print(f"[wake_word] JARVIS: {reply}")
        got = tts.speak(reply)
        if got:
            _tts_play(got[0], got[1])
        else:
            _speak_terminal(reply)
    else:
        print("[wake_word] (no reply)")


def _tts_play(wav_bytes, fmt: str) -> None:
    tmp = tempfile.mktemp(suffix="." + fmt)
    try:
        Path(tmp).write_bytes(wav_bytes)
    except OSError:
        return
    # browser-less play: spd-say (text fallback) is currently preferred
    try:
        if shutil.which("spd-say"):
            os.unlink(tmp)
            return
        import subprocess
        player = "aplay" if shutil.which("aplay") else None
        if player and fmt == "wav":
            subprocess.Popen([player, tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print("TTS playback error:", e)


def _mic_stream_openwakeword():
    import numpy as np
    """Yield 1280-sample int16 chunks. sounddevice if available; else arecord."""
    try:
        import numpy as np
        import sounddevice as sd
        with sd.InputStream(samplerate=SAMPLE_RATE, blocksize=1280, channels=1, dtype="int16") as stream:
            while True:
                audio, _ = stream.read(1280)
                yield audio.flatten().astype(np.int16)
        return
    except Exception:
        pass
    # arecord fallback
    if not shutil.which("arecord"):
        print("[wake_word] no sounddevice and no arecord")
        return
    proc = subprocess.Popen(
        ["arecord", "-D", "default", "-q", "-r", "16000", "-f", "S16_LE",
         "-c", "1", "-t", "raw", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            raw = proc.stdout.read(2560)
            if not raw:
                break
            arr = np.frombuffer(raw, dtype="int16").astype(np.int16)
            if len(arr) < 1280:
                arr = np.pad(arr, (0, 1280 - len(arr)))
            yield arr
    finally:
        proc.kill()


def main() -> None:
    if not GROQ_API_KEY:
        print("[wake_word] GROQ_API_KEY missing in .env")
        return
    if not _enabled():
        print("[wake_word] disabled (AGNET_NO_WAKE_WORD or wake_word_enabled=0).")
        return

    print(f"[wake_word] loading openWakeWord (local, no cloud during idle) ...")
    model = get_oww_model()
    if model is None:
        print("[wake_word] cannot load model; exiting.")
        return

    print(f"[wake_word] armed for 'hey_jarvis'. Ctrl+C to stop. Listening...\n")
    det_count = 0
    try:
        for chunk in _mic_stream_openwakeword():
            try:
                if tts.is_speaking():
                    print("[wake_word] speaking... (paused)", flush=True)
                    time.sleep(0.25)
                    continue
            except Exception:
                pass
            chunk = np.array(chunk, dtype="int16")
            try:
                pred = model.predict(chunk)
            except Exception:
                pred = {WAKE_PHRASE if False else "hey_jarvis": model.predict_scores(chunk)}
            score = float(pred.get("hey_jarvis", 0.0)) if isinstance(pred, dict) else float(pred)
            if score > 0.5:
                det_count += 1
                if det_count >= WAKE_CONFIRM:
                    print(f"\n[wake_word] Detected ({score:.2f}).", flush=True)
                    # command clip
                    tmp = tempfile.mktemp(suffix=".wav")
                    if record(RECORD_COMMAND_SECONDS, tmp):
                        text = transcribe(tmp)
                        try:
                            os.unlink(tmp)
                        except OSError:
                            pass
                        if text and len(text.split()) > 0:
                            print(f"[wake_word] You said: {text}")
                            result = agent.ask_agent(text, thread_id=THREAD_ID)
                            reply = result.get("reply", "") or ""
                            if reply:
                                print(f"[wake_word] JARVIS: {reply}")
                                _speak_terminal(reply)
                        else:
                            print("[wake_word] nothing understood.")
                    det_count = 0
                else:
                    pass
            else:
                if det_count:
                    det_count = 0
                # idle — print a dot every ~1s without spamming
                print(".", end="", flush=True)
    except KeyboardInterrupt:
        print("\n[wake_word] stopped.")
    except Exception as e:
        print(f"\n[wake_word] error: {e}")


def self_test() -> None:
    tmp = tempfile.mktemp(suffix=".wav")
    print("[wake_word] recording 5s... please speak now")
    if not record(5, tmp):
        print("[wake_word] capture failed; check microphone permission.")
        return
    t = transcribe(tmp)
    try:
        os.unlink(tmp)
    except OSError:
        pass
    print(f"[wake_word] transcript: {t!r}")
    if t:
        print("[wake_word] self-test OK — mic + Whisper work.")
    else:
        print("[wake_word] empty transcript — check mic levels.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in ("--self-test", "self-test", "test"):
            self_test()
        elif cmd in ("enable", "--enable"):
            _set_enabled(True)
        elif cmd in ("disable", "--disable"):
            _set_enabled(False)
        elif cmd in ("status", "--status"):
            print("wake_word_enabled =", app_briefing.get_setting("wake_word_enabled", "1"))
            print("AGNET_NO_WAKE_WORD =", os.environ.get("AGNET_NO_WAKE_WORD"))
        elif cmd in ("list", "--list"):
            subprocess.run(["arecord", "-l"], check=False)
        else:
            print("Commands: --self-test | --enable | --disable | --status | --list")
        raise SystemExit(0)
    main()
PY