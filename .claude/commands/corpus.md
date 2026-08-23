---
description: Measure false positives against skills written by other people
argument-hint: [path to a directory of third-party skills]
---

Audit every skill under $ARGUMENTS — work we did not write — and report.

For each skill: score and the rule codes that fired. Then aggregate:

- mean and median score
- how many scored 100
- a count per rule code, worst first
- for any rule firing on more than ~15% of the corpus, quote two real examples

**Then judge each firing rule honestly:** is it a real defect in their work, or
a defect in our rule? Assume ours until proven otherwise. The first corpus run
found a 46% false-positive rate and four defects, including a rule that flagged
security guidance because it quoted an attack string.

Do not change any rule yet. Report first, with a recommendation per rule.

If a rule needs loosening, also state how you will verify it **still fires** on
genuinely bad input — tuning until the corpus is green is the same failure
wearing a different mask.
