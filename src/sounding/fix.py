"""`sounding fix` — turn findings into an actual edit.

Nothing is written without being shown first. The default is a diff; writing
requires --write. A tool that edits your config silently is a tool you stop
trusting the first time it gets something wrong.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from .model import Report
from .patch import FixPlan, Patch, apply


def plan(report: Report, answers: dict[str, str] | None = None) -> FixPlan:
    """Build the set of changes from direct patches plus answered questions."""
    answers = answers or {}
    out = FixPlan()

    for f in report.findings:
        if f.patch:
            out.patches.append(f.patch)

        q = f.question
        if not q:
            continue

        choice = answers.get(q.id)
        if choice is None:
            out.unresolved.append(f"{q.id}: {q.prompt}")
            continue
        if choice in ("skip", "not sure"):
            continue
        if choice in q.outcomes:
            out.patches.extend(q.outcomes[choice])
        else:
            # An answer with no mechanical consequence — the decision is still
            # useful to the human, but there is nothing to write.
            out.unresolved.append(f"{q.id}: answered '{choice}' — no automatic change")

    return out


def render(raw: dict[str, Any]) -> str:
    return json.dumps(raw, indent=2, ensure_ascii=False) + "\n"


def diff(before: dict[str, Any], after: dict[str, Any], name: str = "server.json") -> str:
    a = render(before).splitlines(keepends=True)
    b = render(after).splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(a, b, fromfile=f"a/{name}", tofile=f"b/{name}", n=3)
    )


def write(path: str | Path, raw: dict[str, Any], backup: bool = True) -> Path:
    p = Path(path)
    if backup and p.exists():
        p.with_suffix(p.suffix + ".bak").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    p.write_text(render(raw), encoding="utf-8")
    return p


def summarize(applied: list[Patch]) -> str:
    if not applied:
        return "  nothing to apply"
    lines = []
    for p in applied:
        flag = " TODO" if p.todo else ""
        lines.append(f"  {p.describe()}")
        if p.note:
            lines.append(f"      {p.note}{flag}")
    return "\n".join(lines)
