"""Memory (facts/rules) endpoints backed by jarvis.memory and jarvis.tasks."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import BaseModel
from starlette.status import HTTP_404_NOT_FOUND

from api.deps import require_user  # noqa: E402

router = APIRouter(tags=["memory"])

from jarvis.conversations import recent_conversations, search_conversations  # noqa: E402,E501
from jarvis.memory import add_fact, delete_fact, list_facts_detailed, update_fact_text  # noqa: E402,E501
from jarvis.tasks import add_rule, list_rules_detailed, remove_rule, update_rule_text  # noqa: E402,E501


class FactIn(BaseModel):
    text: str
    source: str = "user"
    origin: Optional[str] = None


class FactUpdate(BaseModel):
    text: str


class RuleIn(BaseModel):
    text: str


class RuleUpdate(BaseModel):
    text: str


@router.get("/memory/facts")
def list_facts(
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    return {"facts": list_facts_detailed()}


@router.post("/memory/facts")
def add_fact_route(
    payload: FactIn,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    ok, msg = add_fact.invoke(
        {"text": payload.text, "source": payload.source or "user", "origin": payload.origin}
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@router.patch("/memory/facts/{fid}")
def update_fact_route(
    fid: str = PathParam(...),
    payload: FactUpdate = ...,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    result = update_fact_text.invoke({"id": int(fid), "new_text": payload.text})
    if result.startswith("Error"):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=result)
    return {"ok": True, "message": result}


@router.delete("/memory/facts/{fid}")
def delete_fact_route(
    fid: str = PathParam(...),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    result = delete_fact.invoke({"fact_id": int(fid)})
    if result.startswith("Error"):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=result)
    return {"ok": True, "message": result}


@router.get("/memory/rules")
def list_rules_route(
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    return {"rules": list_rules_detailed()}


@router.post("/memory/rules")
def add_rule_route(
    payload: RuleIn,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    result = add_rule.invoke({"text": payload.text})
    return {"ok": True, "message": result}


@router.patch("/memory/rules/{rid}")
def update_rule_route(
    rid: str = PathParam(...),
    payload: RuleUpdate = ...,
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    result = update_rule_text.invoke({"rule_id": int(rid), "new_text": payload.text})
    if result.startswith("Error"):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=result)
    return {"ok": True, "message": result}


@router.delete("/memory/rules/{rid}")
def delete_rule_route(
    rid: str = PathParam(...),
    user: dict = Depends(require_user),  # type: ignore[arg-type]
):
    result = remove_rule.invoke({"rule": str(rid)})
    if result.startswith("No rule") or result.startswith("Error"):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=result)
    return {"ok": True, "message": result}
