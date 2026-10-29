"""Briefing endpoints: cached text (GET, never calls an LLM) and refresh (POST)."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import require_user  # noqa: E402

router = APIRouter(tags=["briefing"])

from jarvis.app_briefing import clear_today, generate, today_text  # noqa: E402


def _parse_sections(text: str) -> List[Dict[str, Any]]:
    """Split briefing text into titled sections."""
    sections: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # section headers look like "OVERDUE (0):", "DUE TODAY (1):", etc.
        if stripped.endswith(":") and (
            stripped.split()[0].isupper() if stripped.split() else False
        ):
            if current is not None:
                sections.append(current)
            current = {"title": stripped.rstrip(":"), "items": []}
        elif stripped.startswith("- ") and current is not None:
            current["items"].append(stripped[2:].strip())
        elif current is None:
            current = {"title": "Summary", "items": [stripped]}
        else:
            current["items"].append(stripped)
    if current is not None:
        sections.append(current)
    return sections


@router.get("/briefing")
def get_briefing(
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> Dict[str, Any]:
    """Return today's cached briefing. Never calls an LLM."""
    text = today_text() or ""
    return {
        "text": text,
        "date": date.today().isoformat(),
        "sections": _parse_sections(text),
    }


class RefreshPayload(BaseModel):
    pass


@router.post("/briefing/refresh")
def refresh_briefing(
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> Dict[str, Any]:
    """Rebuild today's briefing (calls the LLM)."""
    text = generate() or ""
    return {
        "ok": True,
        "text": text,
        "date": date.today().isoformat(),
        "sections": _parse_sections(text),
    }
