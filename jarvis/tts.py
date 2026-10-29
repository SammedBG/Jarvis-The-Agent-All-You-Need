"""
tts.py - voice replies: turn the agent's answers into speech.

Two engines, tried in order (see speak()):
  1. Groq Orpheus  - canopylabs/orpheus-v1-english, expressive neural voices
     (troy/autumn/...), wav output, max 200 chars per request -> long replies
     are chunked at sentence boundaries and the wav chunks are stitched into
     one file. Needs the model's terms accepted once in the Groq console.
  2. edge-tts      - Microsoft's free neural voices (no key), mp3 output.
     Used automatically when Groq is unavailable (terms/key/network).

Everything fails soft: speak() returns None on any problem, so the chat
never breaks because the voice did.

The UI speaks only the live turn's final answer, stores the audio base64 in
the message, and replays it (autoplay once) after the turn's rerun - see
app_pages/chat.py.
"""
import base64
import hashlib
import io
import os
import re
import time
import wave
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TTS_CACHE_DIR = BASE_DIR / "tts_cache"

MAX_SPOKEN = 600        # don't read whole essays aloud
GROQ_MODEL = "canopylabs/orpheus-v1-english"
GROQ_VOICE = "troy"     # calm male voice; others: autumn, diana, hannah, austin, daniel
EDGE_VOICE = "en-US-GuyNeural"


# --------------------------------------------------------------------------
# text cleaning: markdown -> speakable plain text
# --------------------------------------------------------------------------

def clean_for_speech(text: str) -> str:
    """Strip markdown/code from an answer so it reads naturally aloud."""
    text = text or ""
    text = re.sub(r"```.*?```", " code omitted. ", text, flags=re.S)   # code blocks
    text = re.sub(r"`([^`]*)`", r"\1", text)                           # `inline`
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)                   # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)               # links -> label
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)          # headings
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)               # bullets
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)                   # quotes
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)                    # bold
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)                       # italic
    text = re.sub(r"~~(.*?)~~", r"\1", text)                           # strike
    text = re.sub(r"[*#_`~✳✅]", "", text)                                # leftovers
    text = " ".join(text.split())
    if len(text) > MAX_SPOKEN:                                         # cap at a word
        cut = text[:MAX_SPOKEN].rsplit(" ", 1)[0]
        text = cut + " ... "
    return text.strip()


# --------------------------------------------------------------------------
# chunking + wav stitching (Groq's 200-char input limit)
# --------------------------------------------------------------------------

def _chunk_text(text: str, limit: int = 180) -> list[str]:
    """Split into pieces of <= limit chars, preferring sentence boundaries."""
    chunks: list[str] = []
    cur = ""
    for s in re.split(r"(?<=[.!?])\s+", text):     # sentences
        if len(s) > limit:                          # overlong sentence -> words
            if cur:
                chunks.append(cur)
                cur = ""
            piece = ""
            for w in s.split():
                while len(w) > limit:               # pathological single word
                    if piece:
                        chunks.append(piece)
                        piece = ""
                    chunks.append(w[:limit])
                    w = w[limit:]
                cand = f"{piece} {w}".strip()
                if len(cand) <= limit:
                    piece = cand
                else:
                    chunks.append(piece)
                    piece = w
            cur = piece                             # tail keeps packing
        else:
            cand = f"{cur} {s}".strip()
            if len(cand) <= limit:
                cur = cand
            else:
                if cur:
                    chunks.append(cur)
                cur = s
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c]


def _stitch_wavs(wavs: list[bytes]) -> bytes:
    """Concatenate wav files (same format) into one: header of the first,
    then all PCM frames back to back."""
    out = io.BytesIO()
    with wave.open(out, "wb") as dst:
        for i, raw in enumerate(wavs):
            with wave.open(io.BytesIO(raw), "rb") as src:
                if i == 0:
                    dst.setparams(src.getparams())
                dst.writeframes(src.readframes(src.getnframes()))
    return out.getvalue()


# --------------------------------------------------------------------------
# engines
# --------------------------------------------------------------------------

def _groq_speak(text: str) -> tuple[bytes, str] | None:
    """Groq Orpheus: chunked at sentence boundaries, stitched into one wav."""
    import os

    import requests

    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return None
    pieces, raws = _chunk_text(text), []
    for piece in pieces:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/speech",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": GROQ_MODEL, "voice": GROQ_VOICE,
                  "input": piece, "response_format": "wav"},
            timeout=45,
        )
        if r.status_code != 200:
            return None          # terms not accepted / key / quota -> caller falls back
        data = None
        if "json" in r.headers.get("content-type", ""):
            try:
                payload = r.json()
            except Exception:
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("audio"), str):
                data = base64.b64decode(payload["audio"])
        if data is None:
            data = r.content
        if data[:4] != b"RIFF":
            return None
        raws.append(data)
    if not raws:
        return None
    return (_stitch_wavs(raws), "wav") if len(raws) > 1 else (raws[0], "wav")


def _edge_speak(text: str) -> tuple[bytes, str] | None:
    """Free fallback: Microsoft edge-tts (mp3). Works with no API key."""
    try:
        import asyncio

        import edge_tts

        async def _run() -> bytes:
            buf = io.BytesIO()
            async for chunk in edge_tts.Communicate(text, voice=EDGE_VOICE).stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            return buf.getvalue()

        data = asyncio.run(_run())
        return (data, "mp3") if data and data[:1] in (b"\xff", b"ID3") else None
    except Exception:
        return None


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _mark_speaking(text: str) -> None:
    try:
        TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (BASE_DIR / ".tts_lock").write_text(f"{time.time() + max(2.0, len(text) / 12.0):.2f}")
    except Exception:
        pass

def _clear_speaking() -> None:
    try:
        (BASE_DIR / ".tts_lock").unlink(missing_ok=True)
    except Exception:
        pass

def is_speaking() -> bool:
    try:
        lock = BASE_DIR / ".tts_lock"
        if not lock.exists():
            return False
        txt = lock.read_text().strip()
        if not txt or time.time() > float(txt):
            lock.unlink(missing_ok=True)
            return False
        return True
    except Exception:
        return False

def _cache_read(key: str) -> tuple[bytes, str] | None:
    try:
        d = TTS_CACHE_DIR / f"{key}.bin"
        f = TTS_CACHE_DIR / f"{key}.fmt"
        if d.exists() and f.exists():
            data = d.read_bytes()
            if data:
                return (data, (f.read_text().strip() or "mp3"))
    except Exception:
        pass
    return None

def _cache_write(key: str, got: tuple[bytes, str]) -> None:
    try:
        TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        TTS_CACHE_DIR / f"{key}.bin"
        (TTS_CACHE_DIR / f"{key}.bin").write_bytes(got[0])
        (TTS_CACHE_DIR / f"{key}.fmt").write_text(got[1])
    except Exception:
        pass

def speak(text: str) -> tuple[bytes, str] | None:
    """Text -> (audio bytes, 'wav'|'mp3'). Disk-cached by cleaned text.
    Groq first (nicer voice), edge-tts as the always-available fallback."""
    plain = clean_for_speech(text)
    if not plain:
        return None
    key = _cache_key(plain)
    cached = _cache_read(key)
    if cached:
        return cached

    _mark_speaking(plain)
    try:
        got = None
        try:
            got = _groq_speak(plain)
        except Exception:
            got = None
        if got is None:
            try:
                got = _edge_speak(plain)
            except Exception:
                got = None
        if got:
            _cache_write(key, got)
        return got
    finally:
        _clear_speaking()


def warm(phrases: list[str] | None = None) -> None:
    """Pre-synthesize common short phrases at startup."""
    if phrases is None:
        phrases = ["Done, sir.", "Screenshot taken, sir.", "Volume set, sir.",
                   "Command complete, sir.", "Morning briefing ready, sir.",
                   "Hi! How can I help you today?"]
    for p in phrases:
        try:
            speak(p)
        except Exception:
            pass


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def player_html(audio: bytes, fmt: str = "wav", autoplay: bool = False) -> str:
    """A native <audio controls> player as a data-URI HTML blob.
    autoplay only for the live turn (browsers allow it after the user has
    interacted with the page, which they have - they just sent a message)."""
    mime = "audio/mpeg" if fmt == "mp3" else "audio/wav"
    b64 = base64.b64encode(audio).decode("ascii")
    auto = " autoplay" if autoplay else ""
    return (f'<audio controls{auto} preload="metadata" id="jrvisaudio" '
            f'class="jrvis-audio" style="width:100%;margin:.35rem 0" '
            f'src="data:{mime};base64,{b64}"></audio>')
