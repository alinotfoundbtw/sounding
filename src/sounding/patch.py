"""Corrections as data.

A finding says what is wrong. A patch says exactly what to change, as a value
rather than as prose, so it can be applied, shown as a diff, or refused.

Two kinds:
  direct  — the correction is unambiguous, attached to the finding itself
  answered — the correction depends on intent, attached to a question option

Anything generated that a human still needs to finish is marked TODO in the
output. The tool does not invent prose and present it as done.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Patch:
    """A single change to a server descriptor.

    target is one of:
      "server"      — field_path applies to the top-level object
      "env"         — field_path is [KEY]
      "tool"        — tool_name selects the tool, field_path applies inside it
      "frontmatter" — field_path is [KEY] in a SKILL.md frontmatter block
    """

    target: str
    field_path: list[str]
    value: Any
    note: str = ""
    tool_name: str = ""
    todo: bool = False  # generated scaffold; needs a human to finish

    def describe(self) -> str:
        where = {
            "server": "",
            "env": "env.",
            "tool": f"tools[{self.tool_name}].",
            "frontmatter": "frontmatter.",
        }.get(self.target, "")
        path = where + ".".join(self.field_path)
        flag = "  (TODO: finish this)" if self.todo else ""
        return f"{path} = {self.value!r}{flag}"


def _set_in(obj: dict[str, Any], path: list[str], value: Any) -> None:
    cur = obj
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[path[-1]] = value


def apply(raw: dict[str, Any], patches: list[Patch]) -> tuple[dict[str, Any], list[Patch]]:
    """Returns (new descriptor, patches that actually applied)."""
    out = copy.deepcopy(raw)
    applied: list[Patch] = []

    for p in patches:
        if p.target == "server":
            _set_in(out, p.field_path, p.value)
            applied.append(p)

        elif p.target == "env":
            env = out.setdefault("env", {})
            if not isinstance(env, dict):
                continue
            _set_in(env, p.field_path, p.value)
            applied.append(p)

        elif p.target == "tool":
            tools = out.get("tools")
            if not isinstance(tools, list):
                continue
            for t in tools:
                if isinstance(t, dict) and t.get("name") == p.tool_name:
                    _set_in(t, p.field_path, p.value)
                    applied.append(p)
                    break

    return out, applied


@dataclass
class FixPlan:
    """What would change, and what still needs a person."""

    patches: list[Patch] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    @property
    def todo_count(self) -> int:
        return sum(1 for p in self.patches if p.todo)


def apply_frontmatter(text: str, patches: list[Patch]) -> tuple[str, list[Patch]]:
    """Rewrite a SKILL.md frontmatter block in place.

    Only touches the fenced block at the top. Body text is never rewritten —
    prose is the author's, and a linter that edits prose is a linter people
    stop running.
    """
    fm_patches = [p for p in patches if p.target == "frontmatter"]
    if not fm_patches:
        return text, []

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text, []
    try:
        close = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return text, []

    block = lines[1:close]
    applied: list[Patch] = []

    for p in fm_patches:
        key = p.field_path[0]
        value = p.value
        rendered = f"{key}: {value}\n"
        for i, line in enumerate(block):
            if line.split(":", 1)[0].strip() == key:
                block[i] = rendered
                # drop folded continuation lines belonging to the old value
                j = i + 1
                while j < len(block) and block[j][:1] in (" ", "\t"):
                    block.pop(j)
                applied.append(p)
                break
        else:
            block.append(rendered)
            applied.append(p)

    return "".join(lines[:1] + block + lines[close:]), applied


def apply_append(text: str, patches: list[Patch]) -> tuple[str, list[Patch]]:
    """Append clauses to a prompt.

    Existing wording is never rewritten. New instructions are added at the end
    under a marked heading so it is obvious what came from the tool.
    """
    adds = [p for p in patches if p.target == "append"]
    if not adds:
        return text, []
    block = ["", "", "<!-- added by sounding -->"]
    for p in adds:
        block.append(p.value)
        block.append("")
    return text.rstrip() + "\n".join(block).rstrip() + "\n", adds
