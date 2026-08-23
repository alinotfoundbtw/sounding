---
description: Add a lint rule with the full discipline — fixtures, both directions, corpus check
argument-hint: [adapter: mcp|skill|prompt] [what it should catch]
---

Add a rule to $ARGUMENTS.

Follow the sequence, and do not skip step 2:

1. **Write the failing fixture first** — the artifact that should trigger it.
2. **Write the fixture that must NOT trigger it.** A plausible, well-written
   artifact that a careless pattern would catch. If you cannot think of one, the
   rule is probably too broad to add.
3. Implement the rule in `src/sounding/rules/`. It needs:
   - a `reference` — the spec section or documented practice. Not optional.
   - a `fix` string, or a `question` with options when intent is required
   - a severity: 15 / 7 / 3. When unsure, pick lower.
4. **Two tests**: fires on the bad case, silent on the good case.
5. Run `/check`.
6. Report the rule code, both fixtures, and what severity you chose and why.

Reminder: false positives are how a linter loses its audience. A rule that fires
on careful work is worse than no rule.
