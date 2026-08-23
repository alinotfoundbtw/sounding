"""Finding artifacts in a tree, and the project config that governs them.

Two things a linter needs before anyone adopts it in a real repo: it has to
find the files itself, and it has to be tunable without forking the rules.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

CONFIG_NAMES = (".sounding.json", "sounding.json")

DEFAULT_EXCLUDES = [
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".tox", "site-packages", ".next", "target",
]

MCP_FILENAMES = re.compile(
    r"^(\.mcp\.json|mcp\.json|mcp[_-]servers?\.json|claude_desktop_config\.json"
    r"|.*\.mcp\.json)$",
    re.I,
)

PROMPT_SUFFIXES = (".txt", ".prompt")


@dataclass
class Config:
    """Per-project settings. Absent config means defaults, never an error."""

    disabled: set[str] = field(default_factory=set)
    severity: dict[str, str] = field(default_factory=dict)
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    min_score: int | None = None
    fail_on: str | None = None
    prompt_globs: list[str] = field(default_factory=list)
    source: Path | None = None

    @classmethod
    def load(cls, start: str | Path) -> "Config":
        p = Path(start)
        root = p if p.is_dir() else p.parent
        for directory in [root, *root.parents]:
            for name in CONFIG_NAMES:
                candidate = directory / name
                if candidate.exists():
                    return cls._from_file(candidate)
        return cls()

    @classmethod
    def _from_file(cls, path: Path) -> "Config":
        try:
            raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A broken config must not stop the audit. Defaults, and the
            # `config` command reports the problem.
            return cls(source=path)
        excludes = list(raw.get("exclude") or [])
        return cls(
            disabled=set(raw.get("disable") or []),
            severity=dict(raw.get("severity") or {}),
            exclude=DEFAULT_EXCLUDES + excludes,
            min_score=raw.get("minScore"),
            fail_on=raw.get("failOn"),
            prompt_globs=list(raw.get("promptGlobs") or []),
            source=path,
        )

    def excluded(self, path: Path) -> bool:
        parts = set(path.parts)
        return any(x in parts for x in self.exclude)


def apply_config(findings: list, config: Config) -> list:
    """Drop disabled rules and re-grade severities.

    Rules are disabled by code (`MCP008`) or by prefix (`MCP`), so a team can
    switch off a whole adapter without listing every rule.
    """
    from .model import Severity

    out = []
    for f in findings:
        if f.rule in config.disabled:
            continue
        if any(f.rule.startswith(d) for d in config.disabled if d.isalpha()):
            continue
        override = config.severity.get(f.rule)
        if override in ("high", "medium", "low"):
            f.severity = Severity(override)
        elif override == "off":
            continue
        out.append(f)
    return out


@dataclass
class Found:
    path: Path
    kind: str


def discover(root: str | Path, config: Config | None = None) -> list[Found]:
    """Walk a tree and classify every auditable artifact.

    Deliberately conservative on prompts: a repo is full of .txt and .md files
    that are not prompts, so those are only picked up when a promptGlobs entry
    in the config says so. Skills and MCP configs are unambiguous enough to
    detect by shape.
    """
    root_path = Path(root)
    config = config or Config()
    found: list[Found] = []
    seen: set[Path] = set()

    if root_path.is_file():
        return [Found(root_path, classify(root_path))]

    for path in sorted(_walk(root_path, config)):
        if path in seen:
            continue
        name = path.name

        if name == "SKILL.md":
            found.append(Found(path.parent, "skill"))
            seen.add(path)
            continue

        if path.suffix.lower() == ".json" and (
            MCP_FILENAMES.match(name) or looks_like_mcp(path)
        ):
            found.append(Found(path, "mcp"))
            seen.add(path)
            continue

        if config.prompt_globs and path.suffix.lower() in PROMPT_SUFFIXES + (".md",):
            rel = path.relative_to(root_path).as_posix()
            if any(_glob_match(rel, g) for g in config.prompt_globs):
                found.append(Found(path, "prompt"))
                seen.add(path)

    return found


MAX_PEEK_BYTES = 2_000_000


def looks_like_mcp(path: Path) -> bool:
    """Detect an MCP descriptor by shape rather than by filename.

    Names are unreliable — a descriptor can be called anything, and plenty of
    unrelated files are called mcp.json. Shape is not: a top-level `mcpServers`
    object, or a `tools` array whose entries have names, is unambiguous.
    """
    try:
        if path.stat().st_size > MAX_PEEK_BYTES:
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    if isinstance(data.get("mcpServers"), dict):
        return True
    tools = data.get("tools")
    if isinstance(tools, list) and tools:
        return all(isinstance(t, dict) and "name" in t for t in tools[:5])
    return False


def _walk(root: Path, config: Config) -> Iterator[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if config.excluded(path.relative_to(root)):
            continue
        yield path


def _glob_match(rel: str, pattern: str) -> bool:
    from fnmatch import fnmatch

    return fnmatch(rel, pattern) or fnmatch(rel, f"*/{pattern}")


def classify(path: Path) -> str:
    if path.is_dir():
        return "skill" if (path / "SKILL.md").exists() else "mcp"
    suffix = path.suffix.lower()
    if suffix in PROMPT_SUFFIXES:
        return "prompt"
    if suffix == ".md":
        if path.name == "SKILL.md":
            return "skill"
        try:
            head = path.read_text(encoding="utf-8")[:400]
        except OSError:
            return "prompt"
        if head.lstrip().startswith("---") and re.search(r"^name\s*:", head, re.M):
            return "skill"
        return "prompt"
    return "mcp"
