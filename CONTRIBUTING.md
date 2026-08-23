# Contributing

## The bar for a rule

A rule that fires on well-written work is worse than no rule — it teaches people
to ignore the output, and then the real findings go unread too.

So every rule must:

1. **Be deterministic.** No model, no network. Same input, same output.
2. **Carry a reference.** The spec section or documented practice that says this
   matters. A finding without one is an opinion.
3. **Carry a fix, or a question.** "This is wrong" without "here is what to do"
   wastes the reader's time.
4. **Be tested in both directions.** It fires on the bad case *and* stays silent
   on a good one. A rule tuned until it never fires has failed differently, not
   less.

## Validate against work you did not write

Rules and fixtures written by the same person always agree with each other. The
only real test is a corpus by other authors.

The first time this repo did that — 35 professionally-written skills — the false
positive rate was 46% and it exposed four defects, including a rule that flagged
security guidance *because it quoted an attack string it was warning about*.

If you add a rule, measure its hit rate on real third-party artifacts and put
the number in the PR. "It passed my fixtures" is not validation.

## Setting up

```bash
git clone https://github.com/alinotfoundbtw/sounding
cd sounding
python -m venv .venv && . .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -e .
```

Python 3.10 or newer, and nothing else to install.

## Before opening a PR

```bash
python -m unittest discover -s tests
sounding selfaudit          # must be 100/100
sounding audit .
python tests/fuzz_manual.py # must report 0 crashes
```

`selfaudit` runs the MCP rules against this tool's own server manifest. If your
change breaks it, the rule is probably wrong.

## Dependencies

There are none, and that is deliberate — it installs anywhere, including in a
browser via Pyodide. Adding one needs a strong argument in the PR.

## Style

English only. Sentence case. Plain verbs. Explain *why* in commit messages; the
diff already says what.
