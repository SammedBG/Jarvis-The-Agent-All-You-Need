"""Settings endpoints: models, token cap, voice toggles, home location, aliases."""
from __future__ import annotations

import os
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
        "api_keys": {
            "groq": bool(os.getenv("GROQ_API_KEY")),
            "google": bool(os.getenv("GOOGLE_PLACES_KEY")),
            "foursquare": bool(os.getenv("FOURSQUARE_KEY")),
            "gmail": bool(os.getenv("GMAIL_ADDRESS") and os.getenv("GMAIL_APP_PASSWORD")),
        },
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


class LocationIn(BaseModel):
    label: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


@router.post("/settings/location")
def save_location_route(
    payload: LocationIn,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    from jarvis.places import save_location as _save_location
    if payload.lat is not None and payload.lon is not None:
        # store directly as "Current location"
        import json
        from jarvis.app_briefing import set_setting as _ss
        _ss("home_location", json.dumps({"label": "Current location", "lat": payload.lat, "lon": payload.lon}))
        return {"ok": True, "label": "Current location", "lat": round(payload.lat, 2), "lon": round(payload.lon, 2)}
    label = (payload.label or "").strip()
    if not label:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="label or lat/lon required")
    result = _save_location.invoke({"label": label})
    return {"ok": True, "result": result}


@router.delete("/settings/location")
def clear_location_route(
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    set_setting("home_location", "")
    return {"ok": True}


class TestKeyIn(BaseModel):
    provider: str


@router.post("/settings/test_key")
def test_key_route(
    payload: TestKeyIn,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    provider = (payload.provider or "").lower()
    # harmless cheapest request
    try:
        if provider == "groq":
            import os
            import requests as _r
            api_key = os.getenv("GROQ_API_KEY", "")
            r = _r.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": "openai/gpt-oss-20b", "max_tokens": 1,
                      "messages": [{"role": "user", "content": "ping"}]},
                timeout=10,
            )
            status = r.status_code
        elif provider == "google":
            import os
            import requests as _r
            key = os.getenv("GOOGLE_PLACES_KEY", "")
            r = _r.get("https://maps.googleapis.com/maps/api/geocode/json",
                        params={"address": "Paris", "key": key}, timeout=10)
            j = r.json()
            status = r.status_code if r.status_code != 200 else (200 if j.get("results") else 400)
        elif provider == "foursquare":
            import os
            import requests as _r
            key = os.getenv("FOURSQUARE_KEY", "")
            r = _r.get("https://api.foursquare.com/v3/places/search",
                        params={"query": "cafe", "ll": "48.8589,2.3200", "radius": 1000, "limit": 1},
                        headers={"Authorization": key}, timeout=10)
            status = r.status_code
        elif provider == "gmail":
            import os
            import imaplib as _i
            addr = os.getenv("GMAIL_ADDRESS", "")
            epw = os.getenv("GMAIL_APP_PASSWORD", "")
            host = os.getenv("GMAIL_IMAP_HOST", "imap.gmail.com")
            port = int(os.getenv("GMAIL_IMAP_PORT", "993"))
            m = _i.IMAP4_SSL(host, port)
            m.login(addr, epw)
            m.logout()
            return {"ok": True, "status": "ok", "detail": "IMAP login succeeded"}
        else:
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="unknown provider")
        if status == 200:
            return {"ok": True, "status": "ok", "detail": "OK"}
        if status == 401 or status == 403:
            return {"ok": True, "status": "invalid", "detail": "Invalid or not set"}
        if status == 429:
            return {"ok": True, "status": "rate_limited", "detail": "Rate limited"}
        return {"ok": True, "status": "error", "detail": f"HTTP {status}"}
    except Exception:
        return {"ok": True, "status": "invalid", "detail": "Invalid or not configured"}