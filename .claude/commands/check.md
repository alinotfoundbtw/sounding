---
description: Run every gate that must pass before committing
---

Run all four checks and report a single verdict. Do not fix anything yet — just
report.

```bash
python -m unittest discover -s tests
sounding selfaudit
sounding audit .
python tests/fuzz_manual.py
```

For each: pass or fail, and the specific failure if any.

If `selfaudit` dropped below 100, treat the rule that fired as suspect before
treating the manifest as wrong — that check has already caught two bad rules.

End with: **READY** or **NOT READY**, and the one thing blocking it.
