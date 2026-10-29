"""Chat endpoints: streaming assistant turns via SSE."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Deque, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sse_starlette import EventSourceResponse
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_409_CONFLICT

from api.deps import require_user  # noqa: E402

router = APIRouter(tags=["chat"])

_executor = ThreadPoolExecutor(max_workers=4)
# thread_id -> asyncio task running the stream
_running: Dict[str, asyncio.Task] = {}
# thread_ids cancelled by the user mid-turn
_cancelled: set[str] = set()


def _redact_args(args: dict) -> str:
    """Redact secret-ish values from tool args for display."""
    from jarvis.tasks import _redact  # noqa: PLC0415

    return _redact(json.dumps(args or {}, default=str))


class ChatPayload(BaseModel):
    thread_id: str | None = None
    message: str


@router.post("/chat")
async def chat(payload: ChatPayload, request: Request, user: dict = Depends(require_user)):  # type: ignore[arg-type]
    """Stream one assistant turn as SSE events."""
    require_csrf(request)
    thread_id = (payload.thread_id or "").strip() or "ui-main"
    message = payload.message or ""

    if thread_id in _running:
        raise HTTPException(
            status_code=409,
            detail="a turn is already running for this thread",
        )
    if thread_id in _cancelled:
        _cancelled.discard(thread_id)

    turn_start = time.monotonic()
    pending_calls: Deque[Dict[str, Any]] = Deque()
    emitted_any_text = False

    async def event_generator():
        nonlocal emitted_any_text
        q: asyncio.Queue = asyncio.Queue()

        def _run():
            try:
                from jarvis.agent import ask_agent_stream  # noqa: PLC0415

                for ev in ask_agent_stream(
                    text=message, thread_id=thread_id, resume=None
                ):
                    asyncio.run_coroutine_threadsafe(q.put(ev), loop)
                # sentinel: stream ended
                asyncio.run_coroutine_threadsafe(q.put(None), loop)
            except Exception as exc:  # noqa: BLE001
                asyncio.run_coroutine_threadsafe(
                    q.put(
                        {
                            "type": "error",
                            "message": "Something went wrong. Please retry.",
                            "kind": "error",
                        }
                    ),
                    loop,
                )
                asyncio.run_coroutine_threadsafe(q.put(None), loop)

        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(_executor, _run)
        _running[thread_id] = task
        try:
            while True:
                if thread_id in _cancelled:
                    _cancelled.discard(thread_id)
                    yield _sse({"type": "error", "message": "cancelled"})
                    return
                ev = await q.get()
                if ev is None:
                    break
                kind = ev.get("type")
                if kind == "delta":
                    text = ev.get("text") or ""
                    if text:
                        emitted_any_text = True
                        yield _sse({"type": "token", "text": text})
                elif kind == "tool_calls":
                    for call in ev.get("calls", []):
                        pending_calls.append(call)
                        yield _sse(
                            {
                                "type": "tool_start",
                                "name": call.get("name", ""),
                                "args_redacted": _redact_args(call.get("args") or {}),
                                "ms": _elapsed_ms(turn_start),
                            }
                        )
                elif kind == "tool_result":
                    name = ev.get("name", "")
                    if pending_calls:
                        pending_calls.popleft()
                    yield _sse(
                        {
                            "type": "tool_end",
                            "name": name,
                            "status": "ok",
                            "ms": _elapsed_ms(turn_start),
                        }
                    )
                elif kind == "pending":
                    for idx, action in enumerate(ev.get("actions") or []):
                        yield _sse(
                            {
                                "type": "approval_required",
                                "id": str(uuid.uuid4())[:8],
                                "tool": action.get("name", ""),
                                "exact_args": action.get("args") or {},
                                "reason": action.get("why", ""),
                                "origin": action.get("origin", ""),
                                "ms": _elapsed_ms(turn_start),
                            }
                        )
                elif kind == "answer":
                    text = ev.get("text") or ""
                    if text and not emitted_any_text:
                        emitted_any_text = True
                        yield _sse({"type": "token", "text": text})
                elif kind == "error":
                    msg = ev.get("message") or "Something went wrong."
                    if ev.get("kind") == "rate_limit":
                        msg = "Daily limit reached, resets shortly."
                    yield _sse({"type": "error", "message": msg})
                # discard events are intentionally ignored
            # stream complete: usage + done
            yield _sse(
                {
                    "type": "usage",
                    "route": "complex",
                    "model_label": _model_label(),
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "latency_ms": _elapsed_ms(turn_start),
                }
            )
            yield _sse({"type": "done"})
        finally:
            _running.pop(thread_id, None)

    return EventSourceResponse(event_generator())


@router.post("/chat/stop")
def chat_stop(request: Request, user: dict = Depends(require_user), thread_id: str | None = None):  # type: ignore[arg-type]
    """Cancel the running turn for a thread."""
    require_csrf(request)
    thread_id = (thread_id or "ui-main").strip()
    _cancelled.add(thread_id)
    return {"ok": True}


# ---- helpers ----

def _sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _model_label() -> str:
    try:
        from jarvis.agent import MODEL_NAME  # noqa: PLC0415

        return MODEL_NAME
    except Exception:
        return "groq:openai/gpt-oss-120b"


def require_csrf(request: Request) -> None:
    from api.auth import _require_csrf  # noqa: PLC0415

    _require_csrf(request)
