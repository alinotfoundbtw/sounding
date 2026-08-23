"""One place where an artifact becomes a report.

This existed in three copies — the CLI, the MCP server, and the discovery
walker each had their own detection and dispatch. Three copies of the same
decision is three chances for the CLI and the server to disagree about what a
file is, and that disagreement would surface as "the tool says something
different in Claude than in CI", which is the worst possible bug for a tool
whose product is trustworthiness.
"""

from __future__ import annotations

import re
from pathlib import Path

from .discover import classify
from .loader import load
from .model import Report
from .rules import mcp as mcp_rules
from .rules import prompt as prompt_rules
from .rules import skill as skill_rules
from .skillfile import load_skill

KINDS = ("mcp", "skill", "prompt")


def detect(path: str | Path, forced: str | None = None) -> str:
    """Explicit kind always wins; otherwise classify by shape."""
    if forced and forced in KINDS:
        return forced
    return classify(Path(path))


def report_for(path: str | Path, kind: str | None = None, profile: str | None = None) -> Report:
    p = Path(path)
    resolved = detect(p, kind)

    if resolved == "skill":
        sk = load_skill(p)
        return Report(subject=sk, findings=skill_rules.run_all(sk))

    if resolved == "prompt":
        pr = prompt_rules.load_prompt(p)
        return Report(subject=pr, findings=prompt_rules.run_all(pr, profile))

    servers = load(p)
    if not servers:
        raise ValueError("no server found in that file")
    return Report(subject=servers[0], findings=mcp_rules.run_all(servers[0]))
