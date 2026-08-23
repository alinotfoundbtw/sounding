"""Deterministic rules for Agent Skills.

The pressure on a skill is different from an MCP server. A server's risk is
permission; a skill's risk is that it never fires, or fires on the wrong task,
or quietly carries instructions nobody reviewed.

Published skills score badly on average, and the reasons are structural rather
than stylistic — which is exactly what a linter can catch.
"""

from __future__ import annotations

import re
from typing import Callable

from ..model import Finding, Question, Severity
from ..patch import Patch
from ..skillfile import Skill

SPEC_FM = "Agent Skills — required frontmatter: name, description"
GUIDE_TRIGGER = "Skill descriptions are the only thing the model matches against"
GUIDE_DISCLOSURE = "Progressive disclosure — keep SKILL.md short, move detail to references/"
GUIDE_TRUST = "Skill supply chain — review instructions before installing"
GUIDE_PORTABLE = "Skills run unmodified across many agent products"

RuleFn = Callable[[Skill], list[Finding]]
REGISTRY: list[tuple[str, RuleFn]] = []


def rule(code: str) -> Callable[[RuleFn], RuleFn]:
    def deco(fn: RuleFn) -> RuleFn:
        REGISTRY.append((code, fn))
        return fn

    return deco


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------

@rule("SKL001")
def missing_frontmatter(s: Skill) -> list[Finding]:
    if not s.has_frontmatter:
        return [
            Finding(
                rule="SKL001",
                severity=Severity.HIGH,
                subject="frontmatter",
                message="No frontmatter block. The skill cannot be registered or triggered.",
                reference=SPEC_FM,
                fix="Open the file with a --- fenced block containing name and description.",
            )
        ]
    out = []
    for err in s.parse_errors:
        out.append(
            Finding(
                rule="SKL001",
                severity=Severity.MEDIUM,
                subject="frontmatter",
                message=f"Unparseable frontmatter — {err}",
                reference=SPEC_FM,
                fix="Use `key: value` per line. Fold long values with an indented continuation.",
            )
        )
    return out


@rule("SKL002")
def name_mismatch(s: Skill) -> list[Finding]:
    if not s.has_frontmatter:
        return []
    if not s.name:
        return [
            Finding(
                rule="SKL002",
                severity=Severity.HIGH,
                subject="frontmatter.name",
                message="No name declared.",
                reference=SPEC_FM,
                patch=Patch(
                    target="frontmatter",
                    field_path=["name"],
                    value=s.stem or "TODO-name",
                    note="taken from the directory name",
                    todo=not s.stem,
                ),
            )
        ]
    out = []
    if s.stem and s.name != s.stem:
        out.append(
            Finding(
                rule="SKL002",
                severity=Severity.MEDIUM,
                subject="frontmatter.name",
                message=(
                    f"name is {s.name!r} but the directory is {s.stem!r}. "
                    "Links and references resolve against the name."
                ),
                reference=SPEC_FM,
                patch=Patch(
                    target="frontmatter",
                    field_path=["name"],
                    value=s.stem,
                    note="aligned to the directory name",
                ),
            )
        )
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s.name):
        out.append(
            Finding(
                rule="SKL002",
                severity=Severity.LOW,
                subject="frontmatter.name",
                message=f"{s.name!r} is not a lowercase hyphenated slug.",
                reference=SPEC_FM,
                fix="Use lowercase words joined by hyphens.",
            )
        )
    return out


# --------------------------------------------------------------------------
# Triggering — the description is the whole interface
# --------------------------------------------------------------------------

TRIGGER_WORDS = re.compile(
    # Real descriptions state triggers in far more ways than a house style
    # suggests: "when building new UI", "for users whose employer...",
    # "handles login and submission". Requiring one blessed phrasing produced
    # a false positive on nearly half of a professional corpus.
    r"("
    r"\buse (this|it|when|for)\b|\bwhen(ever)?\b|\btrigger\b|\bapplies\b"
    r"|\bfor (any|all|tasks|requests|users|files|projects|people|teams|anyone|when)\b"
    r"|\binvoke\b|\bif the user\b|\bafter\b|\bbefore\b|\bduring\b"
    r"|\bhandles?\b|\bcovers?\b|\bsupports?\b|\bhelps? with\b"
    r"|\basked to\b|\brequests?\b|\bmentions?\b|\breferences?\b"
    r"|\b(\.[a-z0-9]{2,5})\b"          # a file extension is itself a trigger
    r"|\b(creating|editing|building|writing|reading|converting|reviewing|"
    r"designing|analyzing|analysing|working with|dealing with)\b"
    r")",
    re.I,
)

FIRST_PERSON = re.compile(r"\b(I |I'm|my |we |our )\b")


@rule("SKL003")
def missing_description(s: Skill) -> list[Finding]:
    if s.has_frontmatter and not s.description.strip():
        return [
            Finding(
                rule="SKL003",
                severity=Severity.HIGH,
                subject="frontmatter.description",
                message=(
                    "No description. The model matches tasks against this field alone — "
                    "without it the skill will never fire."
                ),
                reference=GUIDE_TRIGGER,
                question=Question(
                    id="skill-purpose",
                    prompt="When should this skill fire?",
                    options=[
                        "working with a specific file type",
                        "a named workflow or process",
                        "a domain or subject area",
                        "a specific tool or service",
                    ],
                    applies_to="frontmatter.description",
                    outcomes=_purpose_outcomes(s.name or s.stem or "this skill"),
                ),
            )
        ]
    return []


@rule("SKL004")
def thin_description(s: Skill) -> list[Finding]:
    d = s.description.strip()
    if d and len(d) < 60:
        return [
            Finding(
                rule="SKL004",
                severity=Severity.MEDIUM,
                subject="frontmatter.description",
                message=(
                    f"Description is {len(d)} characters. Too thin to distinguish this "
                    "skill from every other one installed."
                ),
                reference=GUIDE_TRIGGER,
                fix=(
                    "State what it does AND the concrete situations that should trigger "
                    "it. Name file types, tool names, and phrasings users actually use."
                ),
                question=Question(
                    id="skill-purpose",
                    prompt="When should this skill fire?",
                    options=[
                        "working with a specific file type",
                        "a named workflow or process",
                        "a domain or subject area",
                        "a specific tool or service",
                    ],
                    applies_to="frontmatter.description",
                    outcomes=_purpose_outcomes(s.name or s.stem or "this skill"),
                ),
            )
        ]
    return []


ENUMERATION = re.compile(r"(?:[^,]+,){2,}[^,]+")


def _names_situations(d: str) -> bool:
    """An enumeration is a trigger list even without a trigger word.

    "tax estimates, loan comparisons, retirement projections, rent vs. buy"
    tells the model when to fire more precisely than "use this when the user
    asks about finance" does.
    """
    return bool(TRIGGER_WORDS.search(d) or ENUMERATION.search(d))


@rule("SKL005")
def description_has_no_trigger(s: Skill) -> list[Finding]:
    d = s.description.strip()
    if d and len(d) >= 60 and not _names_situations(d):
        return [
            Finding(
                rule="SKL005",
                # A suggestion, not a defect. Plenty of good descriptions imply
                # their trigger through the verb rather than naming it.
                severity=Severity.LOW,
                subject="frontmatter.description",
                message=(
                    "Description says what the skill is but never names a situation "
                    "that should trigger it. Selection accuracy comes from the "
                    "trigger, not the summary."
                ),
                reference=GUIDE_TRIGGER,
                fix=(
                    "Add an explicit clause: 'Use when the user asks to …'. "
                    "Include the words a user would actually type."
                ),
            )
        ]
    return []


def _strip_quoted(text: str) -> str:
    """Remove quoted phrases before checking voice.

    A description should contain the words a user would actually type — and
    those are frequently first person ("my style", "my repo"). Quoting them is
    correct, so quoted spans are not the author's voice.
    """
    return re.sub(r"[\"'“‘][^\"'”’]{0,60}[\"'”’]", " ", text)


@rule("SKL006")
def first_person_description(s: Skill) -> list[Finding]:
    if s.description and FIRST_PERSON.search(_strip_quoted(s.description)):
        return [
            Finding(
                rule="SKL006",
                severity=Severity.LOW,
                subject="frontmatter.description",
                message=(
                    "Description is written in first person. It is matched against a "
                    "task, not read by a person."
                ),
                reference=GUIDE_TRIGGER,
                fix="Write it in the third person, describing the situation it applies to.",
            )
        ]
    return []


# --------------------------------------------------------------------------
# Size and disclosure
# --------------------------------------------------------------------------

@rule("SKL007")
def body_too_long(s: Skill) -> list[Finding]:
    words = len(s.body.split())
    # Measured against a professional corpus: median 916, p90 2937. A threshold
    # under the p90 flags careful comprehensive skills as bloated.
    if words > 4000:
        refs = re.findall(r"references?/[\w./-]+", s.body)
        return [
            Finding(
                rule="SKL007",
                severity=Severity.MEDIUM,
                subject="body",
                message=(
                    f"{words} words in SKILL.md. This is loaded whenever the skill "
                    "fires, so it competes with the user's actual task for context."
                    + ("" if refs else " No reference files are linked.")
                ),
                reference=GUIDE_DISCLOSURE,
                fix=(
                    "Keep SKILL.md to the decision layer — when to do what — and move "
                    "detail into references/ that gets read only when needed."
                ),
            )
        ]
    return []


@rule("SKL008")
def broken_reference(s: Skill) -> list[Finding]:
    if s.base_dir is None:
        return []
    out = []
    seen: set[str] = set()
    for rel in re.findall(r"(?:^|[\s(`\"'])([\w.-]*references?/[\w./-]+\.\w+)", s.body):
        rel = rel.strip("`\"'")
        if rel in seen:
            continue
        seen.add(rel)
        if not (s.base_dir / rel).exists():
            out.append(
                Finding(
                    rule="SKL008",
                    severity=Severity.HIGH,
                    subject=f"reference:{rel}",
                    message=(
                        f"SKILL.md points at {rel}, which does not exist. The agent "
                        "will try to read it and fail mid-task."
                    ),
                    reference=GUIDE_DISCLOSURE,
                    fix="Create the file or remove the pointer.",
                )
            )
    return out


@rule("SKL009")
def no_concrete_guidance(s: Skill) -> list[Finding]:
    body = s.body
    has_example = bool(re.search(r"```|^\s*[-*]\s|\|.*\|", body, re.M))
    if len(body.split()) > 120 and not has_example:
        return [
            Finding(
                rule="SKL009",
                severity=Severity.LOW,
                subject="body",
                message=(
                    "No examples, lists, or code blocks — the body is unbroken prose. "
                    "Concrete cases carry more than description does."
                ),
                reference=GUIDE_DISCLOSURE,
                fix="Add at least one worked example of the skill applied.",
            )
        ]
    return []


# --------------------------------------------------------------------------
# Safety and portability
# --------------------------------------------------------------------------

INJECTION = [
    r"\bignore (all |any )?(previous|prior|above)\b",
    r"\bdisregard\b.{0,20}\b(instruction|rule|guideline)",
    r"\boverride (your|the) (instructions|guidelines|rules)\b",
    r"\bregardless of (any|your) (instructions|guidelines|policy)\b",
    r"\bdo not (tell|inform|mention to) the user\b",
]


DEFENSIVE = re.compile(
    r"(do not follow|never follow|ignore (it|them|these)|refuse|reject|drop|skip|"
    r"treat .{0,30} as data|not as instructions?|such as|for example|e\.g\.|"
    r"if .{0,40} contains|watch for|beware|attempts? to|looks? like|"
    r"addressed to you|injection)",
    re.I,
)


def _is_quoted_or_defensive(body: str, start: int, end: int) -> bool:
    """A skill that warns about an attack string contains that string.

    Security guidance is the single most likely place to find these phrases,
    and flagging it inverts the rule's purpose — the careful author gets the
    finding and the careless one does not.
    """
    window = body[max(0, start - 240) : end + 120]
    if DEFENSIVE.search(window):
        return True
    before, after = body[:start], body[end:]
    for quote in ('"', "'", "\u201c", "`"):
        if quote in before[-80:] and quote in after[:80]:
            return True
    return False


@rule("SKL010")
def injection_language(s: Skill) -> list[Finding]:
    out = []
    for p in INJECTION:
        m = re.search(p, s.body, re.I)
        if m:
            if _is_quoted_or_defensive(s.body, m.start(), m.end()):
                continue
            line = s.body[: m.start()].count("\n") + 1
            out.append(
                Finding(
                    rule="SKL010",
                    severity=Severity.HIGH,
                    subject=f"body:line {line}",
                    message=(
                        f"Instruction attempts to override the host agent "
                        f"(matched: {m.group(0)!r}). Anyone installing this skill is "
                        "installing that instruction."
                    ),
                    reference=GUIDE_TRUST,
                )
            )
    return out


DANGEROUS = [
    (r"rm\s+-rf\s+[/~]", "recursively deletes a root or home path"),
    (r"curl[^\n|]*\|\s*(sudo\s+)?(ba)?sh", "pipes a remote script straight into a shell"),
    (r"wget[^\n|]*\|\s*(sudo\s+)?(ba)?sh", "pipes a remote script straight into a shell"),
    (r"chmod\s+777", "sets world-writable permissions"),
    (r"\beval\s*\(\s*(input|request|user)", "evaluates untrusted input"),
    (r"--no-verify\b", "bypasses commit hooks"),
    (r"git\s+push\s+.*--force(?!-with-lease)", "force-pushes without a lease"),
]


@rule("SKL011")
def dangerous_command(s: Skill) -> list[Finding]:
    out = []
    for pattern, why in DANGEROUS:
        m = re.search(pattern, s.body, re.I)
        if m:
            line = s.body[: m.start()].count("\n") + 1
            out.append(
                Finding(
                    rule="SKL011",
                    severity=Severity.HIGH,
                    subject=f"body:line {line}",
                    message=f"Instructs the agent to run a command that {why}: {m.group(0)!r}",
                    reference=GUIDE_TRUST,
                    fix="Remove it, or gate it behind explicit user confirmation in the text.",
                )
            )
    return out


SECRET_LITERAL = re.compile(r"\b(sk-[A-Za-z0-9-]{12,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,})")


@rule("SKL012")
def embedded_secret(s: Skill) -> list[Finding]:
    m = SECRET_LITERAL.search(s.body)
    if m:
        line = s.body[: m.start()].count("\n") + 1
        return [
            Finding(
                rule="SKL012",
                severity=Severity.HIGH,
                subject=f"body:line {line}",
                message="A literal credential appears in the skill body.",
                reference=GUIDE_TRUST,
                fix="Remove it and rotate the key. Skill files get committed and shared.",
            )
        ]
    return []


ABS_PATH = re.compile(r"(?:^|[\s(`\"'])(/(?:Users|home)/[\w.-]+/[\w./-]*)")


@rule("SKL013")
def machine_specific_path(s: Skill) -> list[Finding]:
    m = ABS_PATH.search(s.body)
    if m:
        line = s.body[: m.start()].count("\n") + 1
        return [
            Finding(
                rule="SKL013",
                severity=Severity.MEDIUM,
                subject=f"body:line {line}",
                message=(
                    f"Absolute path to one machine's home directory: {m.group(1)!r}. "
                    "This breaks for everyone else who installs the skill."
                ),
                reference=GUIDE_PORTABLE,
                fix="Use a path relative to the skill directory or the project root.",
            )
        ]
    return []


# --------------------------------------------------------------------------
# Answer -> correction
# --------------------------------------------------------------------------

_PURPOSE_TEMPLATES = {
    "working with a specific file type": (
        "Work with TODO_FILETYPE files. Use whenever the user asks to create, read, "
        "edit, or convert a TODO_FILETYPE, or mentions a .TODO_EXT file."
    ),
    "a named workflow or process": (
        "Run the TODO_WORKFLOW process. Use when the user asks to TODO_TRIGGER, or "
        "refers to this workflow by name."
    ),
    "a domain or subject area": (
        "Guidance for TODO_DOMAIN work. Use when the user's task involves "
        "TODO_TRIGGER, even if they do not name this skill."
    ),
    "a specific tool or service": (
        "Work with TODO_SERVICE. Use when the user mentions TODO_SERVICE by name or "
        "asks to perform an action against it."
    ),
}


def _purpose_outcomes(name: str) -> dict[str, list[Patch]]:
    return {
        label: [
            Patch(
                target="frontmatter",
                field_path=["description"],
                value=tmpl,
                note=f"description scaffold for {name}",
                todo=True,
            )
        ]
        for label, tmpl in _PURPOSE_TEMPLATES.items()
    }


def run_all(skill: Skill) -> list[Finding]:
    findings: list[Finding] = []
    for _code, fn in REGISTRY:
        findings.extend(fn(skill))
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    findings.sort(key=lambda f: (order[f.severity], f.rule, f.subject))
    return findings
