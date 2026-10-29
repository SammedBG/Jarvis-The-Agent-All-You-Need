"""Task endpoints backed by jarvis.tasks."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.status import HTTP_404_NOT_FOUND

from api.deps import require_user  # noqa: E402

router = APIRouter(tags=["tasks"])

from jarvis.conversations import recent_conversations, search_conversations  # noqa: E402,E501
from jarvis.tasks import (  # noqa: E402,E501
    TASK_TOOLS,
    add_task,
    cancel_task,
    complete_task,
    list_tasks,
    snooze_task,
    update_task,
)

# map tool name -> callable
_TOOL_BY_NAME = {t.name: t for t in TASK_TOOLS if hasattr(t, "name")}


class TaskIn(BaseModel):
    title: str
    due: str = ""
    priority: str = "normal"
    details: str = ""
    repeat: str = ""


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    due: Optional[str] = None
    priority: Optional[str] = None
    title: Optional[str] = None
    details: Optional[str] = None
    repeat: Optional[str] = None
    minutes: Optional[int] = None


@router.get("/tasks")
def list_tasks_route(
    view: str = Query("pending"),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    from jarvis.tasks import list_tasks as _list_tasks

    text = _list_tasks.invoke({"view": view})
    return {"view": view, "text": text, "tasks": _parse_tasks(text)}


def _parse_tasks(text: str) -> List[Dict[str, Any]]:
    """Best-effort parse of list_tasks text into structured items."""
    items: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("Nothing", "Last ", "task(s)")):
            continue
        if line.startswith("- "):
            line = line[2:]
        items.append({"text": line})
    return items


@router.post("/tasks")
def add_task_route(
    payload: TaskIn,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    result = add_task.invoke(
        {
            "title": payload.title,
            "due": payload.due,
            "priority": payload.priority,
            "details": payload.details,
            "repeat": payload.repeat,
        }
    )
    return {"ok": True, "result": result}


@router.patch("/tasks/{task_id}")
def update_task_route(
    task_id: str,
    payload: TaskUpdate,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    task_ref = str(task_id)
    if payload.status == "done":
        result = complete_task.invoke({"id": task_ref})
    elif payload.minutes is not None:
        result = snooze_task.invoke({"id": task_ref, "minutes": payload.minutes})
    else:
        result = update_task.invoke(
            {
                "id": task_ref,
                "due": payload.due or "",
                "priority": payload.priority or "",
                "title": payload.title or "",
                "details": payload.details or "",
                "repeat": payload.repeat or "",
            }
        )
    return {"ok": True, "result": result}


@router.delete("/tasks/{task_id}")
def delete_task_route(
    task_id: str,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    result = cancel_task.invoke({"id": str(task_id), "reason": "deleted via API"})
    return {"ok": True, "result": result}
