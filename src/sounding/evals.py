"""Evaluation — the part determinism cannot fully answer, answered honestly.

**What this measures.** Whether a skill's description would be selected for the
tasks it is meant to handle, and whether it collides with its neighbours. That
is a retrieval problem over the descriptions, and retrieval can be measured
without a model.

**What this does not measure.** Whether the skill's *instructions* work once it
fires. That needs a model, and this tool runs nothing. Every number here is
about selection, and the report says so.

**Why the proxy is worth having anyway.** A skill that never fires is worth
nothing regardless of how good its body is, and description collisions are the
most common reason skills misfire in a populated environment. This finds those
offline, in milliseconds, with no API key.

The scorer is BM25 over description terms — the same family of lexical
retrieval that underlies most first-pass tool selection. It will disagree with
a real model at the margins. It is a smoke test, not an oracle, and it is
labelled as one everywhere it appears.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "how", "in", "is", "it", "its", "of", "on", "or", "that", "the", "this", "to",
    "use", "used", "using", "was", "when", "which", "with", "you", "your", "user",
    "skill", "asks", "ask", "want", "wants", "need", "needs", "should", "can",
    "will", "do", "does", "make", "get", "if", "not", "any", "all", "also",
}

K1 = 1.5
B = 0.75


def tokens(text: str) -> list[str]:
    """Lowercase word tokens, stemmed just enough to match plurals and gerunds."""
    raw = re.findall(r"[a-z0-9][a-z0-9+.#_-]*", text.lower())
    out = []
    for w in raw:
        if w in STOPWORDS or len(w) < 2:
            continue
        for suffix in ("ing", "ies", "es", "s"):
            if len(w) > 4 and w.endswith(suffix):
                w = w[: -len(suffix)] + ("y" if suffix == "ies" else "")
                break
        out.append(w)
    return out


@dataclass
class Candidate:
    name: str
    description: str
    path: str = ""
    terms: Counter = field(default_factory=Counter)

    def __post_init__(self) -> None:
        if not self.terms:
            self.terms = Counter(tokens(self.description))

    @property
    def length(self) -> int:
        return sum(self.terms.values()) or 1


class Index:
    """BM25 over candidate descriptions."""

    def __init__(self, candidates: list[Candidate]) -> None:
        self.candidates = candidates
        self.n = len(candidates) or 1
        self.avg_len = sum(c.length for c in candidates) / self.n if candidates else 1.0
        self.df: Counter = Counter()
        for c in candidates:
            for term in c.terms:
                self.df[term] += 1

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def score(self, task: str, candidate: Candidate) -> float:
        total = 0.0
        for term in tokens(task):
            tf = candidate.terms.get(term, 0)
            if not tf:
                continue
            denom = tf + K1 * (1 - B + B * candidate.length / self.avg_len)
            total += self._idf(term) * (tf * (K1 + 1)) / denom
        return total

    def rank(self, task: str) -> list[tuple[Candidate, float]]:
        scored = [(c, self.score(task, c)) for c in self.candidates]
        scored.sort(key=lambda x: (-x[1], x[0].name))
        return scored


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------

@dataclass
class Case:
    task: str
    expect: str


@dataclass
class Outcome:
    case: Case
    chosen: str
    score: float
    runner_up: str
    runner_score: float

    @property
    def correct(self) -> bool:
        return self.chosen == self.case.expect

    @property
    def unmatched(self) -> bool:
        return self.score <= 0.0

    @property
    def margin(self) -> float:
        return self.score - self.runner_score

    @property
    def ambiguous(self) -> bool:
        """A win this narrow is a coin flip, not a selection."""
        return self.correct and not self.unmatched and self.margin < 0.15 * self.score


@dataclass
class EvalReport:
    outcomes: list[Outcome]
    collisions: list[tuple[str, str, float]]
    candidates: int

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.correct and not o.ambiguous)

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def failures(self) -> list[Outcome]:
        return [o for o in self.outcomes if not o.correct]

    def ambiguous(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.ambiguous]

    def unmatched(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.unmatched]

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": "BM25 lexical retrieval over descriptions",
            "measures": "trigger selection only, not whether instructions work",
            "candidates": self.candidates,
            "cases": self.total,
            "passed": self.passed,
            "accuracy": round(self.accuracy, 3),
            "failures": [
                {
                    "task": o.case.task,
                    "expected": o.case.expect,
                    "chose": o.chosen if not o.unmatched else None,
                }
                for o in self.failures()
            ],
            "ambiguous": [
                {"task": o.case.task, "winner": o.chosen, "runner_up": o.runner_up}
                for o in self.ambiguous()
            ],
            "collisions": [
                {"a": a, "b": b, "overlap": round(v, 3)} for a, b, v in self.collisions
            ],
        }


def run(candidates: list[Candidate], cases: list[Case]) -> EvalReport:
    index = Index(candidates)
    outcomes: list[Outcome] = []
    for case in cases:
        ranked = index.rank(case.task)
        top, top_score = ranked[0] if ranked else (Candidate("", ""), 0.0)
        second, second_score = ranked[1] if len(ranked) > 1 else (Candidate("", ""), 0.0)
        outcomes.append(
            Outcome(
                case=case,
                chosen=top.name if top_score > 0 else "",
                score=top_score,
                runner_up=second.name,
                runner_score=second_score,
            )
        )
    return EvalReport(
        outcomes=outcomes,
        collisions=collisions(candidates),
        candidates=len(candidates),
    )


def collisions(candidates: list[Candidate], threshold: float = 0.55) -> list[tuple[str, str, float]]:
    """Pairs whose descriptions compete for the same vocabulary.

    Runs without any cases at all, which makes it the cheapest useful check
    here: point it at a skills directory and it reports which ones will fight.
    """
    out: list[tuple[str, str, float]] = []
    for i, a in enumerate(candidates):
        for b in candidates[i + 1 :]:
            sa, sb = set(a.terms), set(b.terms)
            if not sa or not sb:
                continue
            overlap = len(sa & sb) / len(sa | sb)
            if overlap >= threshold:
                out.append((a.name, b.name, overlap))
    out.sort(key=lambda x: -x[2])
    return out


# --------------------------------------------------------------------------
# Case files
# --------------------------------------------------------------------------

def load_cases(path: str | Path) -> list[Case]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw.get("cases", raw) if isinstance(raw, dict) else raw
    cases: list[Case] = []
    for item in items:
        if not isinstance(item, dict) or "task" not in item or "expect" not in item:
            continue
        cases.append(Case(task=str(item["task"]), expect=str(item["expect"])))
    return cases


def scaffold(candidates: list[Candidate]) -> dict[str, Any]:
    """Generate a starting case file from the descriptions themselves.

    These are TODO stubs on purpose. Cases derived from a description only
    prove the description matches itself — the value comes from writing the
    phrasings a real user would type, which the tool cannot invent.
    """
    cases = []
    for c in candidates:
        terms = [t for t, _ in Counter(tokens(c.description)).most_common(4)]
        cases.append(
            {
                "task": "TODO: how a user would actually phrase this — "
                + " ".join(terms),
                "expect": c.name,
            }
        )
    return {
        "note": (
            "Replace every TODO with real user phrasing. A case copied from the "
            "description only proves the description matches itself."
        ),
        "cases": cases,
    }
