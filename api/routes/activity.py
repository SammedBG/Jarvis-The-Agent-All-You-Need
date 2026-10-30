"""Activity log endpoint (redacted)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from starlette.status import HTTP_400_BAD_REQUEST

from api.deps import require_user  # noqa: E402

router = APIRouter(tags=["activity"])

from jarvis.tasks import list_activity  # noqa: E402


@router.get("/activity")
def list_activity_route(
    limit: int = Query(50, ge=1, le=1000),
    tool: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    rows = list_activity(limit=limit, tool=tool, status=status, since=since)
    return {"activities": rows}
