"""FastAPI backend for JARVIS desktop assistant.

Thin HTTP layer over the existing jarvis/ package. No agent logic, approval
behaviour, fast path, lookup tools or safety code is changed here; every route
calls the existing jarvis.* functions directly.

Run with:

    uvicorn api.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")


@asynccontextmanager
async def _lifespan(_app):
    validate_startup()
    yield


# ---- create app first so routers can be imported without side effects ----
app = FastAPI(title="JARVIS Desktop Assistant", version="1.0.0", lifespan=_lifespan)

# ---- security headers middleware ----
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "media-src 'self' blob:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none';"
    ),
}


def _is_dummy_key(key: str) -> bool:
    k = (key or "").strip().lower()
    if not k:
        return True
    if len(k) < 20:
        return True
    if k in {"dummy", "test", "invalid", "fake", "xxx", "placeholder", "none", "dummy_timeout"}:
        return True
    if k.startswith(("dummy", "fake", "placeholder")):
        return True
    return False


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def validate_startup() -> None:
    """Raise SystemExit if startup is unsafe (dummy/missing key) unless fake/test mode."""
    if _env_enabled("JARVIS_FAKE_AGENT") or _env_enabled("JARVIS_TEST_MODE"):
        return
    key = os.environ.get("GROQ_API_KEY", "")
    if _is_dummy_key(key):
        print(
            "ERROR: GROQ_API_KEY is missing, empty, 'dummy', or otherwise invalid. "
            "Set a real key in .env (or export JARVIS_FAKE_AGENT=1 for test/fake-agent mode).",
            file=sys.stderr,
        )
        raise SystemExit(1)


def validate_bind_host(host: str) -> bool:
    """Loopback-only binding unless --allow-remote / JARVIS_ALLOW_REMOTE=1."""
    loopback = {"127.0.0.1", "localhost", "::1"}
    if host in loopback:
        return True
    if _env_enabled("JARVIS_ALLOW_REMOTE") or _env_enabled("JARVIS_ALLOW_REMOTE_FLAG"):
        return True
    return False


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


app.add_middleware(SecurityHeadersMiddleware)

# CORS: same-origin by default; allowed origins read from settings/env at runtime.
_ALLOWED_ORIGINS: list[str] = []


def _load_allowed_origins() -> list[str]:
    """Read allowed origins from settings table / env, fall back to same-origin."""
    origins: list[str] = []
    try:
        from jarvis.tasks import _conn as _tasks_conn  # noqa: PLC0415
        rows = _tasks_conn.execute(
            "SELECT value FROM settings WHERE key='allowed_origins'"
        ).fetchall()
        if rows and rows[0][0]:
            for origin in rows[0][0].split(","):
                origin = origin.strip()
                if origin:
                    origins.append(origin)
    except Exception:
        pass
    env_origins = os.getenv("JARVIS_ALLOWED_ORIGINS", "")
    for origin in env_origins.split(","):
        origin = origin.strip()
        if origin and origin not in origins:
            origins.append(origin)
    return origins


def get_allowed_origins() -> list[str]:
    global _ALLOWED_ORIGINS
    if not _ALLOWED_ORIGINS:
        _ALLOWED_ORIGINS = _load_allowed_origins()
    return _ALLOWED_ORIGINS


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["content-type", "x-csrf-token", "authorization"],
    max_age=600,
)

# ---- import routers (after app exists) ----
from api.auth import router as auth_router  # noqa: E402
from api.routes.chat import router as chat_router  # noqa: E402
from api.routes.conversations import router as conversations_router  # noqa: E402
from api.routes.tasks import router as tasks_router  # noqa: E402
from api.routes.memory import router as memory_router  # noqa: E402
from api.routes.activity import router as activity_router  # noqa: E402
from api.routes.usage import router as usage_router  # noqa: E402
from api.routes.settings import router as settings_router  # noqa: E402
from api.routes.briefing import router as briefing_router  # noqa: E402
from api.routes.voice import router as voice_router  # noqa: E402
from api.routes.documents import router as documents_router  # noqa: E402

app.include_router(auth_router, prefix="/api/auth")
app.include_router(chat_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(activity_router, prefix="/api")
app.include_router(usage_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(briefing_router, prefix="/api")
app.include_router(voice_router, prefix="/api")
app.include_router(documents_router, prefix="/api")


@app.get("/api/me")
def me_endpoint(request: Request):
    from api.auth import me as _auth_me  # noqa: PLC0415

    return _auth_me(request)


@app.get("/health")
@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


# ---- SPA hosting: serve built frontend (never shadows /api) ----
_DIST = BASE_DIR / "web" / "dist"


def _mount_spa() -> None:
    if not _DIST.exists() or not (_DIST / "index.html").exists():
        return
    try:
        from fastapi.responses import FileResponse  # noqa: PLC0415
        from fastapi.staticfiles import StaticFiles  # noqa: PLC0415

        # Serve built assets (JS/CSS) directly.
        app.mount(
            "/assets",
            StaticFiles(directory=str(_DIST / "assets")),
            name="assets",
        )

        # SPA fallback: any non-/api route returns index.html.
        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            if full_path.startswith("api/") or full_path == "api":
                # Should never happen if passthrough routes matched first, but
                # keep a clear 404 to avoid shadowing the API.
                from fastapi import HTTPException  # noqa: PLC0415

                raise HTTPException(status_code=404, detail="not found")
            return FileResponse(_DIST / "index.html")
    except Exception as _e:
        pass


_mount_spa()


if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description='JARVIS API launcher')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--allow-remote', action='store_true')
    args = parser.parse_args()
    if not validate_bind_host(args.host):
        print('ERROR: refusing to bind to non-loopback host %r. Use --host 127.0.0.1 or --allow-remote (env JARVIS_ALLOW_REMOTE=1) for safe operation.' % args.host, file=sys.stderr)
        sys.exit(1)
    if args.allow_remote:
        os.environ['JARVIS_ALLOW_REMOTE']='1'
    validate_startup()
    uvicorn.run(app, host=args.host, port=args.port)
