## Problem

<!-- What was wrong. Lead with this, not with the change. -->

## Change

## Checks

- [ ] `python -m unittest discover -s tests`
- [ ] `sounding selfaudit` — 100/100
- [ ] `sounding audit .` — clean fixtures still clean
- [ ] `python tests/fuzz_manual.py` — 0 crashes

## If this adds or changes a rule

- [ ] Tested in both directions: fires on the bad case, silent on a good one
- [ ] Carries a reference and a fix or question
- [ ] Measured against third-party artifacts — hit rate: <!-- n of m -->
