"""handoff — шина агентов на файловой системе, доступная агенту инструментами.

Зачем плагин, если есть Rust-бинарь: бинарь надо ставить, а шина должна работать
сразу после установки плагина и быть видимой в интерфейсе Hermes. Протокол тот же,
файлы те же — плагин и бинарь читают одну очередь.
"""

from __future__ import annotations

import json

from . import core, schemas


def _result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def register(ctx):
    ctx.register_tool(
        name="handoff_post",
        toolset="handoff",
        schema=schemas.POST,
        handler=lambda args, **kw: _result(core.post(
            channel=args.get("channel", ""),
            key=args.get("key", ""),
            body=args.get("body", ""),
            to=args.get("to", "*"),
            sender=args.get("from", ""),
            delay=int(args.get("delay") or 0),
        )),
        emoji="📤",
        description="Publish a durable message to a handoff channel (idempotent by key)",
    )

    ctx.register_tool(
        name="handoff_take",
        toolset="handoff",
        schema=schemas.TAKE,
        handler=lambda args, **kw: _result(core.take(
            channel=args.get("channel", ""),
            who=args.get("for") or "agent",
            lease=int(args.get("lease") or 300),
        )),
        emoji="🤲",
        description="Claim one message with a lease (exclusive while the lease is alive)",
    )

    ctx.register_tool(
        name="handoff_ack",
        toolset="handoff",
        schema=schemas.ACK,
        handler=lambda args, **kw: _result(core.ack(args.get("channel", ""), args.get("key", ""))),
        emoji="✅",
        description="Finish a leased message (move it to done)",
    )

    ctx.register_tool(
        name="handoff_nack",
        toolset="handoff",
        schema=schemas.NACK,
        handler=lambda args, **kw: _result(core.nack(
            args.get("channel", ""), args.get("key", ""), int(args.get("max_attempts") or 5))),
        emoji="↩️",
        description="Return a message to the queue, or park it in dead after N attempts",
    )

    ctx.register_tool(
        name="handoff_sweep",
        toolset="handoff",
        schema=schemas.SWEEP,
        handler=lambda args, **kw: _result(core.sweep(args.get("channel", ""))),
        emoji="🧹",
        description="Recover messages whose lease expired (a consumer died mid-work)",
    )

    ctx.register_tool(
        name="handoff_list",
        toolset="handoff",
        schema=schemas.LIST,
        handler=lambda args, **kw: _result(core.listing(
            args.get("channel", ""), args.get("state") or "queue")),
        emoji="📋",
        description="List messages in a channel state",
    )

    ctx.register_tool(
        name="handoff_stats",
        toolset="handoff",
        schema=schemas.STATS,
        handler=lambda args, **kw: _result(core.stats()),
        emoji="📊",
        description="Totals per channel and state",
    )

    ctx.register_tool(
        name="handoff_wait",
        toolset="handoff",
        schema=schemas.WAIT,
        handler=lambda args, **kw: _result(core.wait(
            channel=args.get("channel", ""),
            who=args.get("for") or "agent",
            lease=int(args.get("lease") or 300),
            timeout=int(args.get("timeout") or 0),
        )),
        emoji="⏳",
        description="Block briefly until a message arrives, then lease it",
    )
