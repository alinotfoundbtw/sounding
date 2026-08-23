"""sounding as an MCP server.

The tool that audits MCP servers is one. That is not a joke — it is the test.
`sounding selfaudit` runs the rule set against this server's own manifest, and
the test suite fails if it scores below 100. Every constraint the rules ask for
is one this server has to satisfy first.

JSON-RPC 2.0 over stdio, no dependencies.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import MARK, __version__
from . import engine
from . import fix as fix_mod
from .model import Report
from .rules import mcp as mcp_rules
from .rules import prompt as prompt_rules
from .rules import skill as skill_rules
from .loader import load
from .skillfile import load_skill

PROTOCOL_VERSION = "2025-06-18"

KIND_ENUM = ["mcp", "skill", "prompt"]

# --------------------------------------------------------------------------
# Tool manifest
#
# These descriptions are held to the same standard the rules enforce: they say
# what the tool does, when to use it, and when not to. Annotations are explicit.
# Every string parameter is constrained.
# --------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "sounding_audit",
        "description": (
            "Audit an MCP server descriptor, an Agent Skill, or a prompt file and "
            "return findings, a score, and the open questions that would resolve "
            "the remaining issues. Use this when the user asks to review, check, "
            "lint, or improve a SKILL.md, an .mcp.json, a tool definition, or a "
            "system prompt. Static analysis only — nothing is executed or "
            "connected to. Do not use it to audit ordinary source code, which it "
            "knows nothing about."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file or skill directory to audit.",
                    "pattern": "^(?!.*\\.\\.)[^\\x00]{1,4096}$",
                },
                "kind": {
                    "type": "string",
                    "description": "Adapter to use. Omit to detect from the path.",
                    "enum": KIND_ENUM,
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "sounding_answer",
        "description": (
            "Apply answers to the questions returned by sounding_audit and return "
            "the resulting corrections as a unified diff, without writing anything "
            "to disk. Use this after the user has chosen from the options an audit "
            "offered. Do not use it to make edits the audit did not propose — it "
            "only applies known corrections."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path that was audited.",
                    "pattern": "^(?!.*\\.\\.)[^\\x00]{1,4096}$",
                },
                "answers": {
                    "type": "object",
                    "description": (
                        "Map of question id to the exact option text chosen by the "
                        "user. Unanswered questions are reported, never guessed."
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "kind": {"type": "string", "enum": KIND_ENUM},
            },
            "required": ["path", "answers"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "sounding_rules",
        "description": (
            "List the rule set for one artifact kind, with each rule's code and "
            "what it checks, plus the scoring weights. Use this when the user asks "
            "what sounding checks for, or why a particular finding was raised."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": "Which rule set to list.",
                    "enum": KIND_ENUM,
                }
            },
            "required": ["kind"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
]

SERVER_INFO = {"name": "sounding", "version": __version__, "title": f"sounding {MARK}"}


def manifest() -> dict[str, Any]:
    """This server described as a descriptor — the input its own rules take."""
    return {
        "name": "sounding",
        "version": __version__,
        "transport": "stdio",
        "command": "sounding",
        "args": ["serve"],
        "env": {},
        "tools": TOOLS,
    }


# --------------------------------------------------------------------------
# Audit dispatch
# --------------------------------------------------------------------------

def _detect(path: Path, kind: str | None) -> str:
    return engine.detect(path, kind)


def _report_for(path: Path, kind: str) -> Report:
    return engine.report_for(path, kind)


def _audit(args: dict[str, Any]) -> dict[str, Any]:
    path = Path(args["path"])
    kind = _detect(path, args.get("kind"))
    report = _report_for(path, kind)
    payload = report.to_dict()
    payload["kind"] = kind
    payload["scope"] = "static analysis; nothing executed, connected to, or scanned"
    payload["questions"] = [q.to_dict() for q in report.questions()]
    return payload


def _answer(args: dict[str, Any]) -> dict[str, Any]:
    from . import patch as patch_mod

    path = Path(args["path"])
    kind = _detect(path, args.get("kind"))
    report = _report_for(path, kind)
    plan = fix_mod.plan(report, dict(args.get("answers") or {}))

    if kind == "mcp":
        before = load(path)[0].raw
        after, applied = patch_mod.apply(before, plan.patches)
        diff = fix_mod.diff(before, after, name=path.name)
    elif kind == "skill":
        src = load_skill(path).path
        assert src is not None
        before_text = src.read_text(encoding="utf-8")
        after_text, applied = patch_mod.apply_frontmatter(before_text, plan.patches)
        diff = _text_diff(before_text, after_text, src.name)
    else:
        before_text = path.read_text(encoding="utf-8")
        after_text, applied = patch_mod.apply_append(before_text, plan.patches)
        diff = _text_diff(before_text, after_text, path.name)

    return {
        "kind": kind,
        "diff": diff,
        "applied": [p.describe() for p in applied],
        "needs_human": [p.describe() for p in applied if p.todo],
        "unresolved": plan.unresolved,
        "written": False,
        "note": (
            "Nothing was written to disk. Entries under needs_human are scaffolds, "
            "not finished text."
        ),
    }


def _text_diff(before: str, after: str, name: str) -> str:
    import difflib

    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
            n=2,
        )
    )


def _rules(args: dict[str, Any]) -> dict[str, Any]:
    registry = {
        "mcp": mcp_rules.REGISTRY,
        "skill": skill_rules.REGISTRY,
        "prompt": prompt_rules.REGISTRY,
    }[args["kind"]]
    return {
        "kind": args["kind"],
        "rules": [
            {
                "code": code,
                "checks": (fn.__doc__ or fn.__name__.replace("_", " ")).strip().splitlines()[0],
            }
            for code, fn in registry
        ],
        "weights": {"high": 15, "medium": 7, "low": 3},
        "score": "100 - sum(weights), floored at 0",
    }


HANDLERS = {
    "sounding_audit": _audit,
    "sounding_answer": _answer,
    "sounding_rules": _rules,
}


# --------------------------------------------------------------------------
# JSON-RPC
# --------------------------------------------------------------------------

def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    mid = message.get("id")

    if method == "initialize":
        return _ok(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "ping":
        return _ok(mid, {})

    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})

    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        handler = HANDLERS.get(name)
        if handler is None:
            return _err(mid, -32602, f"unknown tool: {name}")
        try:
            result = handler(params.get("arguments") or {})
        except FileNotFoundError as exc:
            return _tool_error(mid, f"not found: {exc}")
        except (OSError, ValueError, KeyError) as exc:
            return _tool_error(mid, f"{type(exc).__name__}: {exc}")
        return _ok(mid, {
            "content": [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}],
            "isError": False,
        })

    if mid is None:
        return None
    return _err(mid, -32601, f"method not found: {method}")


def _ok(mid: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _tool_error(mid: Any, message: str) -> dict[str, Any]:
    """Tool failures are results, not protocol errors — the model should see them."""
    return _ok(mid, {"content": [{"type": "text", "text": message}], "isError": True})


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_err(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        response = handle(message)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
    return 0
