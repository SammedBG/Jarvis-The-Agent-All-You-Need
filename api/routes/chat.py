"""Chat endpoints: streaming assistant turns via SSE."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sse_starlette import EventSourceResponse
from starlette.status import HTTP_409_CONFLICT

from api.deps import require_user  # noqa: E402

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

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
    pending_calls = deque()
    emitted_any_text = False
    stream_usage = {"prompt_tokens": 0, "completion_tokens": 0, "route": ""}

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
                try:
                    ev = await asyncio.wait_for(
                        q.get(), timeout=float(os.getenv("JARVIS_CHAT_IDLE_TIMEOUT", "90"))
                    )
                except asyncio.TimeoutError:
                    logger.warning("Chat stream idle timeout for thread %s", thread_id)
                    yield _sse({
                        "type": "error",
                        "message": "The assistant timed out while waiting for the model. Check the API key, model access, and network, then retry.",
                    })
                    return
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
                    txt = ev.get("text", "") or ""
                    tstatus = "ok"
                    if isinstance(txt, str) and txt.strip().lower().startswith("error"):
                        tstatus = "error"
                    yield _sse(
                        {
                            "type": "tool_end",
                            "name": name,
                            "status": tstatus,
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
                elif kind == "usage":
                    stream_usage["prompt_tokens"] = int(ev.get("prompt_tokens", 0) or 0)
                    stream_usage["completion_tokens"] = int(ev.get("completion_tokens", 0) or 0)
                    stream_usage["route"] = ev.get("route", "") or ""
                elif kind == "error":
                    if ev.get("kind") == "rate_limit":
                        retry = ev.get("retry_after")
                        if isinstance(retry, (int, float)) and retry and retry > 0:
                            reset = datetime.now(timezone.utc) + timedelta(seconds=int(retry))
                            msg = "Daily limit reached, resets at %s." % reset.astimezone().strftime("%H:%M")
                        else:
                            msg = "Daily limit reached, resets shortly."
                    elif ev.get("kind") == "limit":
                        msg = (
                            "I reached the request's reasoning-step limit before I could finish. "
                            "Try a narrower question; any tool results are available in API Activity."
                        )
                    else:
                        detail = str(ev.get("message", "")).lower()
                        if any(term in detail for term in ("401", "authentication", "invalid api key", "unauthorized")):
                            msg = "The model provider rejected its API key. Update GROQ_API_KEY in .env and restart the API."
                        elif any(term in detail for term in ("timeout", "timed out", "connection", "connecterror")):
                            msg = "Could not reach the model provider. Check the network and retry."
                        elif any(term in detail for term in ("model", "not found", "unsupported")):
                            msg = "The configured model is unavailable. Check the model setting and provider access."
                        elif "tool call validation failed" in detail or "not in request.tools" in detail:
                            msg = "The assistant tried to use a tool that wasn't available for this step. The error was logged; please retry."
                        else:
                            msg = "The assistant could not complete this request. Check API Activity for details, then retry."
                        # log details to Activity; never return raw error to client
                        try:
                            from jarvis.tasks import log_tool_activity  # noqa: PLC0415

                            log_tool_activity(
                                "chat",
                                {"thread_id": thread_id},
                                ev.get("message", msg),
                                status="error",
                            )
                        except Exception:
                            pass
                    yield _sse({"type": "error", "message": msg})
                # discard events are intentionally ignored
            # stream complete: usage + done
            yield _sse(
                {
                    "type": "usage",
                    "route": stream_usage["route"] or "unknown",
                    "model_label": _model_label(),
                    "prompt_tokens": stream_usage["prompt_tokens"],
                    "completion_tokens": stream_usage["completion_tokens"],
                    "latency_ms": _elapsed_ms(turn_start),
                }
            )
            yield _sse({"type": "done"})
        finally:
            _running.pop(thread_id, None)

    return EventSourceResponse(event_generator())


class ApprovePayload(BaseModel):
    id: Any = None
    approved: bool
    feedback: Optional[str] = None
    thread_id: str | None = None


class StopPayload(BaseModel):
    thread_id: str | None = None


@router.post("/chat/stop")
def chat_stop(
    request: Request,
    payload: StopPayload | None = None,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
    thread_id: str | None = None,
):
    """Cancel the running turn for a thread."""
    thread_id = (thread_id or (payload.thread_id if payload else None) or "ui-main").strip()
    _cancelled.add(thread_id)
    return {"ok": True}


@router.post("/approve")
def approve(request: Request, payload: ApprovePayload, user: dict = Depends(require_user)):  # type: ignore[arg-type]
    """Resume the paused graph with the exact pending tool call."""
    thread_id = (payload.thread_id or request.query_params.get("thread_id") or "ui-main").strip()
    # If pending approval is identified by id vs the graph's own pending,
    # the resumed action is always the server-side pending one, never client args.
    resume_obj: Dict[str, Any]
    if payload.approved:
        resume_obj = {"approved": True}
    else:
        resume_obj = {"approved": False, "feedback": payload.feedback or ""}
    try:
        if not payload.approved:
            # always log a decline to Activity (never client-supplied args)
            try:
                from jarvis.tasks import log_tool_activity  # noqa: PLC0415

                log_tool_activity(
                    "approval_decided",
                    {"id": payload.id},
                    "User declined.",
                    status="declined",
                )
            except Exception:
                pass
            try:
                from jarvis.agent import get_pending  # noqa: PLC0415

                config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
                pending = get_pending(config)
                if pending is not None:
                    for a_ in pending.get("actions", []):
                        log_tool_activity(
                            a_.get("name", "approval"),
                            a_.get("args") or {},
                            "User declined.",
                            status="declined",
                        )
            except Exception:
                pass
        from jarvis.agent import ask_agent  # noqa: PLC0415

        result = ask_agent("", thread_id=thread_id, resume=resume_obj)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="approval failed")
    return {
        "ok": True,
        "reply": result.get("reply"),
        "tools": result.get("tools"),
        "error": result.get("error"),
        "pending": result.get("pending"),
    }



# ---- helpers ----

def _sse(payload: Dict[str, Any]) -> Dict[str, str]:
    return {"data": json.dumps(payload, default=str)}


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _model_label() -> str:
    try:
        from jarvis.agent import MODEL_NAME  # noqa: PLC0415

        return MODEL_NAME
    except Exception:
        return "groq:openai/gpt-oss-120b"
