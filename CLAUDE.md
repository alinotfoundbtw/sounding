# CLAUDE.md

Operating instructions for this repository. Read this before doing anything.

---

## Identity

Everything public in this repo belongs to **alinotfound**.

- **English only.** No Persian anywhere — code, comments, commits, issues,
  releases, docs. Not in a commit message, not in a TODO.
- **No real name.** Never add one to a file, a commit author line, a changelog,
  a README, or an issue. If a config or credential surfaces one, stop and say
  so rather than committing it.
- **The mark is `·)))`** and it belongs in the README footer and the console
  signature. Nowhere else. It is a signature, not decoration.

---

## What this project is

`sounding` audits agent instructions — MCP servers, Agent Skills, and prompts —
for structural problems, scores them with a visible formula, writes the
corrections, and pins them so drift is caught.

The product is **trustworthiness**. Every decision follows from that:

- A finding without a reference is an opinion. This tool does not ship opinions.
- A score whose formula is hidden is a vibe. The formula is always printed.
- Nothing is written to disk without being shown first.
- Generated text that still needs a human says `TODO` inside itself.
- The tool states plainly what it does not check.

If a change makes the tool more impressive but less honest, it is the wrong
change. Say so instead of making it.

---

## Hard rules

These need explicit approval from the user, every time. Never assume it.

- `git push --force` or `--force-with-lease` on `main`
- Deleting or renaming a repository, or changing its visibility
- Publishing to PyPI, npm, or any registry
- Rewriting history: `rebase` on pushed commits, `filter-branch`, amending a
  pushed commit
- Adding a dependency — this package has **zero** and that is a feature
- Anything touching credentials, tokens, or `security.txt` contact details

Never, under any circumstances:

- Commit a secret, a token, an API key, or a `.env` with real values
- Invent numbers. No download counts, no user counts, no benchmark results that
  were not actually measured. If a number appears in public text, it must be
  reproducible by running something in this repo.
- Add a badge for something that does not exist
- Write "trusted by" or testimonials

---

## Before any commit

Run all four. A failure in any one means do not commit.

```bash
python -m unittest discover -s tests    # the full suite
sounding selfaudit                       # must be 100/100
sounding audit .                         # clean fixtures stay clean
python tests/fuzz_manual.py              # must report 0 crashes
```

`sounding selfaudit` runs this tool's rules against its own MCP manifest. If a
change to a rule breaks it, the rule is probably wrong — that check has already
caught two bad rules.

---

## Adding or changing a rule

1. **It must be deterministic.** No model, no network, no randomness. Same
   input, same output.
2. **It must carry a reference.** Which spec section or documented practice says
   this matters. The test suite fails on a finding without one.
3. **It must carry a fix or a question.** A finding that only says "this is
   wrong" wastes the reader's time.
4. **It must be tested in both directions.** One test that it fires on the bad
   case, one that it stays silent on the good case. Tuning until nothing fires
   is the same failure as firing on everything.
5. **Validate against work we did not write.** Rules written and tested by the
   same person always agree with themselves. Run against a corpus of real
   third-party skills before believing a rule is correct. The first time this
   was done it exposed a 46% false-positive rate and four defects — one of them
   a rule that flagged *security guidance* because it quoted an attack string.

False positives are how a linter loses its audience. When unsure, lower the
severity rather than deleting the rule, and say why in a comment.

---

## Writing style for everything public

README, commit messages, issue replies, release notes, docs. One voice.

- **Quiet, precise, technical. Never cute.** One line where most projects write
  three.
- **Lead with the problem, not the feature.** "Tool descriptions decide which
  tool gets called and nobody reviews them" beats "sounding is a powerful
  linting tool".
- **Show real output.** Paste an actual terminal block. Never mock one up, and
  never edit one to look better than it is.
- **Name limitations in the README, not a footnote.** The scope section exists
  because a security tool that oversells is worse than none.
- Sentence case. Plain verbs. No emoji. No exclamation marks.
- Banned: "elevate", "seamless", "empower", "unlock", "leverage", "revolutionary",
  "game-changing", "blazing fast", "simply", "just".

### Commits

Conventional commits, imperative mood, lowercase subject, no trailing period.

```
fix(skill): parse YAML block scalars in frontmatter

`description: |` was read as broken syntax, which cascaded into every
other rule — the description then measured one character long.

Found by auditing 35 third-party skills: 11 of them use block scalars.
```

Explain **why**, not what — the diff already says what. If a change came from a
real failure, say which failure.

### Pull requests

Even solo. One PR per change, description states the problem first, CI green
before merge. The public history is part of the portfolio.

### Releases

Tag `v0.9.0`, notes grouped as Added / Changed / Fixed, each line pointing at
what it means for someone using the tool. Link the diff.

---

## Repository standards

Every repo under this account has, and CI verifies:

- `README.md` opening with the problem, real output, and an honest scope section
- `LICENSE` (MIT)
- `SECURITY.md` with a working disclosure route
- `.github/workflows/ci.yml` running the full check list on 3.10, 3.11, 3.12
- Topics set, description set, no default "No description provided"
- No committed build artifacts, no `.bak`, no `__pycache__`, no `dist/`

---

## Repo layout

```
src/sounding/
  engine.py        one place an artifact becomes a report — CLI and MCP server
                   both call this, so they can never disagree
  model.py         Finding, Question, Report, Severity
  patch.py         corrections as data
  rules/           mcp.py · skill.py · prompt.py · profiles.py
  server.py        MCP server; its own manifest must pass mcp.py
  discover.py      project scan + config
  baseline.py      baseline + SARIF
  evals.py         trigger routing (BM25, deterministic)
playground/        single self-contained HTML, wheel embedded as base64
tests/             the suite, including fuzz and corpus regressions
```

**Do not duplicate detection logic.** It lived in three copies once and that is
exactly how the CLI and the MCP server start disagreeing about what a file is.

---

## When asked to "make the GitHub better"

Do these, in this order, and stop to confirm before anything irreversible:

1. Verify the four checks above pass
2. Repo description, topics, and pinned repos
3. README accuracy — every claim in it must be true today
4. Open issues for known gaps rather than quietly leaving them:
   `pin`/`diff` still only supports MCP, not skills or prompts; the playground's
   browser rendering has never been opened by anyone
5. Release notes for the current version

Do not open an issue for something already fixed, and do not close one without
saying what fixed it.
