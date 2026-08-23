"""Load a server descriptor.

Accepts three shapes, because these are what people actually have on disk:

1. A tools/list response:      {"tools": [...]}
2. A full descriptor:          {"name":..., "transport":..., "tools":[...]}
3. A client config file:       {"mcpServers": {"name": {...}}}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import Server


def _text(value: Any) -> str:
    """Coerce to string. Descriptors in the wild carry numbers and nulls."""
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _sanitize_tools(raw: Any, problems: list[str]) -> list[dict[str, Any]]:
    """Drop what cannot be a tool, and record why.

    A linter that crashes on a malformed file is useless precisely when it is
    most needed — malformed files are the ones worth checking. Structural
    problems become findings, never exceptions.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        problems.append(f"`tools` is {type(raw).__name__}, expected a list")
        return []

    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            problems.append(f"tools[{i}] is {type(item).__name__}, expected an object")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"tools[{i}] has no usable `name`")
            continue

        clean: dict[str, Any] = {"name": name}
        desc = item.get("description")
        if desc is not None and not isinstance(desc, str):
            problems.append(f"tools[{name}].description is {type(desc).__name__}, expected a string")
        clean["description"] = _text(desc)

        schema = item.get("inputSchema")
        if schema is not None and not isinstance(schema, dict):
            problems.append(f"tools[{name}].inputSchema is {type(schema).__name__}, expected an object")
            schema = None
        if isinstance(schema, dict):
            props = schema.get("properties")
            if props is not None and not isinstance(props, dict):
                problems.append(f"tools[{name}].inputSchema.properties is not an object")
                schema = {**schema, "properties": {}}
            elif isinstance(props, dict):
                bad = [k for k, v in props.items() if not isinstance(v, dict)]
                for k in bad:
                    problems.append(f"tools[{name}].inputSchema.properties.{k} is not an object")
                if bad:
                    schema = {**schema, "properties": {k: v for k, v in props.items() if k not in bad}}
            clean["inputSchema"] = schema

        ann = item.get("annotations")
        if ann is not None and not isinstance(ann, dict):
            problems.append(f"tools[{name}].annotations is {type(ann).__name__}, expected an object")
            ann = None
        if isinstance(ann, dict):
            clean["annotations"] = ann

        out.append(clean)
    return out


def _sanitize_env(raw: Any, problems: list[str]) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        problems.append(f"`env` is {type(raw).__name__}, expected an object")
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str):
            problems.append(f"env has a non-string key ({type(k).__name__})")
            continue
        out[k] = _text(v)
    return out


def _server_from_entry(name: str, entry: dict[str, Any]) -> Server:
    problems: list[str] = []
    if not isinstance(entry, dict):
        return Server(name=name, malformed=[f"entry is {type(entry).__name__}, expected an object"])

    url = _text(entry.get("url"))
    transport = _text(entry.get("transport")) or ("http" if url else "stdio")
    args = entry.get("args")
    if args is not None and not isinstance(args, list):
        problems.append(f"`args` is {type(args).__name__}, expected a list")
        args = []

    return Server(
        name=_text(entry.get("name")) or name,
        version=_text(entry.get("version")),
        transport=transport,
        url=url,
        command=_text(entry.get("command")),
        args=[_text(a) for a in (args or [])],
        env=_sanitize_env(entry.get("env"), problems),
        tools=_sanitize_tools(entry.get("tools"), problems),
        resources=list(entry.get("resources") or []) if isinstance(entry.get("resources"), list) else [],
        prompts=list(entry.get("prompts") or []) if isinstance(entry.get("prompts"), list) else [],
        raw=entry,
        malformed=problems,
    )


def load(path: str | Path) -> list[Server]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object at the top level.")

    if "mcpServers" in data and isinstance(data["mcpServers"], dict):
        return [_server_from_entry(n, e) for n, e in data["mcpServers"].items()]

    name = data.get("name") or Path(path).stem
    return [_server_from_entry(name, data)]
