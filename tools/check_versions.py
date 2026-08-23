"""Fail if the version disagrees anywhere.

Docs drifting out of sync with the code is a small problem for most projects
and a fatal one for this one: a tool that sells auditability cannot ship a
README describing commands that do not exist, or an install guide quoting a
test count from three versions ago.

So the agreement is enforced rather than remembered.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(msg: str) -> None:
    print(f"  MISMATCH  {msg}")


def main() -> int:
    problems = 0

    init = (ROOT / "src/sounding/__init__.py").read_text(encoding="utf-8")
    version = re.search(r'__version__ = "([^"]+)"', init).group(1)

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
    if declared != version:
        fail(f"pyproject.toml says {declared}, __init__.py says {version}")
        problems += 1

    # The playground embeds the wheel as base64, so there is no filename to
    # match on. An earlier version of this check grepped for one, found nothing,
    # and passed — a guard that cannot fail is worse than no guard, because it
    # is counted as protection. Decode the payload and read its metadata.
    playground = ROOT / "playground/index.html"
    if playground.exists():
        import base64
        import io
        import zipfile

        html = playground.read_text(encoding="utf-8")
        m = re.search(r'const WHEEL_B64 = "([A-Za-z0-9+/=]+)"', html)
        if not m:
            fail("playground/index.html has no embedded wheel")
            problems += 1
        # The wheel being correct is not the same as the wheel being reachable.
        # It shipped once with its opening <script> tag missing: the constant
        # rendered as body text, this check passed on it, and every run in the
        # browser died with "WHEEL_B64 is not defined". So confirm the
        # declaration is actually inside a script element.
        elif not any(
            m.group(0) in block
            for block in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
        ):
            fail("playground/index.html declares WHEEL_B64 outside any <script> block")
            problems += 1
        else:
            try:
                blob = base64.b64decode(m.group(1))
                with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                    meta = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
                    embedded = re.search(
                        r"^Version: (.+)$", zf.read(meta).decode(), re.M
                    ).group(1).strip()
            except Exception as exc:  # noqa: BLE001 - any failure is a finding
                fail(f"embedded wheel is unreadable: {type(exc).__name__}")
                problems += 1
            else:
                if embedded != version:
                    fail(f"embedded playground wheel is {embedded}, expected {version}")
                    problems += 1

                # And it must be the wheel actually built from this source.
                on_disk = sorted((ROOT / "playground").glob("*.whl"))
                if on_disk and on_disk[-1].read_bytes() != blob:
                    fail("embedded wheel differs from the one on disk")
                    problems += 1

    wheels = sorted(p.name for p in (ROOT / "playground").glob("*.whl"))
    unexpected = [w for w in wheels if version not in w]
    if unexpected:
        fail(f"stale wheel(s) in playground/: {unexpected}")
        problems += 1

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    markers = readme.count("← you are here")
    if markers != 1:
        fail(f"README roadmap has {markers} '← you are here' markers, expected exactly 1")
        problems += 1

    # Pasted terminal output goes stale exactly as silently as a number does,
    # and it is worse when it does: a README showing output the tool no longer
    # produces is the most direct possible contradiction of "auditable".
    #
    # This used to re-run only the blocks containing `audit .`, which left five
    # of six pasted blocks unguarded — and four of them had drifted onto files
    # that no longer exist in the repo. Every `$ sounding ...` line is re-run
    # now, in order, so a block showing a pin followed by a diff is reproduced
    # the way a reader would reproduce it.
    import os
    import shutil
    import tempfile

    def _norm(text: str) -> str:
        # Line endings differ by platform; content must not.
        lines = text.replace("\r\n", "\n").split("\n")
        return "\n".join(line.rstrip() for line in lines).strip()

    def _steps(block: str) -> list[tuple[str, str]]:
        """Split a block into (command, expected output) pairs."""
        out: list[tuple[str, str]] = []
        command: str | None = None
        buf: list[str] = []
        for line in block.split("\n"):
            if line.startswith("$ "):
                if command is not None:
                    out.append((command, "\n".join(buf)))
                command, buf = line[2:].strip(), []
            elif command is not None:
                buf.append(line)
        if command is not None:
            out.append((command, "\n".join(buf)))
        return out

    # Commands run against a throwaway copy of the tree: `pin` writes a
    # lockfile, and the repo is not the place for it.
    sandbox = Path(tempfile.mkdtemp(prefix="sounding-docs-")) / "repo"
    shutil.copytree(
        ROOT, sandbox,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".venv", ".git", "dist", "build",
            "*.egg-info", "sounding.lock.json", ".sounding-baseline.json",
        ),
    )
    try:
        for block in re.findall(r"```[a-z]*\n(\$ .*?)```", readme, re.S):
            for command, pasted in _steps(block):
                if not command.startswith("sounding "):
                    continue
                if "--interactive" in command:
                    continue  # needs a human on stdin; not reproducible
                live = subprocess.run(
                    [sys.executable, "-m", "sounding.cli", *command.split()[1:]],
                    cwd=sandbox, capture_output=True, text=True, encoding="utf-8",
                    env=dict(os.environ, NO_COLOR="1"),
                ).stdout.strip("\n")
                # A block may open with `[...]` to say "the tail of the real
                # output". `fix` prints a 90-line diff before its summary and
                # the diff is already shown elsewhere in the README; eliding it
                # is honest, pasting a doctored version would not be. Anything
                # kept still has to match exactly.
                want, got = _norm(pasted), _norm(live)
                elided = want.startswith("[...]")
                if elided:
                    want = want[len("[...]"):].strip()
                    ok = got.endswith(want)
                else:
                    ok = got == want
                if not ok:
                    fail(f"README block `$ {command}` no longer matches live output")
                    problems += 1
    finally:
        shutil.rmtree(sandbox.parent, ignore_errors=True)

    # Test counts quoted in prose go stale silently.
    #
    # Skipped when invoked from the suite itself: this script runs the tests,
    # and a test that runs this script would recurse until the machine gives up.
    # (It did.)
    if "--no-test-count" in sys.argv:
        if problems:
            print(f"\n{problems} version/doc mismatch(es).")
            return 1
        print(f"·))) versions agree: {version}")
        return 0

    actual = int(re.search(r"Ran (\d+) tests", subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stderr).group(1))
    for doc in ROOT.rglob("*.md"):
        if ".git" in doc.parts:
            continue
        for quoted in re.findall(r"\b(\d{2,4}) tests\b", doc.read_text(encoding="utf-8")):
            if int(quoted) != actual:
                fail(f"{doc.relative_to(ROOT)} says {quoted} tests, actual is {actual}")
                problems += 1

    if problems:
        print(f"\n{problems} version/doc mismatch(es).")
        return 1
    print(f"·))) versions agree: {version}, {actual} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
