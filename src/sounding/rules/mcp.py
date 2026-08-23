"""Deterministic rules for MCP servers.

Every rule answers: what is wrong, why it matters (with a source), and how to
fix it. Nothing here uses a model. If a check cannot be made without running
the server or asking a human, it becomes a question rather than a verdict.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from ..model import Finding, Question, Server, Severity
from ..patch import Patch

# Reference labels. Kept short; the docs map lives in references.py.
SPEC_TOOLS = "MCP spec — Tools: name, description, inputSchema"
SPEC_ANNOT = "MCP spec — Tool annotations: readOnlyHint, destructiveHint"
SPEC_TRANSPORT = "MCP spec — Transports: Streamable HTTP"
GUIDE_TRUST = "MCP security guidance — scan before installing, pin tool descriptions"
GUIDE_DESC = "Tool description quality — the model selects tools by description alone"

RuleFn = Callable[[Server], list[Finding]]
REGISTRY: list[tuple[str, RuleFn]] = []


def tools_of(s: Server) -> list[dict[str, Any]]:
    """Only the tools that are shaped like tools.

    `Server` is a public type and can be built by hand, so rules never assume
    the loader sanitized anything. Malformed entries are reported by MCP000,
    not crashed on here.
    """
    tools = s.tools
    if not isinstance(tools, list):
        return []
    return [t for t in tools if isinstance(t, dict) and isinstance(t.get("name"), str)]


def text_of(tool: dict[str, Any], key: str) -> str:
    v = tool.get(key)
    return v if isinstance(v, str) else ""


def props_of(tool: dict[str, Any]) -> dict[str, Any]:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties")
    return props if isinstance(props, dict) else {}


def rule(code: str) -> Callable[[RuleFn], RuleFn]:
    def deco(fn: RuleFn) -> RuleFn:
        REGISTRY.append((code, fn))
        return fn

    return deco


# --------------------------------------------------------------------------
# Description quality — the model has nothing else to go on
# --------------------------------------------------------------------------

@rule("MCP000")
def malformed_descriptor(s: Server) -> list[Finding]:
    """Structural problems found while reading the file."""
    return [
        Finding(
            rule="MCP000",
            severity=Severity.HIGH,
            subject="descriptor",
            message=(
                f"{problem}. This part could not be audited, so anything wrong "
                "inside it is invisible to every other rule."
            ),
            reference=SPEC_TOOLS,
            fix="Fix the shape so the rest of the file can be checked.",
        )
        for problem in s.malformed
    ]


@rule("MCP001")
def missing_description(s: Server) -> list[Finding]:
    out = []
    for t in tools_of(s):
        if not text_of(t, "description").strip():
            out.append(
                Finding(
                    rule="MCP001",
                    severity=Severity.HIGH,
                    subject=f"tool:{t.get('name', '?')}",
                    message="Tool has no description.",
                    reference=SPEC_TOOLS,
                    question=Question(
                        id=f"purpose:{t.get('name')}",
                        prompt=f"What does `{t.get('name')}` do, in one sentence?",
                        options=[
                            "reads data",
                            "writes or changes data",
                            "runs a computation",
                            "calls an external service",
                        ],
                        applies_to=f"tools[{t.get('name')}].description",
                        outcomes=_purpose_outcomes(t.get("name", "?")),
                    ),
                )
            )
    return out


@rule("MCP002")
def thin_description(s: Server) -> list[Finding]:
    out = []
    for t in tools_of(s):
        desc = text_of(t, "description").strip()
        if desc and len(desc) < 40:
            out.append(
                Finding(
                    rule="MCP002",
                    severity=Severity.MEDIUM,
                    subject=f"tool:{t.get('name', '?')}",
                    message=(
                        f"Description is {len(desc)} characters. Too thin for the "
                        "model to know when to call this rather than something else."
                    ),
                    reference=GUIDE_DESC,
                    fix=(
                        "State what it does, when to use it, and when NOT to use it. "
                        "Selection accuracy comes from the boundary, not the summary."
                    ),
                )
            )
    return out


@rule("MCP003")
def injection_surface(s: Server) -> list[Finding]:
    """Tool descriptions are injected into the model's context verbatim.

    A description that issues instructions to the model — rather than
    describing the tool — is an injection vector, whether or not it was
    written maliciously.
    """
    patterns = [
        r"\bignore (all |any )?(previous|prior|above)\b",
        r"\bdisregard\b.{0,20}\b(instruction|rule|prompt)",
        r"\byou (must|should) always\b",
        r"\bbefore (answering|responding|any)\b",
        r"\bdo not (tell|mention|reveal)\b",
        # "system prompt" alone is a legitimate noun — a tool may audit one.
        # Only an instruction *about* the model's own prompt is a finding.
        r"\b(your|the) system prompt\b(?!.{0,30}\b(file|files|artifact|document)\b)",
        r"\b(reveal|print|output|repeat|leak)\b.{0,20}\b(system )?(prompt|instructions)\b",
        r"</?(system|assistant|instructions)>",
    ]
    out = []
    for t in tools_of(s):
        desc = text_of(t, "description")
        for p in patterns:
            m = re.search(p, desc, re.I)
            if m:
                out.append(
                    Finding(
                        rule="MCP003",
                        severity=Severity.HIGH,
                        subject=f"tool:{t.get('name', '?')}",
                        message=(
                            f"Description instructs the model rather than describing "
                            f"the tool (matched: {m.group(0)!r}). This text enters the "
                            "context window verbatim."
                        ),
                        reference=GUIDE_TRUST,
                        fix=(
                            "Describe behaviour only. A tool description is API "
                            "documentation, not a prompt."
                        ),
                    )
                )
                break
    return out


@rule("MCP004")
def ambiguous_pair(s: Server) -> list[Finding]:
    """Two tools the model cannot tell apart is worse than one tool."""
    out = []
    seen: list[tuple[str, set[str]]] = []
    for t in tools_of(s):
        name = t.get("name", "?")
        words = set(re.findall(r"[a-z]{4,}", text_of(t, "description").lower()))
        if not words:
            continue
        for other_name, other_words in seen:
            union = words | other_words
            if not union:
                continue
            overlap = len(words & other_words) / len(union)
            if overlap > 0.8:
                out.append(
                    Finding(
                        rule="MCP004",
                        severity=Severity.MEDIUM,
                        subject=f"tool:{name}",
                        message=(
                            f"Description is {overlap:.0%} identical to `{other_name}`. "
                            "The model has no basis to choose between them."
                        ),
                        reference=GUIDE_DESC,
                        fix="Name the distinguishing condition in both descriptions.",
                    )
                )
                break
        seen.append((name, words))
    return out


# --------------------------------------------------------------------------
# Permission and blast radius
# --------------------------------------------------------------------------

SHELL_HINTS = re.compile(
    r"\b(shell|bash|sh|exec|execute|command|subprocess|eval|system call|"
    r"arbitrary code|run code)\b",
    re.I,
)


@rule("MCP005")
def shell_execution(s: Server) -> list[Finding]:
    out = []
    for t in tools_of(s):
        blob = f"{t.get('name', '')} {text_of(t, 'description')}"
        if SHELL_HINTS.search(blob):
            out.append(
                Finding(
                    rule="MCP005",
                    severity=Severity.HIGH,
                    subject=f"tool:{t.get('name', '?')}",
                    message=(
                        "Tool appears to execute commands. Any prompt injection "
                        "reaching this server reaches the shell."
                    ),
                    reference=GUIDE_TRUST,
                    question=Question(
                        id=f"shell:{t.get('name')}",
                        prompt=(
                            f"`{t.get('name')}` looks like it runs commands. "
                            "How is the command constrained?"
                        ),
                        options=[
                            "allowlist of fixed commands",
                            "sandboxed / container",
                            "arbitrary — no constraint",
                            "not actually an exec tool",
                        ],
                        applies_to=f"tools[{t.get('name')}]",
                    ),
                )
            )
    return out


WRITE_HINTS = re.compile(
    r"\b(delete|remove|drop|write|update|create|send|post|publish|deploy|"
    r"revoke|purge|overwrite)\b",
    re.I,
)


@rule("MCP006")
def unmarked_write(s: Server) -> list[Finding]:
    """Clients gate confirmation on annotations. Unmarked writes bypass that."""
    out = []
    for t in tools_of(s):
        blob = f"{t.get('name', '')} {text_of(t, 'description')}"
        ann = t.get("annotations")
        ann = ann if isinstance(ann, dict) else {}
        if WRITE_HINTS.search(blob):
            if ann.get("readOnlyHint") is True:
                out.append(
                    Finding(
                        rule="MCP006",
                        severity=Severity.HIGH,
                        subject=f"tool:{t.get('name', '?')}",
                        message=(
                            "Marked readOnlyHint=true but the description describes "
                            "a mutation. The annotation contradicts the tool."
                        ),
                        reference=SPEC_ANNOT,
                        fix="Set readOnlyHint=false and add destructiveHint if it destroys data.",
                        patch=Patch(
                            target="tool",
                            tool_name=t.get("name", "?"),
                            field_path=["annotations", "readOnlyHint"],
                            value=False,
                            note="annotation contradicted the description",
                        ),
                    )
                )
            elif "destructiveHint" not in ann and "readOnlyHint" not in ann:
                out.append(
                    Finding(
                        rule="MCP006",
                        severity=Severity.MEDIUM,
                        subject=f"tool:{t.get('name', '?')}",
                        message=(
                            "Mutating tool has no annotations. Clients cannot prompt "
                            "the user for confirmation."
                        ),
                        reference=SPEC_ANNOT,
                        question=Question(
                            id=f"destructive:{t.get('name')}",
                            prompt=f"Can `{t.get('name')}` destroy or overwrite data?",
                            options=[
                                "yes, irreversibly",
                                "yes, but reversible",
                                "no, additive only",
                            ],
                            applies_to=f"tools[{t.get('name')}].annotations",
                            outcomes=_destructive_outcomes(t.get("name", "?")),
                        ),
                    )
                )
    return out


@rule("MCP007")
def unvalidated_input(s: Server) -> list[Finding]:
    out = []
    for t in tools_of(s):
        schema = t.get("inputSchema")
        schema = schema if isinstance(schema, dict) else {}
        props = schema.get("properties")
        props = props if isinstance(props, dict) else (None if "properties" not in schema else {})
        if not schema:
            out.append(
                Finding(
                    rule="MCP007",
                    severity=Severity.HIGH,
                    subject=f"tool:{t.get('name', '?')}",
                    message="No inputSchema. Arguments are unvalidated.",
                    reference=SPEC_TOOLS,
                    fix="Declare a JSON Schema with explicit properties and required fields.",
                )
            )
        elif props is not None and len(props) == 0:
            out.append(
                Finding(
                    rule="MCP007",
                    severity=Severity.LOW,
                    subject=f"tool:{t.get('name', '?')}",
                    message="inputSchema declares no properties.",
                    reference=SPEC_TOOLS,
                    fix="If the tool takes no arguments this is fine; otherwise declare them.",
                )
            )
    return out


RISKY_PARAM = re.compile(r"^(path|file|filepath|dir|cmd|command|query|sql|url|host)$", re.I)


@rule("MCP008")
def unconstrained_param(s: Server) -> list[Finding]:
    """A free string named `path` or `cmd` is where traversal and injection live."""
    out = []
    for t in tools_of(s):
        props = props_of(t)
        for pname, pdef in props.items():
            if not isinstance(pdef, dict):
                continue
            if not RISKY_PARAM.match(pname):
                continue
            if pdef.get("type") != "string":
                continue
            constrained = any(k in pdef for k in ("enum", "pattern", "format", "const"))
            if not constrained:
                out.append(
                    Finding(
                        rule="MCP008",
                        severity=Severity.MEDIUM,
                        subject=f"tool:{t.get('name', '?')}.{pname}",
                        message=(
                            f"`{pname}` is an unconstrained string. No enum, pattern, "
                            "or format — the model can pass anything."
                        ),
                        reference=SPEC_TOOLS,
                        question=Question(
                            id=f"constrain:{t.get('name')}.{pname}",
                            prompt=f"What values are valid for `{pname}`?",
                            options=[
                                "a fixed set (enum)",
                                "matches a pattern",
                                "any value within a sandboxed root",
                                "genuinely unconstrained",
                            ],
                            applies_to=f"tools[{t.get('name')}].inputSchema.properties.{pname}",
                            outcomes=_constrain_outcomes(t.get("name", "?"), pname),
                        ),
                    )
                )
    return out


# --------------------------------------------------------------------------
# Transport, secrets, and hygiene
# --------------------------------------------------------------------------

SECRET_KEY = re.compile(r"(api[_-]?key|token|secret|password|passwd|credential)", re.I)
SECRET_VALUE = re.compile(r"^(sk-|ghp_|gho_|xox[baprs]-|AKIA|eyJ[A-Za-z0-9_-]{10,})")


@rule("MCP009")
def embedded_secret(s: Server) -> list[Finding]:
    out = []
    env = s.env if isinstance(s.env, dict) else {}
    for k, v in env.items():
        if not isinstance(k, str):
            continue
        val = str(v)
        looks_like_ref = val.startswith("${") or val in ("", "REPLACE_ME")
        if looks_like_ref:
            continue
        if SECRET_VALUE.match(val) or (SECRET_KEY.search(k) and len(val) > 12):
            out.append(
                Finding(
                    rule="MCP009",
                    severity=Severity.HIGH,
                    subject=f"env:{k}",
                    message="Config appears to contain a literal credential.",
                    reference=GUIDE_TRUST,
                    fix="Reference an environment variable (${VAR}) and rotate this value.",
                    patch=Patch(
                        target="env",
                        field_path=[k],
                        value="${" + k + "}",
                        note="literal credential replaced with a reference — rotate the old value",
                    ),
                )
            )
    return out


@rule("MCP010")
def insecure_transport(s: Server) -> list[Finding]:
    if s.url and s.url.startswith("http://"):
        parts = s.url.split("/")
        host = parts[2].split(":")[0] if len(parts) > 2 else ""
        if host not in ("localhost", "127.0.0.1", "::1"):
            return [
                Finding(
                    rule="MCP010",
                    severity=Severity.HIGH,
                    subject="transport",
                    message="Remote server is served over plaintext HTTP.",
                    reference=SPEC_TRANSPORT,
                    fix="Serve over HTTPS. Tool arguments frequently carry user data.",
                    patch=Patch(
                        target="server",
                        field_path=["url"],
                        value="https://" + s.url[len("http://"):],
                        note="transport upgraded to https",
                    ),
                )
            ]
    return []


@rule("MCP011")
def unpinnable(s: Server) -> list[Finding]:
    if not s.version:
        return [
            Finding(
                rule="MCP011",
                severity=Severity.MEDIUM,
                subject="server",
                message="No version declared. Consumers cannot pin or detect drift.",
                reference=GUIDE_TRUST,
                fix="Declare a semver version and bump it whenever a tool contract changes.",
                patch=Patch(
                    target="server",
                    field_path=["version"],
                    value="0.1.0",
                    note="starting version so consumers can pin",
                    todo=True,
                ),
            )
        ]
    return []


@rule("MCP012")
def surface_bloat(s: Server) -> list[Finding]:
    n = len(tools_of(s))
    if n > 40:
        return [
            Finding(
                rule="MCP012",
                severity=Severity.MEDIUM,
                subject="server",
                message=(
                    f"{n} tools. Every description occupies context on every request, "
                    "and selection accuracy falls as the surface grows."
                ),
                reference=GUIDE_DESC,
                question=Question(
                    id="split",
                    prompt=f"This server exposes {n} tools. Can it be split?",
                    options=[
                        "yes, by domain",
                        "yes, read vs write",
                        "no, all are needed together",
                    ],
                    applies_to="server",
                ),
            )
        ]
    return []


# --------------------------------------------------------------------------
# Answer -> correction
#
# Generated descriptions are scaffolds, flagged TODO. The tool will not write
# prose and present it as finished work.
# --------------------------------------------------------------------------

_PURPOSE_TEMPLATES = {
    "reads data": (
        "Read {n} and return the result. Use when the caller needs current "
        "values. TODO: say what it reads and when NOT to use it."
    ),
    "writes or changes data": (
        "Change {n} and return the updated state. TODO: say what changes, "
        "whether it is reversible, and when NOT to use it."
    ),
    "runs a computation": (
        "Compute {n} from the given arguments. Performs no I/O. "
        "TODO: state the inputs and the output shape."
    ),
    "calls an external service": (
        "Call an external service to {n}. TODO: name the service, the data "
        "sent to it, and the failure behaviour."
    ),
}


def _purpose_outcomes(tool: str) -> dict[str, list[Patch]]:
    return {
        label: [
            Patch(
                target="tool",
                tool_name=tool,
                field_path=["description"],
                value=tmpl.format(n=tool),
                note="description scaffold",
                todo=True,
            )
        ]
        for label, tmpl in _PURPOSE_TEMPLATES.items()
    }


def _destructive_outcomes(tool: str) -> dict[str, list[Patch]]:
    def ann(read_only: bool, destructive: bool, note: str) -> list[Patch]:
        return [
            Patch(
                target="tool",
                tool_name=tool,
                field_path=["annotations", "readOnlyHint"],
                value=read_only,
                note=note,
            ),
            Patch(
                target="tool",
                tool_name=tool,
                field_path=["annotations", "destructiveHint"],
                value=destructive,
                note=note,
            ),
        ]

    return {
        "yes, irreversibly": ann(False, True, "irreversible write — clients will confirm"),
        "yes, but reversible": ann(False, False, "reversible write"),
        "no, additive only": ann(False, False, "additive only"),
    }


def _constrain_outcomes(tool: str, param: str) -> dict[str, list[Patch]]:
    base = ["inputSchema", "properties", param]
    return {
        "a fixed set (enum)": [
            Patch(
                target="tool",
                tool_name=tool,
                field_path=base + ["enum"],
                value=["TODO_VALUE_1", "TODO_VALUE_2"],
                note="replace with the real allowed values",
                todo=True,
            )
        ],
        "matches a pattern": [
            Patch(
                target="tool",
                tool_name=tool,
                field_path=base + ["pattern"],
                value="^TODO_REGEX$",
                note="replace with the real pattern",
                todo=True,
            )
        ],
        "any value within a sandboxed root": [
            Patch(
                target="tool",
                tool_name=tool,
                field_path=base + ["pattern"],
                value="^(?!/)(?!.*\\.\\.).+$",
                note="relative paths only, no traversal",
            )
        ],
    }


def run_all(server: Server) -> list[Finding]:
    findings: list[Finding] = []
    for _code, fn in REGISTRY:
        findings.extend(fn(server))
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    findings.sort(key=lambda f: (order[f.severity], f.rule, f.subject))
    return findings


def rule_codes() -> list[str]:
    return [c for c, _ in REGISTRY]
