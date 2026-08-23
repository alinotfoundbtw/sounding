"""Load a SKILL.md.

Frontmatter is parsed with a deliberately small YAML subset: `key: value`,
quoted strings, and inline `[a, b]` lists. That covers every skill in the wild
and keeps the dependency count at zero, which matters more for a linter than
handling exotic YAML nobody writes.

Malformed frontmatter is not an exception — it is a finding. The loader
records what it could not parse and lets the rules report it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FENCE = re.compile(r"^---\s*$", re.M)
KEY_LINE = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$")


@dataclass
class Skill:
    kind: str = "skill"
    name: str = ""
    version: str = ""
    description: str = ""
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    path: Path | None = None
    base_dir: Path | None = None
    has_frontmatter: bool = True
    parse_errors: list[str] = field(default_factory=list)

    @property
    def stem(self) -> str:
        """Directory name — what `name` is supposed to match."""
        if self.base_dir is None:
            return ""
        return self.base_dir.name


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


BLOCK_SCALAR = re.compile(r"^([|>])([+-]?\d*)$")


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], list[str]]:
    """A small YAML subset: key/value, quoted strings, inline lists, and block
    scalars.

    Block scalars matter more than they look. Long trigger descriptions are
    written as `description: |` in a third of real skills, and a parser that
    treats their body as broken syntax reports a dozen phantom findings and
    then reads the description as one character long — which cascades into
    every other rule.
    """
    data: dict[str, Any] = {}
    errors: list[str] = []
    current_key: str | None = None
    buffer: list[str] = []
    fold = False  # `>` folds newlines into spaces; `|` keeps them

    def flush() -> None:
        nonlocal current_key, buffer, fold
        if current_key is not None:
            if fold:
                data[current_key] = " ".join(x.strip() for x in buffer if x.strip())
            else:
                data[current_key] = "\n".join(buffer).strip()
        current_key, buffer, fold = None, [], False

    lines = text.splitlines()
    for raw_line in lines:
        line = raw_line.rstrip()

        if current_key is not None:
            if not line.strip():
                buffer.append("")
                continue
            if raw_line.startswith((" ", "\t")):
                buffer.append(line.strip() if fold else line.lstrip())
                continue

        if not line.strip():
            continue

        m = KEY_LINE.match(line)
        if not m:
            errors.append(f"cannot parse frontmatter line: {line.strip()[:60]}")
            continue

        flush()
        key, value = m.group(1), m.group(2).strip()

        block = BLOCK_SCALAR.match(value)
        if block:
            current_key, buffer, fold = key, [], block.group(1) == ">"
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [_unquote(x) for x in inner.split(",") if x.strip()] if inner else []
        elif value == "":
            current_key, buffer, fold = key, [], True
        else:
            data[key] = _unquote(value)

    flush()
    return data, errors


def load_skill(path: str | Path) -> Skill:
    p = Path(path)
    if p.is_dir():
        p = p / "SKILL.md"
    text = p.read_text(encoding="utf-8")

    parts = FENCE.split(text, maxsplit=2)
    if text.lstrip().startswith("---") and len(parts) >= 3:
        fm_text, body = parts[1], parts[2]
        fm, errors = _parse_frontmatter(fm_text)
        has_fm = True
    else:
        fm, errors, body, has_fm = {}, [], text, False

    return Skill(
        name=str(fm.get("name", "") or ""),
        version=str(fm.get("version", "") or ""),
        description=str(fm.get("description", "") or ""),
        frontmatter=fm,
        body=body,
        path=p,
        base_dir=p.parent,
        has_frontmatter=has_fm,
        parse_errors=errors,
    )
