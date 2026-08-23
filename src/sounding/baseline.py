"""Baseline and SARIF.

**Baseline** exists because of how linters die in real repos: someone runs one
on an existing codebase, gets four hundred findings, and switches it off. A
baseline records what is already there so CI fails on *new* problems only, and
the existing ones become a list to work through rather than a wall.

**SARIF** puts findings in GitHub's Security tab, where they show up as
annotations on the pull request that introduced them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .model import Finding, Severity

BASELINE_NAME = ".sounding-baseline.json"


def fingerprint(path: str, finding: Finding) -> str:
    """Stable across line moves and reworded messages.

    Deliberately excludes the message text — a finding should not reappear as
    "new" because the rule's wording improved.
    """
    blob = f"{path}|{finding.rule}|{finding.subject}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass
class Baseline:
    accepted: set[str]
    path: Path | None = None
    created: str = ""

    @classmethod
    def load(cls, path: str | Path = BASELINE_NAME) -> "Baseline":
        p = Path(path)
        if not p.exists():
            return cls(accepted=set())
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(accepted=set(), path=p)
        return cls(
            accepted=set(raw.get("accepted") or []),
            path=p,
            created=raw.get("created", ""),
        )

    @classmethod
    def build(cls, entries: list[tuple[str, Finding]]) -> dict[str, Any]:
        return {
            "version": 1,
            "tool": f"sounding {__version__}",
            "note": (
                "Findings recorded here are suppressed. They are a backlog, not a "
                "pass — remove entries as they are fixed."
            ),
            "accepted": sorted({fingerprint(p, f) for p, f in entries}),
        }

    def filter(self, path: str, findings: list[Finding]) -> tuple[list[Finding], int]:
        """Returns (new findings, count suppressed)."""
        if not self.accepted:
            return findings, 0
        kept = [f for f in findings if fingerprint(path, f) not in self.accepted]
        return kept, len(findings) - len(kept)


# --------------------------------------------------------------------------
# SARIF 2.1.0
# --------------------------------------------------------------------------

_SARIF_LEVEL = {
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
}


def sarif(results: list[tuple[str, str, list[Finding]]]) -> str:
    """results: list of (path, kind, findings)."""
    rules: dict[str, dict[str, Any]] = {}
    sarif_results: list[dict[str, Any]] = []

    for path, kind, findings in results:
        for f in findings:
            if f.rule not in rules:
                rules[f.rule] = {
                    "id": f.rule,
                    "name": f.rule,
                    "shortDescription": {"text": f.reference},
                    "fullDescription": {"text": f.reference},
                    "defaultConfiguration": {"level": _SARIF_LEVEL[f.severity]},
                    "properties": {"kind": kind, "tags": ["agent-instructions", kind]},
                }
            entry: dict[str, Any] = {
                "ruleId": f.rule,
                "level": _SARIF_LEVEL[f.severity],
                "message": {"text": f.message},
                "partialFingerprints": {"soundingFingerprint": fingerprint(path, f)},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": path.replace("\\", "/")},
                            "region": {"startLine": _line_of(f)},
                        }
                    }
                ],
            }
            if f.fix:
                entry["message"]["text"] += f"\n\nFix: {f.fix}"
            elif f.question:
                entry["message"]["text"] += f"\n\nNeeds a decision: {f.question.prompt}"
            sarif_results.append(entry)

    return json.dumps(
        {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "sounding",
                            "version": __version__,
                            "informationUri": "https://github.com/alinotfoundbtw/sounding",
                            "rules": list(rules.values()),
                        }
                    },
                    "results": sarif_results,
                }
            ],
        },
        indent=2,
    )


def _line_of(f: Finding) -> int:
    """Best-effort line number; subjects carry one when the rule knows it."""
    import re

    m = re.search(r"line (\d+)", f.subject)
    return int(m.group(1)) if m else 1
