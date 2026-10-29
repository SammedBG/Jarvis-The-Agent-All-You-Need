"""Settings endpoints: models, token cap, voice toggles, home location, aliases."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.status import HTTP_400_BAD_REQUEST

from api.deps import require_user  # noqa: E402

router = APIRouter(tags=["settings"])

from jarvis.app_briefing import get_setting, set_setting  # noqa: E402

ALLOWED_MODELS = {"groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b"}


class SettingsIn(BaseModel):
    model_complex: Optional[str] = None
    model_simple: Optional[str] = None
    groq_daily_token_cap: Optional[int] = None
    voice_replies: Optional[bool] = None
    voice_announcements: Optional[bool] = None
    home_location: Optional[str] = None
    fast_path_aliases: Optional[str] = None


def _validate_model(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    if value not in ALLOWED_MODELS:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="model must be one of: groq:openai/gpt-oss-120b, groq:openai/gpt-oss-20b",
        )
    return value


@router.get("/settings")
def get_settings(
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> Dict[str, Any]:
    def _get(key: str, default: str = "") -> str:
        return get_setting(key, default)

    return {
        "model_complex": _get("model_complex", "groq:openai/gpt-oss-120b"),
        "model_simple": _get("model_simple", "groq:openai/gpt-oss-20b"),
        "groq_daily_token_cap": int(_get("groq_daily_token_cap", "200000") or 200000),
        "voice_replies": _get("voice_replies", "0") == "1",
        "voice_announcements": _get("voice_announcements", "0") == "1",
        "home_location": _get("home_location", ""),
        "fast_path_aliases": _get("fast_path_aliases", ""),
    }


@router.patch("/settings")
def update_settings(
    payload: SettingsIn,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> Dict[str, Any]:
    updates: Dict[str, str] = {}
    if payload.model_complex is not None:
        updates["model_complex"] = _validate_model(payload.model_complex)
    if payload.model_simple is not None:
        updates["model_simple"] = _validate_model(payload.model_simple)
    if payload.groq_daily_token_cap is not None:
        updates["groq_daily_token_cap"] = str(int(payload.groq_daily_token_cap))
    if payload.voice_replies is not None:
        updates["voice_replies"] = "1" if payload.voice_replies else "0"
    if payload.voice_announcements is not None:
        updates["voice_announcements"] = "1" if payload.voice_announcements else "0"
    if payload.home_location is not None:
        updates["home_location"] = payload.home_location
    if payload.fast_path_aliases is not None:
        updates["fast_path_aliases"] = payload.fast_path_aliases

    for key, value in updates.items():
        set_setting(key, value)

    return get_settings(user)
