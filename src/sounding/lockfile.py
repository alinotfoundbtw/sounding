"""Pin and diff.

The threat this addresses: a server earns trust, then quietly changes what its
tools claim to do. The tool contract is what the model reads, so a description
change is a behaviour change even when the code is untouched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .model import Server

LOCK_NAME = "sounding.lock.json"


def _digest(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def tool_fingerprints(server: Server) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in server.tools:
        name = t.get("name", "?")
        out[name] = _digest(
            {
                "description": t.get("description", ""),
                "inputSchema": t.get("inputSchema", {}),
                "annotations": t.get("annotations", {}),
            }
        )
    return out


def build(servers: list[Server]) -> dict[str, Any]:
    return {
        "lockfileVersion": 1,
        "servers": {
            s.name: {
                "version": s.version,
                "transport": s.transport,
                "tools": tool_fingerprints(s),
            }
            for s in servers
        },
    }


def write(servers: list[Server], path: str | Path = LOCK_NAME) -> Path:
    p = Path(path)
    p.write_text(json.dumps(build(servers), indent=2) + "\n", encoding="utf-8")
    return p


def read(path: str | Path = LOCK_NAME) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def diff(servers: list[Server], lock: dict[str, Any]) -> list[str]:
    """Returns human-readable drift lines. Empty means nothing moved."""
    out: list[str] = []
    locked = lock.get("servers", {})
    current = build(servers)["servers"]

    for name, cur in current.items():
        old = locked.get(name)
        if old is None:
            out.append(f"+ server {name} is not in the lockfile")
            continue
        if old.get("version") != cur.get("version"):
            out.append(
                f"~ {name}: version {old.get('version') or '(none)'} "
                f"-> {cur.get('version') or '(none)'}"
            )
        old_tools, cur_tools = old.get("tools", {}), cur.get("tools", {})
        for tname, tfp in cur_tools.items():
            if tname not in old_tools:
                out.append(f"+ {name}.{tname} added")
            elif old_tools[tname] != tfp:
                out.append(
                    f"! {name}.{tname} contract changed "
                    f"({old_tools[tname]} -> {tfp})"
                )
        for tname in old_tools:
            if tname not in cur_tools:
                out.append(f"- {name}.{tname} removed")

    for name in locked:
        if name not in current:
            out.append(f"- server {name} no longer present")
    return out
