---
description: Bring the GitHub presence up to standard — reports first, changes only on approval
---

Audit and improve the public presence of this repository. **Report everything
before changing anything**, and stop for confirmation before anything
irreversible (see the hard rules in CLAUDE.md).

## 1. Correctness first

Run `/check`. If the tree does not pass, nothing about presentation matters yet.

## 2. Verify every public claim

Read `README.md` line by line against reality:

- Test count — run them and compare
- Rule counts per adapter — count the registries
- Version numbers in examples
- Roadmap markers — is "you are here" on the right line
- Every terminal block — re-run the command and confirm the output still matches

Report each mismatch. Stale numbers in a README are the cheapest possible way to
look unmaintained.

## 3. Repository metadata

Check and propose (do not apply yet):

- Description — one sentence, states the problem, not "a tool for X"
- Topics — `mcp`, `ai-agents`, `security`, `linter`, `model-context-protocol`
- Pinned repositories on the profile
- Social preview image

## 4. Known gaps become issues

Anything real and unfinished gets an issue rather than silence. Currently:

- `pin` / `diff` supports MCP only — not skills or prompts, though drift matters
  more for skills
- The playground's browser rendering has never been exercised by anyone
- Prompt rules have no eval layer; only skills have routing analysis

Write each as a problem statement, not a feature request. Do not open an issue
for something already fixed.

## 5. Report

Give me a list of what you would change, grouped by whether it needs my
approval. Then wait.
