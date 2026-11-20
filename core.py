"""handoff — ядро шины агентов на файловой системе.

Тот же протокол, что у Rust-бинаря `handoff` (tools/handoff): каталоги состояний,
сообщение как файл `key=value` + тело, переходы через атомарный `rename`.
Файлы совместимы: плагин и бинарь читают и пишут одну и ту же очередь.

Состояния: `queue` → `leased` → `done`, плюс `dead` после N отказов и `sweep`,
который возвращает сообщения от умерших получателей.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

STATES = ("queue", "leased", "done", "dead")
KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,120}")
CHANNEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,60}")


def base_dir() -> Path:
    """Каталог шины. `HANDOFF_HOME` перекрывает путь — так канал делят профили."""
    explicit = os.environ.get("HANDOFF_HOME")
    if explicit:
        return Path(explicit).expanduser()
    return Path.home() / ".local/share/handoff"


def channel_dir(channel: str) -> Path:
    return base_dir() / "channels" / channel


def ensure_dirs(channel: str) -> Path:
    root = channel_dir(channel)
    for state in STATES:
        (root / state).mkdir(parents=True, exist_ok=True)
    return root


def now() -> int:
    return int(time.time())


def _valid_channel(channel: str) -> bool:
    return bool(CHANNEL_RE.fullmatch(channel or ""))


def _valid_key(key: str) -> bool:
    return bool(KEY_RE.fullmatch(key or ""))


def render(message: dict[str, Any]) -> str:
    return (
        f"key={message['key']}\n"
        f"from={message['from']}\n"
        f"to={message['to']}\n"
        f"created={message['created']}\n"
        f"attempts={message['attempts']}\n"
        f"lease_until={message['lease_until']}\n\n"
        f"{message['body']}\n"
    )


def parse(text: str) -> dict[str, Any] | None:
    head, _, body = text.partition("\n\n")
    fields: dict[str, str] = {}
    for line in head.splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            fields[name.strip()] = value.strip()
    if "key" not in fields:
        return None
    return {
        "key": fields["key"],
        "from": fields.get("from", "unknown"),
        "to": fields.get("to", "*"),
        "created": int(fields.get("created") or 0),
        "attempts": int(fields.get("attempts") or 0),
        "lease_until": int(fields.get("lease_until") or 0),
        "body": body.rstrip("\n"),
    }


def read(path: Path) -> dict[str, Any] | None:
    try:
        return parse(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def write_atomic(target: Path, message: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(f".tmp{os.getpid()}")
    temp.write_text(render(message), encoding="utf-8")
    os.replace(temp, target)


def post(channel: str, key: str, body: str, to: str = "*", sender: str = "", delay: int = 0) -> dict[str, Any]:
    if not _valid_channel(channel):
        return {"success": False, "error": "invalid channel name"}
    if not _valid_key(key):
        return {"success": False, "error": "invalid key: letters, digits, . _ : - only"}
    body = (body or "").strip()
    if not body:
        return {"success": False, "error": "empty message body"}

    root = ensure_dirs(channel)
    if any((root / state / f"{key}.msg").exists() for state in STATES):
        return {"success": True, "data": {"key": key, "duplicate": True,
                                          "note": "already known — nothing posted (idempotent)"}}

    message = {
        "key": key,
        "from": sender or os.environ.get("USER") or "agent",
        "to": to or "*",
        "created": now() + max(0, int(delay or 0)),
        "attempts": 0,
        "lease_until": 0,
        "body": body,
    }
    write_atomic(root / "queue" / f"{key}.msg", message)
    return {"success": True, "data": {"key": key, "channel": channel, "to": message["to"], "duplicate": False}}


def take(channel: str, who: str, lease: int = 300) -> dict[str, Any]:
    if not _valid_channel(channel):
        return {"success": False, "error": "invalid channel name"}
    root = ensure_dirs(channel)
    candidates: list[tuple[int, Path]] = []
    for path in sorted((root / "queue").glob("*.msg")):
        message = read(path)
        if not message or message["created"] > now():
            continue
        if message["to"] not in ("*", who):
            continue
        candidates.append((message["created"], path))
    candidates.sort(key=lambda item: item[0])

    for _, path in candidates:
        leased = root / "leased" / path.name
        try:
            os.replace(path, leased)  # атомарный захват: выигрывает ровно один
        except OSError:
            continue
        message = read(leased)
        if not message:
            continue
        message["lease_until"] = now() + max(1, int(lease or 300))
        message["attempts"] += 1
        write_atomic(leased, message)
        return {"success": True, "data": message}

    return {"success": True, "data": None, "note": f"nothing to take for {who} in {channel}"}


def ack(channel: str, key: str) -> dict[str, Any]:
    root = ensure_dirs(channel)
    leased = root / "leased" / f"{key}.msg"
    if not leased.exists():
        return {"success": False, "error": f"{key} is not leased (never taken, or already acked)"}
    os.replace(leased, root / "done" / f"{key}.msg")
    return {"success": True, "data": {"key": key, "state": "done"}}


def nack(channel: str, key: str, max_attempts: int = 5) -> dict[str, Any]:
    root = ensure_dirs(channel)
    leased = root / "leased" / f"{key}.msg"
    message = read(leased)
    if not message:
        return {"success": False, "error": f"{key} is not leased"}
    if message["attempts"] >= max(1, int(max_attempts or 5)):
        os.replace(leased, root / "dead" / f"{key}.msg")
        return {"success": True, "data": {"key": key, "state": "dead", "attempts": message["attempts"]}}
    message["lease_until"] = 0
    message["created"] = now()
    write_atomic(root / "queue" / f"{key}.msg", message)
    leased.unlink(missing_ok=True)
    return {"success": True, "data": {"key": key, "state": "queue", "attempts": message["attempts"]}}


def sweep(channel: str) -> dict[str, Any]:
    root = ensure_dirs(channel)
    returned: list[str] = []
    for path in sorted((root / "leased").glob("*.msg")):
        message = read(path)
        if not message or message["lease_until"] > now():
            continue
        message["lease_until"] = 0
        message["created"] = now()
        write_atomic(root / "queue" / path.name, message)
        path.unlink(missing_ok=True)
        returned.append(message["key"])
    return {"success": True, "data": {"returned": returned, "count": len(returned)}}


def listing(channel: str, state: str = "queue") -> dict[str, Any]:
    if state not in STATES:
        return {"success": False, "error": f"state must be one of {', '.join(STATES)}"}
    root = ensure_dirs(channel)
    items = []
    for path in sorted((root / state).glob("*.msg")):
        message = read(path)
        if not message:
            continue
        if message["lease_until"] > now():
            note = f"leased for {message['lease_until'] - now()}s"
        elif message["created"] > now():
            note = f"due in {message['created'] - now()}s"
        else:
            note = "ready"
        items.append({
            "key": message["key"],
            "to": message["to"],
            "from": message["from"],
            "attempts": message["attempts"],
            "note": note,
            "body": message["body"],
        })
    return {"success": True, "data": {"channel": channel, "state": state, "count": len(items), "messages": items}}


def stats() -> dict[str, Any]:
    channels_root = base_dir() / "channels"
    totals = {state: 0 for state in STATES}
    channels: dict[str, dict[str, int]] = {}
    if channels_root.is_dir():
        for channel in sorted(channels_root.iterdir()):
            if not channel.is_dir():
                continue
            counts = {}
            for state in STATES:
                count = len(list((channel / state).glob("*.msg"))) if (channel / state).is_dir() else 0
                counts[state] = count
                totals[state] += count
            channels[channel.name] = counts
    return {"success": True, "data": {"totals": totals, "channels": channels, "home": str(base_dir())}}


def wait(channel: str, who: str, lease: int = 300, timeout: int = 0) -> dict[str, Any]:
    # timeout=0 — одна немедленная проверка. Иначе инструмент в чате висел бы вечно.
    if not timeout:
        result = take(channel, who, lease)
        if result.get("data"):
            return result
        return {"success": True, "data": None, "note": f"nothing to take for {who} in {channel}"}
    deadline = now() + int(timeout)
    while True:
        result = take(channel, who, lease)
        if result.get("data"):
            return result
        if deadline and now() >= deadline:
            return {"success": True, "data": None, "note": f"timeout after {timeout}s"}
        time.sleep(0.2)
