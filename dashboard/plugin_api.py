"""handoff в интерфейсе Hermes: панель очереди.

Монтируется в `/api/plugins/handoff/`. Ничего не хранит и не решает сам: каждый
запрос — чтение тех же файлов, что у агента и у CLI-бинаря. Панель умеет ровно то,
что умеет шина: показать состояние, опубликовать сообщение, подтвердить (`ack`)
и вернуть (`sweep`) зависшие аренды. Отправлять письма она не может — это не её дело.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import (  # noqa: E402  — импорт после правки sys.path
    ack as core_ack,
    listing,
    post as core_post,
    stats as core_stats,
    sweep as core_sweep,
)

router = APIRouter()


@router.get("/state")
def state() -> dict:
    """Полное состояние: итоги по каналам, плюс содержимое всех состояний."""
    totals = core_stats()
    if not totals.get("success"):
        raise HTTPException(status_code=500, detail=totals.get("error", "cannot read bus"))

    channels = {}
    for name, counts in totals["data"]["channels"].items():
        channels[name] = {
            "counts": counts,
            "messages": {
                state: listing(name, state)["data"]["messages"]
                for state in ("queue", "leased", "dead")
                if counts.get(state, 0) > 0
            },
        }
    return {"home": totals["data"]["home"], "totals": totals["data"]["totals"], "channels": channels}


@router.post("/post")
def publish(payload: dict = Body(...)) -> dict:
    result = core_post(
        channel=str(payload.get("channel", "")),
        key=str(payload.get("key", "")),
        body=str(payload.get("body", "")),
        to=str(payload.get("to", "*")),
        sender=str(payload.get("from", "dashboard")),
        delay=int(payload.get("delay") or 0),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "post failed"))
    return result


@router.post("/ack")
def confirm(payload: dict = Body(...)) -> dict:
    result = core_ack(str(payload.get("channel", "")), str(payload.get("key", "")))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "ack failed"))
    return result


@router.post("/sweep")
def recover(payload: dict = Body(...)) -> dict:
    result = core_sweep(str(payload.get("channel", "")))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "sweep failed"))
    return result
