"""Command line interface."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import MARK, __version__
from . import baseline as baseline_mod
from . import discover as discover_mod
from . import engine
from . import evals as evals_mod
from . import fix as fix_mod
from . import lockfile as lock_mod
from . import report as report_mod
from .loader import load
from .skillfile import load_skill
from .model import Report, Severity
from .rules import mcp, prompt as prompt_rules, skill as skill_rules


def _detect(path: str, forced: str | None = None) -> str:
    return engine.detect(path, forced)


def _audit_skill(args: argparse.Namespace) -> int:
    try:
        sk = load_skill(args.path)
    except OSError as exc:
        print(f"{MARK} cannot read {args.path}: {exc}", file=sys.stderr)
        return 2

    report = Report(subject=sk, findings=skill_rules.run_all(sk))
    report.findings = discover_mod.apply_config(
        report.findings, discover_mod.Config.load(args.path)
    )

    if args.format == "json":
        print(report_mod.as_json(report))
    elif args.format == "md":
        print(report_mod.markdown(report))
    else:
        print(report_mod.terminal(report))
        if args.interactive:
            answers = _ask(report)
            kept = {k: v for k, v in answers.items() if v not in ("skip", "not sure")}
            if kept:
                print("  Recorded. Run `sounding fix` to apply:")
                for k, v in kept.items():
                    print(f"    {k} = {v}")
                print()

    counts = report.counts()
    worst = 2 if counts["high"] else (1 if counts["medium"] else 0)
    if args.min_score is not None and report.score < args.min_score:
        print(
            f"{MARK} score {report.score} is below --min-score {args.min_score}",
            file=sys.stderr,
        )
        worst = 2
    if args.fail_on == "never":
        return 0
    if args.fail_on == "high":
        return 2 if worst >= 2 else 0
    return worst


def _report_for(path: Path, kind: str) -> Report:
    return engine.report_for(path, kind)


def _scan(args: argparse.Namespace) -> int:
    """Audit every artifact under a directory."""
    root = Path(args.path)
    config = discover_mod.Config.load(root)
    base = baseline_mod.Baseline.load(args.baseline) if args.baseline else baseline_mod.Baseline(set())
    found = discover_mod.discover(root, config)

    if not found:
        print(f"{MARK} NO CONTACTS — nothing auditable under {root}")
        if not config.prompt_globs:
            print("  (prompts are only picked up via promptGlobs in .sounding.json)")
        return 0

    rows: list[tuple[str, str, int, dict[str, int], int]] = []
    sarif_input: list[tuple[str, str, list]] = []
    all_entries: list[tuple[str, object]] = []
    worst = 0
    suppressed_total = 0

    for item in found:
        # Always POSIX separators. A report whose text depends on the operating
        # system cannot be diffed, pasted into a PR, or compared against a
        # previous run — and the SARIF writer already normalizes, so leaving
        # the table native made the two outputs disagree with each other.
        rel = (item.path.relative_to(root) if item.path != root else item.path).as_posix()
        try:
            report = _report_for(item.path, item.kind)
        except (OSError, ValueError) as exc:
            print(f"  {rel}: skipped ({exc})", file=sys.stderr)
            continue

        report.findings = discover_mod.apply_config(report.findings, config)
        all_entries.extend((rel, f) for f in report.findings)
        report.findings, suppressed = base.filter(rel, report.findings)
        suppressed_total += suppressed

        sarif_input.append((rel, item.kind, report.findings))
        rows.append((rel, item.kind, report.score, report.counts(), suppressed))

        counts = report.counts()
        if counts["high"]:
            worst = max(worst, 2)
        elif counts["medium"]:
            worst = max(worst, 1)

        if args.format == "text" and report.findings and args.verbose:
            print(report_mod.terminal(report))

    if args.write_baseline:
        payload = baseline_mod.Baseline.build(all_entries)  # type: ignore[arg-type]
        Path(args.write_baseline).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"{MARK} baseline written to {args.write_baseline} "
            f"({len(payload['accepted'])} findings suppressed)"
        )
        print("  These are a backlog, not a pass. CI will now fail only on new findings.")
        return 0

    if args.format == "sarif":
        print(baseline_mod.sarif(sarif_input))
        return 0
    if args.format == "json":
        print(json.dumps(
            {"root": str(root),
             "artifacts": [
                 {"path": r, "kind": k, "score": sc, "counts": c, "baselined": b}
                 for r, k, sc, c, b in rows
             ]}, indent=2))
        return 0

    _print_table(rows, suppressed_total, config)

    min_score = args.min_score if args.min_score is not None else config.min_score
    if min_score is not None and any(sc < min_score for _, _, sc, _, _ in rows):
        print(f"{MARK} at least one artifact is below --min-score {min_score}", file=sys.stderr)
        worst = 2

    fail_on = args.fail_on or config.fail_on or "high"
    if fail_on == "never":
        return 0
    if fail_on == "high":
        return 2 if worst >= 2 else 0
    return worst


def _print_table(rows, suppressed: int, config) -> None:
    if not rows:
        return
    width = max(len(r[0]) for r in rows)
    width = min(max(width, 12), 60)
    print()
    print(f"{MARK} {len(rows)} artifact(s)")
    print()
    print(f"  {'ARTIFACT'.ljust(width)}  {'KIND'.ljust(7)} {'SCORE':>5}   FINDINGS")
    for rel, kind, score, counts, baselined in sorted(rows, key=lambda r: r[2]):
        label = rel if len(rel) <= width else "..." + rel[-(width - 3):]
        if any(counts.values()):
            detail = f"{counts['high']}h {counts['medium']}m {counts['low']}l"
        elif baselined:
            # Not clean — accepted. Saying "clean" here would be a lie.
            detail = f"{baselined} baselined"
        else:
            detail = "clean"
        print(f"  {label.ljust(width)}  {kind.ljust(7)} {score:>5}   {detail}")
    print()
    total = sum(sc for _, _, sc, _, _ in rows) // len(rows)
    print(f"  mean score {total}/100")
    if suppressed:
        print(
            f"  {suppressed} finding(s) suppressed by baseline — a backlog, not a pass"
        )
    if config.source:
        print(f"  config: {config.source}")
    print()


def _audit_prompt(args: argparse.Namespace) -> int:
    pr = prompt_rules.load_prompt(args.path)
    report = Report(
        subject=pr, findings=prompt_rules.run_all(pr, getattr(args, "profile", None))
    )
    report.findings = discover_mod.apply_config(
        report.findings, discover_mod.Config.load(args.path)
    )
    if args.format == "json":
        print(report_mod.as_json(report))
    elif args.format == "md":
        print(report_mod.markdown(report))
    else:
        print(report_mod.terminal(report))
        _profile_line(pr)
        if args.interactive:
            _ask(report)
    counts = report.counts()
    worst = 2 if counts["high"] else (1 if counts["medium"] else 0)
    if args.fail_on == "never":
        return 0
    if args.fail_on == "high":
        return 2 if worst >= 2 else 0
    return worst


def _audit(args: argparse.Namespace) -> int:
    p = Path(args.path)
    if p.is_dir() and not (p / "SKILL.md").exists():
        return _scan(args)
    kind = _detect(args.path, args.type)
    if kind == "skill":
        return _audit_skill(args)
    if kind == "prompt":
        return _audit_prompt(args)

    try:
        servers = load(args.path)
    except (OSError, ValueError) as exc:
        print(f"{MARK} cannot read {args.path}: {exc}", file=sys.stderr)
        return 2

    worst = 0
    for server in servers:
        report = Report(subject=server, findings=mcp.run_all(server))
        report.findings = discover_mod.apply_config(
            report.findings, discover_mod.Config.load(args.path)
        )

        if args.format == "json":
            print(report_mod.as_json(report))
        elif args.format == "md":
            print(report_mod.markdown(report))
        else:
            print(report_mod.terminal(report))

        if args.interactive and args.format == "text":
            answers = _ask(report)
            kept = {k: v for k, v in answers.items() if v not in ("skip", "not sure")}
            if kept:
                print("  Recorded. Run `sounding fix` to apply:")
                for k, v in kept.items():
                    print(f"    {k} = {v}")
                print()

        counts = report.counts()
        if counts["high"]:
            worst = max(worst, 2)
        elif counts["medium"]:
            worst = max(worst, 1)

        if args.min_score is not None and report.score < args.min_score:
            print(
                f"{MARK} score {report.score} is below --min-score {args.min_score}",
                file=sys.stderr,
            )
            worst = max(worst, 2)

    if args.fail_on == "never":
        return 0
    if args.fail_on == "high":
        return 2 if worst >= 2 else 0
    return worst  # "any"


def _ask(report: Report, limit: int = 3) -> dict[str, str]:
    questions = report.questions(limit=limit)
    if not questions:
        return {}
    print("  Answering these produces the corrections. Ctrl-C to stop.\n")
    answers: dict[str, str] = {}
    for q in questions:
        opts = q.options + (["not sure", "skip"] if q.allow_unknown else [])
        print(f"  {q.prompt}")
        for i, opt in enumerate(opts, 1):
            print(f"    {i}) {opt}")
        try:
            raw = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  stopped.\n")
            return answers
        try:
            choice = opts[int(raw) - 1]
        except (ValueError, IndexError):
            choice = "skip"
        answers[q.id] = choice
        print()

    return answers


def _fix_skill(args: argparse.Namespace) -> int:
    from . import patch as patch_mod

    sk = load_skill(args.path)
    report = Report(subject=sk, findings=skill_rules.run_all(sk))

    answers: dict[str, str] = {}
    if args.answers:
        answers.update(json.loads(Path(args.answers).read_text(encoding="utf-8")))
    if args.interactive:
        print(report_mod.terminal(report))
        answers.update(_ask(report))

    fp = fix_mod.plan(report, answers)
    src_path = sk.path
    assert src_path is not None
    before = src_path.read_text(encoding="utf-8")
    after, applied = patch_mod.apply_frontmatter(before, fp.patches)

    if not applied:
        print(f"{MARK} nothing to apply.")
        if fp.unresolved:
            print("\n  These need a decision first (`--interactive`):")
            for u in fp.unresolved:
                print(f"    {u}")
            print()
        return 0

    import difflib

    print(
        "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{src_path.name}",
                tofile=f"b/{src_path.name}",
                n=2,
            )
        )
    )
    print()
    print(f"{MARK} {len(applied)} change(s):")
    print(fix_mod.summarize(applied))

    if fp.todo_count:
        print()
        print(
            f"  {fp.todo_count} of these are scaffolds marked TODO. "
            "They are placeholders, not finished work — edit them before shipping."
        )
    if fp.unresolved:
        print()
        print("  Still unresolved:")
        for u in fp.unresolved:
            print(f"    {u}")

    if args.write:
        if not args.no_backup:
            src_path.with_suffix(".md.bak").write_text(before, encoding="utf-8")
        src_path.write_text(after, encoding="utf-8")
        print()
        print(f"{MARK} wrote {src_path}")
    else:
        print()
        print("  Dry run. Re-run with --write to apply.")

    print()
    print("  Body text is never rewritten — prose is yours.")
    return 0


def _fix_prompt(args: argparse.Namespace) -> int:
    from . import patch as patch_mod

    pr = prompt_rules.load_prompt(args.path)
    report = Report(
        subject=pr, findings=prompt_rules.run_all(pr, getattr(args, "profile", None))
    )
    answers: dict[str, str] = {}
    if args.answers:
        answers.update(json.loads(Path(args.answers).read_text(encoding="utf-8")))
    if args.interactive:
        print(report_mod.terminal(report))
        answers.update(_ask(report))

    fp = fix_mod.plan(report, answers)
    before = pr.text
    after, applied = patch_mod.apply_append(before, fp.patches)
    if not applied:
        print(f"{MARK} nothing to apply.")
        if fp.unresolved:
            print("\n  These need a decision first (`--interactive`):")
            for u in fp.unresolved:
                print(f"    {u}")
            print()
        return 0

    import difflib

    print("".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="a/" + Path(args.path).name, tofile="b/" + Path(args.path).name, n=2)))
    print()
    print(f"{MARK} {len(applied)} change(s):")
    print(fix_mod.summarize(applied))
    if args.write:
        assert pr.path is not None
        if not args.no_backup:
            pr.path.with_suffix(pr.path.suffix + ".bak").write_text(before, encoding="utf-8")
        pr.path.write_text(after, encoding="utf-8")
        print(f"\n{MARK} wrote {pr.path}")
    else:
        print("\n  Dry run. Re-run with --write to apply.")
    print("\n  Your existing wording is never rewritten — clauses are appended.")
    return 0


def _fix(args: argparse.Namespace) -> int:
    kind = _detect(args.path, args.type)
    if kind == "skill":
        return _fix_skill(args)
    if kind == "prompt":
        return _fix_prompt(args)
    try:
        servers = load(args.path)
    except (OSError, ValueError) as exc:
        print(f"{MARK} cannot read {args.path}: {exc}", file=sys.stderr)
        return 2
    if len(servers) != 1:
        print(f"{MARK} fix works on one server at a time, found {len(servers)}", file=sys.stderr)
        return 2

    server = servers[0]
    report = Report(subject=server, findings=mcp.run_all(server))

    answers: dict[str, str] = {}
    if args.answers:
        answers.update(json.loads(Path(args.answers).read_text(encoding="utf-8")))
    if args.interactive:
        print(report_mod.terminal(report))
        answers.update(_ask(report))

    fp = fix_mod.plan(report, answers)
    after, applied = fix_mod.apply(server.raw, fp.patches)

    if not applied:
        print(f"{MARK} nothing to apply.")
        if fp.unresolved:
            print("\n  These need a decision first (`--interactive`):")
            for u in fp.unresolved:
                print(f"    {u}")
            print()
        return 0

    d = fix_mod.diff(server.raw, after, name=Path(args.path).name)
    print(d if d else "  (no textual change)")
    print()
    print(f"{MARK} {len(applied)} change(s):")
    print(fix_mod.summarize(applied))

    if fp.todo_count:
        print()
        print(
            f"  {fp.todo_count} of these are scaffolds marked TODO. "
            "They are placeholders, not finished work — edit them before shipping."
        )

    if fp.unresolved:
        print()
        print("  Still unresolved:")
        for u in fp.unresolved:
            print(f"    {u}")

    if args.write:
        out = fix_mod.write(args.path, after, backup=not args.no_backup)
        print()
        print(f"{MARK} wrote {out}" + ("" if args.no_backup else f" (backup: {out}.bak)"))
    else:
        print()
        print("  Dry run. Re-run with --write to apply.")
    return 0


def _refuse_non_mcp(path: str, command: str) -> str | None:
    """`pin` and `diff` read a tool contract, and only MCP artifacts have one.

    They used to hand the path straight to the JSON loader and die with whatever
    the OS or json module raised — PermissionError on a skill directory,
    JSONDecodeError on a prompt. That is bad on its own for a tool that promises
    to report structural problems rather than raise them, and worse for `diff`,
    which exits 2 for genuine drift: a traceback in CI was indistinguishable
    from a changed tool contract.

    Returns the refusal message, or None when the artifact really is MCP.
    """
    if not Path(path).exists():
        return f"{MARK} no such path: {path}"
    kind = _detect(path)
    if kind == "mcp":
        return None
    return (
        f"{MARK} `{command}` supports MCP descriptors only — {path} is a {kind}.\n"
        f"  Drift for skills and prompts is not tracked yet. `sounding audit` "
        f"handles this artifact."
    )


def _pin(args: argparse.Namespace) -> int:
    refusal = _refuse_non_mcp(args.path, "pin")
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 1
    servers = load(args.path)
    out = lock_mod.write(servers, args.out)
    total = sum(len(s.tools) for s in servers)
    print(f"{MARK} pinned {len(servers)} server(s), {total} tool(s) -> {out}")
    return 0


def _diff(args: argparse.Namespace) -> int:
    refusal = _refuse_non_mcp(args.path, "diff")
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 1
    if not Path(args.lock).exists():
        print(f"{MARK} no lockfile at {args.lock}. Run `sounding pin` first.", file=sys.stderr)
        return 2
    servers = load(args.path)
    drift = lock_mod.diff(servers, lock_mod.read(args.lock))
    if not drift:
        print(f"{MARK} NO CONTACTS — nothing changed since the last pin.")
        return 0
    print(f"{MARK} drift detected:\n")
    for line in drift:
        print(f"  {line}")
    print()
    contract_changed = any(line.startswith("!") for line in drift)
    return 2 if contract_changed else 1


def _candidates(root: Path) -> list:
    config = discover_mod.Config.load(root)
    out = []
    for item in discover_mod.discover(root, config):
        if item.kind != "skill":
            continue
        sk = load_skill(item.path)
        out.append(evals_mod.Candidate(
            name=sk.name or sk.stem,
            description=sk.description,
            path=str(item.path),
        ))
    return out


def _eval(args: argparse.Namespace) -> int:
    root = Path(args.path)
    candidates = _candidates(root)
    if not candidates:
        print(f"{MARK} NO CONTACTS — no skills found under {root}", file=sys.stderr)
        return 2

    if args.scaffold:
        payload = evals_mod.scaffold(candidates)
        Path(args.scaffold).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"{MARK} wrote {len(payload['cases'])} stub case(s) to {args.scaffold}")
        print("  Every task is a TODO. Replace them with how users actually phrase it —")
        print("  a case copied from the description only proves it matches itself.")
        return 0

    cases = evals_mod.load_cases(args.cases) if args.cases else []
    report = evals_mod.run(candidates, cases)

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_eval(report, args.path)

    if args.min_accuracy is not None and cases:
        if report.accuracy < args.min_accuracy:
            print(
                f"{MARK} accuracy {report.accuracy:.0%} is below "
                f"--min-accuracy {args.min_accuracy:.0%}",
                file=sys.stderr,
            )
            return 2
    return 1 if (report.failures() or report.collisions) else 0


def _profile_line(pr) -> None:
    from .rules import profiles as profiles_mod

    if not getattr(pr, "profile", ""):
        return
    prof = profiles_mod.PROFILES[pr.profile]
    done, total = profiles_mod.coverage(pr.text, prof)
    print(f"  profile   {prof.label} — {done}/{total} dimensions addressed")
    if prof.note:
        print()
        for line in _wrap(prof.note, 68):
            print(f"  {line}")
    print()


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width)


def _print_eval(report, path: str) -> None:
    print()
    print(f"{MARK}  eval — {report.candidates} skill(s) under {path}")
    print()
    print("  Measures trigger selection only: whether the right skill would be")
    print("  chosen, not whether its instructions work. Lexical proxy, not a model.")
    print()

    if report.total:
        print(f"  routing   {report.passed}/{report.total} decisive and correct"
              f"   ({report.accuracy:.0%})")
        print()
        for o in report.failures():
            if o.unmatched:
                print(f"  MISS    {o.case.task[:64]!r}")
                print(f"          expected {o.case.expect}, nothing matched at all")
            else:
                print(f"  WRONG   {o.case.task[:64]!r}")
                print(f"          expected {o.case.expect}, chose {o.chosen}")
            print()
        for o in report.ambiguous():
            print(f"  CLOSE   {o.case.task[:64]!r}")
            print(f"          {o.chosen} beat {o.runner_up} by {o.margin:.2f} — a coin flip")
            print()
    else:
        print("  No cases supplied. Ran collision analysis only.")
        print("  `--scaffold cases.json` writes a starting case file.")
        print()

    if report.collisions:
        print("  Descriptions competing for the same vocabulary:")
        for a, b, v in report.collisions:
            print(f"    {a} <-> {b}   {v:.0%} overlap")
        print()
        print("  Whichever wins, it will not be for a reason either author chose.")
        print()
    elif report.candidates > 1:
        print("  No description collisions.")
        print()


def _serve(_args: argparse.Namespace) -> int:
    from .server import serve

    return serve()


def _selfaudit(_args: argparse.Namespace) -> int:
    """Run the MCP rule set against this server's own manifest."""
    from .loader import _server_from_entry
    from .server import manifest

    server = _server_from_entry("sounding", manifest())
    report = Report(subject=server, findings=mcp.run_all(server))
    print(report_mod.terminal(report))
    if report.findings:
        print("  A tool that audits MCP servers has to pass its own rules.\n")
        return 2
    return 0


def _rules(_args: argparse.Namespace) -> int:
    print(f"{MARK} sounding {__version__}\n")
    for label, registry in (
        ("MCP servers", mcp.REGISTRY),
        ("Agent Skills", skill_rules.REGISTRY),
        ("Prompts", prompt_rules.REGISTRY),
    ):
        print(f"  {label}")
        for code, fn in registry:
            doc = (fn.__doc__ or "").strip().splitlines()
            summary = doc[0] if doc else fn.__name__.replace("_", " ")
            print(f"    {code}  {summary}")
        print()
    print("  Severity weights: high 15 · medium 7 · low 3")
    print("  Score = 100 - sum(weights), floored at 0")
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sounding",
        description=(
            "Governance for agent instructions. v0.1 audits MCP servers: "
            "static analysis of the declared tool contract. Nothing is executed."
        ),
    )
    p.add_argument("--version", action="version", version=f"sounding {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("audit", help="audit a server descriptor or client config")
    a.add_argument("path", help="MCP descriptor/config (.json) or a skill (SKILL.md or its directory)")
    a.add_argument("--format", choices=["text", "json", "md", "sarif"], default="text")
    a.add_argument("--type", choices=["mcp", "skill", "prompt"], default=None,
                   help="override adapter detection")
    a.add_argument("--profile", default=None,
                   help="prompt profile: image, extraction, agent, or none (default: auto-detect)")
    a.add_argument("--interactive", action="store_true", help="answer open questions")
    a.add_argument("--min-score", type=int, default=None)
    a.add_argument("--baseline", nargs="?", const=baseline_mod.BASELINE_NAME,
                   default=None, help="suppress findings recorded in a baseline file")
    a.add_argument("--write-baseline", nargs="?", const=baseline_mod.BASELINE_NAME,
                   default=None, help="record current findings as accepted")
    a.add_argument("--verbose", action="store_true",
                   help="in a directory scan, print every finding")
    a.add_argument(
        "--fail-on",
        choices=["any", "high", "never"],
        default="high",
        help="exit non-zero on findings at or above this level (default: high)",
    )
    a.set_defaults(func=_audit)

    f = sub.add_parser("fix", help="apply corrections to the source descriptor")
    f.add_argument("path")
    f.add_argument("--write", action="store_true", help="apply changes (default is a dry run)")
    f.add_argument("--interactive", action="store_true", help="answer open questions first")
    f.add_argument("--answers", help="JSON file of {question_id: chosen option}")
    f.add_argument("--no-backup", action="store_true")
    f.add_argument("--type", choices=["mcp", "skill", "prompt"], default=None)
    f.add_argument("--profile", default=None)
    f.set_defaults(func=_fix)

    pin = sub.add_parser("pin", help="write a lockfile of current tool contracts")
    pin.add_argument("path")
    pin.add_argument("--out", default=lock_mod.LOCK_NAME)
    pin.set_defaults(func=_pin)

    d = sub.add_parser("diff", help="detect drift against the lockfile")
    d.add_argument("path")
    d.add_argument("--lock", default=lock_mod.LOCK_NAME)
    d.set_defaults(func=_diff)

    e = sub.add_parser("eval", help="measure whether skills trigger on the right tasks")
    e.add_argument("path", help="directory containing skills")
    e.add_argument("--cases", help="JSON file of {task, expect} pairs")
    e.add_argument("--scaffold", help="write a starting case file and exit")
    e.add_argument("--min-accuracy", type=float, default=None)
    e.add_argument("--format", choices=["text", "json"], default="text")
    e.set_defaults(func=_eval)

    sv = sub.add_parser("serve", help="run as an MCP server over stdio")
    sv.set_defaults(func=_serve)

    sa = sub.add_parser("selfaudit", help="audit this server's own tool manifest")
    sa.set_defaults(func=_selfaudit)

    r = sub.add_parser("rules", help="list the rule set and the scoring formula")
    r.set_defaults(func=_rules)

    return p


def _force_utf8_output() -> None:
    """Emit UTF-8 regardless of the console's codepage.

    Files are read and written as UTF-8 everywhere in this package, but stdout
    inherited the locale encoding. On a cp1252 Windows console the mark went out
    as a single 0xB7 byte, so redirecting a report to a file produced mojibake;
    under an ASCII stdout (`LC_ALL=C`, common in slim containers) `print` raised
    UnicodeEncodeError and the CLI died on a clean audit.

    `errors="replace"` is deliberate belt and braces: a report that renders one
    character wrong is a cosmetic problem, and a linter that crashes while
    reporting is not.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # not a TextIOWrapper (captured, redirected in-process)
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # already detached, or not reconfigurable
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
