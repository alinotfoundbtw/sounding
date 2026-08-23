"""Rendering.

Two rules held throughout:
  - No finding is shown without its reference.
  - The score always shows its formula. A number you cannot audit is a vibe.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys

from . import MARK, __version__
from .model import Report, Severity

_ANSI = {
    "abyss": "\033[38;5;235m",
    "signal": "\033[38;5;33m",
    "ping": "\033[38;5;80m",
    "flare": "\033[38;5;214m",
    "drift": "\033[38;5;103m",
    "surface": "\033[38;5;255m",
    "bold": "\033[1m",
    "off": "\033[0m",
}

_MARK_COLOR = {
    Severity.HIGH: "flare",
    Severity.MEDIUM: "signal",
    Severity.LOW: "drift",
}


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _c(text: str, key: str, color: bool) -> str:
    if not color:
        return text
    return f"{_ANSI[key]}{text}{_ANSI['off']}"


def _stamp() -> str:
    now = _dt.datetime.now(_dt.timezone.utc)
    return now.strftime("%Y.%m.%d · %H:%MZ")


def terminal(report: Report, color: bool | None = None) -> str:
    color = _supports_color() if color is None else color
    s = report.subject
    lines: list[str] = []

    lines.append("")
    lines.append(
        f"{_c(MARK, 'signal', color)}  "
        f"{_c(s.name or '(unnamed)', 'surface', color)}"
        + (f"  {_c(s.version, 'drift', color)}" if s.version else "")
    )
    lines.append("")

    if not report.findings:
        lines.append(f"  {_c('NO CONTACTS', 'drift', color)}")
        lines.append(f"  {_c('Nothing flagged. This is a clean sounding.', 'drift', color)}")
    else:
        for f in report.findings:
            tag = f.severity.value.upper().ljust(6)
            lines.append(
                f"  {_c(tag, _MARK_COLOR[f.severity], color)} "
                f"{_c(f.rule, 'drift', color)}  "
                f"{_c(f.subject, 'ping', color)}"
            )
            lines.append(f"         {f.message}")
            lines.append(f"         {_c('ref', 'drift', color)}  {f.reference}")
            if f.fix:
                lines.append(f"         {_c('fix', 'drift', color)}  {f.fix}")
            lines.append("")

    counts = report.counts()
    lines.append(
        f"  {_c('score', 'drift', color)}  "
        f"{_c(str(report.score), 'surface', color)}/100"
        f"   {_c(report.formula, 'drift', color)}"
    )
    lines.append(
        f"  {_c('found', 'drift', color)}  "
        f"{counts['high']} high · {counts['medium']} medium · {counts['low']} low"
    )

    questions = report.questions()
    if questions:
        lines.append("")
        lines.append(f"  {_c('Three questions would let me write the fixes:', 'surface', color)}")
        for i, q in enumerate(questions, 1):
            lines.append(f"    {i}. {q.prompt}")
            opts = q.options + (["not sure", "skip"] if q.allow_unknown else [])
            lines.append(f"       {_c(' / '.join(opts), 'drift', color)}")
        lines.append("")
        lines.append(f"  {_c('Run with --interactive to answer them.', 'drift', color)}")

    lines.append("")
    lines.append(
        _c(f"{MARK} sounding {__version__} · {_stamp()}", "drift", color)
    )
    lines.append("")
    return "\n".join(lines)


def markdown(report: Report) -> str:
    s = report.subject
    counts = report.counts()
    out: list[str] = []
    out.append(f"# Sounding — {s.name or 'unnamed'}")
    out.append("")
    out.append(f"**Score {report.score}/100** — `{report.formula}`")
    out.append("")
    out.append(
        f"{counts['high']} high · {counts['medium']} medium · {counts['low']} low"
    )
    out.append("")
    out.append(
        "Static analysis only. Nothing was executed, connected to, or scanned. "
        "Findings describe what the artifact declares, not runtime behaviour."
    )
    out.append("")

    if not report.findings:
        out.append("## NO CONTACTS")
        out.append("")
        out.append("Nothing flagged against the current rule set.")
    else:
        for sev in (Severity.HIGH, Severity.MEDIUM, Severity.LOW):
            group = [f for f in report.findings if f.severity is sev]
            if not group:
                continue
            out.append(f"## {sev.value.title()}")
            out.append("")
            for f in group:
                out.append(f"### `{f.rule}` — {f.subject}")
                out.append("")
                out.append(f.message)
                out.append("")
                out.append(f"**Why:** {f.reference}")
                if f.fix:
                    out.append("")
                    out.append(f"**Fix:** {f.fix}")
                if f.question:
                    out.append("")
                    out.append(f"**Needs a decision:** {f.question.prompt}")
                out.append("")

    questions = report.questions()
    if questions:
        out.append("## Open questions")
        out.append("")
        for q in questions:
            opts = q.options + (["not sure", "skip"] if q.allow_unknown else [])
            out.append(f"- {q.prompt}")
            out.append(f"  - {' / '.join(opts)}")
        out.append("")

    out.append("---")
    out.append("")
    out.append(f"<sub>`{MARK}` sounding {__version__} · {_stamp()}</sub>")
    out.append("")
    return "\n".join(out)


def as_json(report: Report) -> str:
    payload = report.to_dict()
    payload["tool"] = {"name": "sounding", "version": __version__, "mark": MARK}
    payload["generated"] = _stamp()
    payload["scope"] = "static analysis of declared tool contract; nothing executed"
    return json.dumps(payload, indent=2, ensure_ascii=False)
