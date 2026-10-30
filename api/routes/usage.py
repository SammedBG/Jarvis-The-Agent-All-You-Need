"""Usage endpoints: today's token sum via one SQL query, per-day and per-route."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import require_user  # noqa: E402

router = APIRouter(tags=["usage"])

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(BASE_DIR))

from jarvis.tasks import DB_PATH  # noqa: E402


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


class UsageOut(BaseModel):
    today_tokens: int
    today_calls: int
    daily: List[Dict[str, Any]]
    by_route: List[Dict[str, Any]]


@router.get("/usage")
def get_usage(
    user: dict = Depends(require_user),  # type: ignore[arg-type]
) -> UsageOut:
    today = date.today().isoformat()
    conn = _db()
    try:
        # one SQL query for today's token sum
        row = conn.execute(
            "SELECT SUM(prompt_tokens + completion_tokens) AS total, "
            "COUNT(*) AS calls FROM usage WHERE substr(ts,1,10)=?",
            (today,),
        ).fetchone()
        today_tokens = int(row["total"] or 0)
        today_calls = int(row["calls"] or 0)

        # per-day breakdown
        daily_rows = conn.execute(
            "SELECT substr(ts,1,10) AS day, "
            "SUM(prompt_tokens) AS prompt_tokens, "
            "SUM(completion_tokens) AS completion_tokens, "
            "SUM(total_tokens) AS total_tokens, "
            "COUNT(*) AS calls "
            "FROM usage GROUP BY day ORDER BY day DESC LIMIT 30"
        ).fetchall()
        daily = [
            {
                "day": r["day"],
                "prompt_tokens": r["prompt_tokens"] or 0,
                "completion_tokens": r["completion_tokens"] or 0,
                "total_tokens": r["total_tokens"] or 0,
                "calls": r["calls"],
            }
            for r in daily_rows
        ]

        # per-route breakdown
        route_rows = conn.execute(
            "SELECT route AS route, "
            "SUM(prompt_tokens) AS prompt_tokens, "
            "SUM(completion_tokens) AS completion_tokens, "
            "SUM(total_tokens) AS total_tokens, "
            "COUNT(*) AS calls "
            "FROM usage GROUP BY route ORDER BY total_tokens DESC"
        ).fetchall()
        by_route = [
            {
                "route": r["route"],
                "prompt_tokens": r["prompt_tokens"] or 0,
                "completion_tokens": r["completion_tokens"] or 0,
                "total_tokens": r["total_tokens"] or 0,
                "calls": r["calls"],
            }
            for r in route_rows
        ]
    finally:
        conn.close()

    return UsageOut(
        today_tokens=today_tokens,
        today_calls=today_calls,
        daily=daily,
        by_route=by_route,
    )
