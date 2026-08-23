"""Core types.

Every finding carries three things, always:
  what   - the finding itself
  why    - a reference to an authoritative source
  fix    - either a direct correction, or a question whose answer produces one

A finding without a reference is an opinion. This tool does not ship opinions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .patch import Patch


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def weight(self) -> int:
        return {"high": 15, "medium": 7, "low": 3}[self.value]


@dataclass
class Question:
    """Asked only when the fix depends on intent the tool cannot infer."""

    id: str
    prompt: str
    options: list[str]
    allow_unknown: bool = True
    applies_to: str = ""
    # option label -> patches produced by choosing it
    outcomes: dict[str, list["Patch"]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        opts = list(self.options)
        if self.allow_unknown:
            opts = opts + ["not sure", "skip"]
        return {
            "id": self.id,
            "prompt": self.prompt,
            "options": opts,
            "applies_to": self.applies_to,
        }


@dataclass
class Finding:
    rule: str
    severity: Severity
    subject: str          # which tool / field this is about
    message: str          # what is wrong
    reference: str        # why it matters — spec section or doc
    fix: str | None = None            # direct correction, when unambiguous
    question: Question | None = None  # asked, when intent is required
    patch: "Patch | None" = None      # applied by `sounding fix`, no input needed

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "subject": self.subject,
            "message": self.message,
            "reference": self.reference,
            "fix": self.fix,
            "question": self.question.to_dict() if self.question else None,
            "patch": self.patch.describe() if self.patch else None,
        }


@dataclass
class Server:
    """A server descriptor: the result of tools/list plus transport metadata."""

    kind: str = "mcp"
    name: str = ""
    version: str = ""
    transport: str = ""
    url: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    malformed: list[str] = field(default_factory=list)


@dataclass
class Artifact:
    """Anything that can be audited: an MCP server, a skill, a prompt.

    All three are the same thing underneath — text handed to a model, living
    in a repo, versioned, drifting, carrying an injection surface.
    """

    name: str = ""
    version: str = ""
    kind: str = ""


@dataclass
class Report:
    subject: Any
    findings: list[Finding]

    @property
    def score(self) -> int:
        penalty = sum(f.severity.weight for f in self.findings)
        return max(0, 100 - penalty)

    @property
    def formula(self) -> str:
        counts = {s: 0 for s in Severity}
        for f in self.findings:
            counts[f.severity] += 1
        parts = [
            f"{counts[s]}x{s.value}({s.weight})" for s in Severity if counts[s]
        ] or ["no findings"]
        return f"100 - [{' + '.join(parts)}] = {self.score}"

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in Severity}
        for f in self.findings:
            out[f.severity.value] += 1
        return out

    def questions(self, limit: int = 3) -> list[Question]:
        """Highest-impact questions first. Never overwhelm — three is the cap."""
        order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
        ranked = sorted(
            (f for f in self.findings if f.question),
            key=lambda f: order[f.severity],
        )
        seen: set[str] = set()
        out: list[Question] = []
        for f in ranked:
            q = f.question
            assert q is not None
            if q.id in seen:
                continue
            seen.add(q.id)
            out.append(q)
            if len(out) >= limit:
                break
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": getattr(self.subject, "name", ""),
            "kind": getattr(self.subject, "kind", "mcp"),
            "version": getattr(self.subject, "version", ""),
            "score": self.score,
            "formula": self.formula,
            "counts": self.counts(),
            "findings": [f.to_dict() for f in self.findings],
        }
