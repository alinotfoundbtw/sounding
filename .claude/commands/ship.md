---
description: Prepare a release — does not publish
argument-hint: [version]
---

Prepare release $ARGUMENTS. Do not push a tag and do not publish anything
without explicit confirmation.

1. Run `/check`. Stop if anything fails.
2. Bump the version in `src/sounding/__init__.py` and `pyproject.toml`. They
   must match.
3. Rebuild the playground wheel and re-embed it:
   ```bash
   rm -f playground/*.whl
   python -m build --wheel --outdir playground/
   ```
   then replace `WHEEL_B64` in `playground/index.html` with the new base64.
   Verify the embedded bytes start with `PK`.
4. Re-read the README top to bottom. Every claim must be true of this version —
   test counts, rule counts, feature list, roadmap marker. Fix anything stale.
5. Draft release notes: Added / Changed / Fixed, each line saying what it means
   for someone using the tool.
6. Show me the diff and the notes. Wait for approval before tagging.
