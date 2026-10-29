"""Voice endpoints: transcription (STT) and speech synthesis (TTS)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import requests
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.responses import Response
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_413_CONTENT_TOO_LARGE as HTTP_413_REQUEST_ENTITY_TOO_LARGE

from api.deps import require_user  # noqa: E402

router = APIRouter(tags=["voice"])

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(BASE_DIR))

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB


class SpeakIn(BaseModel):
    text: str


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> Dict[str, str]:
    """Transcribe an audio file via Groq Whisper. Returns {text}."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=400, detail="transcription not configured (no GROQ_API_KEY)"
        )

    data = await file.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="audio file too large",
        )

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (file.filename or "audio.wav", data, file.content_type or "audio/wav")},
            data={"model": "whisper-large-v3-turbo"},
            timeout=90,
        )
        r.raise_for_status()
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="transcription service unavailable")
    return {"text": r.json().get("text", "").strip()}


@router.post("/speak")
def speak(
    payload: SpeakIn,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> Response:
    """Synthesize text to speech using the existing TTS (markdown stripped)."""
    from jarvis.tts import clean_for_speech, speak  # noqa: PLC0415

    text = clean_for_speech(payload.text or "")
    if not text:
        raise HTTPException(status_code=400, detail="nothing to speak")

    try:
        result = speak(text)
    except Exception:
        raise HTTPException(status_code=502, detail="speech synthesis unavailable")
    if not result:
        raise HTTPException(status_code=502, detail="speech synthesis returned nothing")

    audio_bytes, fmt = result
    media_type = f"audio/{fmt}" if fmt else "audio/mpeg"
    return Response(content=audio_bytes, media_type=media_type)
