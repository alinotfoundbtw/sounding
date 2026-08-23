"""Deterministic rules for prompts.

Scope, stated up front: this checks what can be checked by reading. Whether a
prompt actually *works* can only be found by running it, and this tool does not
run anything. What it catches is the structural class of problem — the missing
specification, the contradiction, the unguarded interpolation — which is where
most prompt failures actually come from.

No model is used. Same input, same output, every time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..model import Finding, Question, Severity
from ..patch import Patch

G_FORMAT = "An unspecified output format is filled in differently on each run"
G_FAILURE = "Undefined failure behaviour is where hallucination enters"
G_INJECT = "Untrusted input must be delimited and marked as data, not instruction"
G_CLARITY = "Contradictions and vague quantifiers are resolved arbitrarily"
G_ECONOMY = "Everything in the prompt competes with the task for attention"


@dataclass
class Prompt:
    kind: str = "prompt"
    name: str = ""
    version: str = ""
    text: str = ""
    path: Path | None = None
    profile: str = ""

    @property
    def words(self) -> int:
        return len(self.text.split())

    def line_of(self, index: int) -> int:
        return self.text[:index].count("\n") + 1


def load_prompt(path: str | Path) -> Prompt:
    p = Path(path)
    return Prompt(name=p.stem, text=p.read_text(encoding="utf-8"), path=p)


RuleFn = Callable[[Prompt], list[Finding]]
REGISTRY: list[tuple[str, RuleFn]] = []


def rule(code: str) -> Callable[[RuleFn], RuleFn]:
    def deco(fn: RuleFn) -> RuleFn:
        REGISTRY.append((code, fn))
        return fn

    return deco


# --------------------------------------------------------------------------
# Missing specification
# --------------------------------------------------------------------------

FORMAT_WORDS = re.compile(
    r"\b(json|yaml|xml|markdown|csv|table|bullet|list|format|schema|"
    r"respond with|reply with|output|return (a|an|the)|structure)\b",
    re.I,
)


@rule("PRM001")
def no_output_format(p: Prompt) -> list[Finding]:
    if p.words >= 40 and not FORMAT_WORDS.search(p.text):
        return [
            Finding(
                rule="PRM001",
                severity=Severity.MEDIUM,
                subject="output",
                message=(
                    "No output format is specified. The shape of the response will "
                    "vary between runs, which breaks anything parsing it."
                ),
                reference=G_FORMAT,
                question=Question(
                    id="output-format",
                    prompt="What shape should the output be?",
                    options=["JSON", "Markdown", "plain prose", "a single line"],
                    applies_to="output format",
                    outcomes=_format_outcomes(),
                ),
            )
        ]
    return []


FAILURE_WORDS = re.compile(
    r"(\bif you (can'?t|cannot|are unable|do not know|don'?t know)\b"
    r"|\bwhen (unclear|ambiguous|unsure|uncertain)\b"
    r"|\bif\b[^.\n]{0,60}\b(is|are|was|contains?) (empty|missing|blank|unavailable|"
    r"no [a-z ]{0,20}|not (found|provided|available|enough))\b"
    r"|\bif (there (is|are) no|no .{0,25}(is )?(found|available|provided))\b"
    r"|\bdo not (guess|speculate|invent|fabricate|assume|make up)\b"
    r"|\bnever (guess|speculate|invent|fabricate|make up)\b"
    r"|\botherwise\b|\bfall ?back\b"
    r"|\bsay (you (do not|don'?t) know|so)\b|\brefuse\b|\bdecline\b"
    r"|\bask (one|a|the user)[^.\n]{0,40}\b(question|clarif)"
    r"|\breturn (an? )?(empty|null|nothing)\b)",
    re.I,
)


@rule("PRM002")
def no_failure_behaviour(p: Prompt) -> list[Finding]:
    if p.words >= 40 and not FAILURE_WORDS.search(p.text):
        return [
            Finding(
                rule="PRM002",
                severity=Severity.HIGH,
                subject="failure",
                message=(
                    "Nothing says what to do when the input is missing, empty, or "
                    "insufficient. With no instruction, the model produces its best "
                    "guess and presents it with the same confidence as a real answer."
                ),
                reference=G_FAILURE,
                question=Question(
                    id="failure-mode",
                    prompt="When there isn't enough information, what should happen?",
                    options=[
                        "ask the user a question",
                        "say it doesn't know",
                        "return an empty result",
                        "make a best guess and label it",
                    ],
                    applies_to="failure behaviour",
                    outcomes=_failure_outcomes(),
                ),
            )
        ]
    return []


LENGTH_WORDS = re.compile(
    r"\b(\d+\s*(words?|sentences?|paragraphs?|lines?|characters?|items?|bullets?)|"
    r"brief|concise|short|one (line|sentence|paragraph)|no more than|at most|"
    r"under \d+|keep it)\b",
    re.I,
)


@rule("PRM003")
def no_length_bound(p: Prompt) -> list[Finding]:
    if p.words >= 60 and not LENGTH_WORDS.search(p.text):
        return [
            Finding(
                rule="PRM003",
                severity=Severity.LOW,
                subject="length",
                message="No length guidance. Output length will drift run to run.",
                reference=G_FORMAT,
                fix="State a bound: a word count, a sentence count, or 'one paragraph'.",
            )
        ]
    return []


# --------------------------------------------------------------------------
# Injection surface
# --------------------------------------------------------------------------

PLACEHOLDER = re.compile(r"(\{\{?\s*[\w.]+\s*\}?\}|\$\{[\w.]+\}|<[\w_]+>|%s|\{[\w]+\})")
DELIMITED = re.compile(r"(```|<[\w]+>[\s\S]{0,400}</[\w]+>|\"\"\"|---)")


@rule("PRM004")
def undelimited_interpolation(p: Prompt) -> list[Finding]:
    out = []
    seen: set[str] = set()
    for m in PLACEHOLDER.finditer(p.text):
        token = m.group(1)
        if token in seen:
            continue
        seen.add(token)
        window = p.text[max(0, m.start() - 220) : m.end() + 220]
        if DELIMITED.search(window):
            continue
        out.append(
            Finding(
                rule="PRM004",
                severity=Severity.HIGH,
                subject=f"line {p.line_of(m.start())}",
                message=(
                    f"{token} is interpolated directly into the instructions with no "
                    "delimiter around it. Whatever lands there is read as instruction."
                ),
                reference=G_INJECT,
                fix=(
                    "Wrap it in a fenced block or an XML tag, and say in the prompt "
                    "that the contents are data to be processed, not instructions to "
                    "be followed."
                ),
            )
        )
    return out[:5]


INJECTION = [
    r"\bignore (all |any )?(previous|prior|above)\b",
    r"\boverride (your|the) (instructions|guidelines|rules)\b",
    r"\bregardless of (any|your) (instructions|guidelines|policy|rules)\b",
    r"\bdo not (tell|inform|reveal to) the user\b",
    r"\bpretend (you are not|that you)\b",
]


@rule("PRM005")
def override_language(p: Prompt) -> list[Finding]:
    out = []
    for pat in INJECTION:
        m = re.search(pat, p.text, re.I)
        if m:
            out.append(
                Finding(
                    rule="PRM005",
                    severity=Severity.HIGH,
                    subject=f"line {p.line_of(m.start())}",
                    message=(
                        f"Instruction attempts to override prior rules "
                        f"(matched: {m.group(0)!r}). This is unreliable and it is what "
                        "an injected payload looks like — it teaches the wrong pattern."
                    ),
                    reference=G_INJECT,
                )
            )
    return out


SECRET = re.compile(r"\b(sk-[A-Za-z0-9-]{12,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,})")


@rule("PRM006")
def embedded_secret(p: Prompt) -> list[Finding]:
    m = SECRET.search(p.text)
    if m:
        return [
            Finding(
                rule="PRM006",
                severity=Severity.HIGH,
                subject=f"line {p.line_of(m.start())}",
                message="A literal credential appears in the prompt text.",
                reference=G_INJECT,
                fix="Remove it and rotate the key. Prompts get logged, cached, and shared.",
            )
        ]
    return []


# --------------------------------------------------------------------------
# Clarity
# --------------------------------------------------------------------------

def _ngram_prefixes(text: str, marker: str) -> set[str]:
    """Every 1-3 word phrase following a marker.

    Comparing whole captured spans misses the common case, where the same
    instruction is written at different lengths — "always be concise" against
    "never be concise if the customer is angry". Prefixes catch the overlap.
    """
    out: set[str] = set()
    for m in re.finditer(marker + r"\s+([a-z']+(?:\s+[a-z']+){0,3})", text, re.I):
        words = m.group(1).lower().split()
        for n in range(1, min(3, len(words)) + 1):
            phrase = " ".join(words[:n])
            if len(phrase) > 3:  # skip bare articles and particles
                out.add(phrase)
    return out


STOP_PHRASES = {"be", "use", "the", "a", "an", "it", "them", "this", "that", "make"}


@rule("PRM007")
def contradiction(p: Prompt) -> list[Finding]:
    """always X somewhere, never X somewhere else."""
    always = _ngram_prefixes(p.text, r"\b(?:always|must|should)")
    never = _ngram_prefixes(p.text, r"\b(?:never|do not|don'?t|avoid|must not)")
    clashes = sorted(
        c for c in (always & never) if c not in STOP_PHRASES and len(c.split()) >= 2
    )
    return [
        Finding(
            rule="PRM007",
            severity=Severity.HIGH,
            subject="consistency",
            message=(
                f"The prompt both requires and forbids {c!r}. The model resolves this "
                "arbitrarily, so behaviour will look random."
            ),
            reference=G_CLARITY,
            fix="Decide which one holds, or state the condition that separates them.",
        )
        for c in clashes[:3]
    ]


VAGUE = re.compile(
    r"\b(appropriate(ly)?|as needed|if necessary|reasonable|relevant|"
    r"some|a few|several|properly|good|nice|high[- ]quality|etc\.?)\b",
    re.I,
)


@rule("PRM008")
def vague_quantifier(p: Prompt) -> list[Finding]:
    hits = {m.group(0).lower() for m in VAGUE.finditer(p.text)}
    if len(hits) >= 3:
        return [
            Finding(
                rule="PRM008",
                severity=Severity.MEDIUM,
                subject="precision",
                message=(
                    "Vague terms carry real instructions here: "
                    + ", ".join(sorted(hits)[:6])
                    + ". Each is interpreted differently on each run."
                ),
                reference=G_CLARITY,
                fix="Replace with something checkable — a number, a list, a condition.",
            )
        ]
    return []


@rule("PRM009")
def negation_heavy(p: Prompt) -> list[Finding]:
    negs = len(re.findall(r"\b(never|do not|don'?t|avoid|must not|no longer)\b", p.text, re.I))
    pos = len(
        re.findall(
            r"\b(?<!not )(always|must(?! not)|should(?! not)|use|write|return|include|"
            r"respond|reply|output|state|give)\b",
            p.text,
            re.I,
        )
    )
    if negs >= 5 and negs > pos:
        return [
            Finding(
                rule="PRM009",
                severity=Severity.MEDIUM,
                subject="phrasing",
                message=(
                    f"{negs} prohibitions against {pos} positive instructions. A list of "
                    "things not to do leaves the actual target undefined."
                ),
                reference=G_CLARITY,
                fix="For each prohibition, state the behaviour you want instead.",
            )
        ]
    return []


@rule("PRM010")
def duplicated_instruction(p: Prompt) -> list[Finding]:
    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", p.text) if len(s.strip()) > 14
    ]
    seen: dict[str, int] = {}
    out = []
    for i, ln in enumerate(sentences, 1):
        key = re.sub(r"\W+", " ", ln.lower()).strip()
        if key in seen:
            out.append(
                Finding(
                    rule="PRM010",
                    severity=Severity.LOW,
                    subject="repetition",
                    message=(
                        f"An instruction is repeated verbatim: {ln[:60]!r}. Two copies "
                        "means the next edit changes one and misses the other."
                    ),
                    reference=G_ECONOMY,
                    fix="Keep one copy.",
                )
            )
        else:
            seen[key] = i
    return out[:3]


@rule("PRM011")
def bloat(p: Prompt) -> list[Finding]:
    if p.words > 1500:
        return [
            Finding(
                rule="PRM011",
                severity=Severity.MEDIUM,
                subject="size",
                message=(
                    f"{p.words} words. Everything here is re-read on every request and "
                    "competes with the user's actual input for attention."
                ),
                reference=G_ECONOMY,
                fix=(
                    "Move rarely-needed detail out of the always-loaded prompt, and "
                    "cut anything the model already does by default."
                ),
            )
        ]
    return []


# --------------------------------------------------------------------------
# Answer -> correction
#
# These append a clause to the prompt. They are scaffolds, marked TODO, and the
# tool never rewrites your existing wording.
# --------------------------------------------------------------------------

def _format_outcomes() -> dict[str, list[Patch]]:
    tmpl = {
        "JSON": (
            "Respond with a single JSON object and nothing else — no prose, no code "
            "fences. TODO: specify the keys and their types."
        ),
        "Markdown": (
            "Respond in Markdown. TODO: name the sections and their order."
        ),
        "plain prose": (
            "Respond in plain prose with no headings, lists, or code blocks."
        ),
        "a single line": "Respond with one line and nothing else.",
    }
    return {
        k: [
            Patch(
                target="append",
                field_path=["output"],
                value=v,
                note="output format clause",
                todo="TODO" in v,
            )
        ]
        for k, v in tmpl.items()
    }


def _failure_outcomes() -> dict[str, list[Patch]]:
    tmpl = {
        "ask the user a question": (
            "If the information needed is missing or ambiguous, ask one specific "
            "question instead of answering."
        ),
        "say it doesn't know": (
            "If you do not have enough information to answer, say so plainly. Do not "
            "guess and do not fill gaps with plausible detail."
        ),
        "return an empty result": (
            "If there is no valid result, return an empty result rather than an "
            "approximation."
        ),
        "make a best guess and label it": (
            "If the information is incomplete, give your best answer and state "
            "explicitly which parts are uncertain and why."
        ),
    }
    return {
        k: [
            Patch(
                target="append",
                field_path=["failure"],
                value=v,
                note="failure behaviour clause",
            )
        ]
        for k, v in tmpl.items()
    }


def run_all(p: Prompt, profile: str | None = None) -> list[Finding]:
    """Generic rules, plus the profile's dimensions when one applies.

    Profile detection is conservative — guessing wrong produces a page of
    findings about dimensions the author never meant to address.
    """
    from . import profiles as profiles_mod

    findings: list[Finding] = []
    for _code, fn in REGISTRY:
        findings.extend(fn(p))

    chosen = None
    if profile and profile != "none":
        chosen = profiles_mod.PROFILES.get(profile)
    elif profile is None:
        chosen = profiles_mod.detect(p.text)
    if chosen is not None:
        p.profile = chosen.id
        if chosen.suppress:
            findings = [f for f in findings if f.rule not in chosen.suppress]
        findings.extend(profiles_mod.run(p.text, chosen))
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    findings.sort(key=lambda f: (order[f.severity], f.rule, f.subject))
    return findings
