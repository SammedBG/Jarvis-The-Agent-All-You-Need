"""Request dependencies for the JARVIS API."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED

from api.auth import get_session_from_request  # noqa: PLC0415


def require_user(request: Request) -> Dict[str, Any]:
    """Authenticate via the session cookie; raise 401 if missing/invalid."""
    session = get_session_from_request(request)
    if not session:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    return session


def require_csrf(request: Request) -> None:
    """Validate X-CSRF-Token on mutating methods."""
    from api.auth import _require_csrf  # noqa: PLC0415

    _require_csrf(request)
