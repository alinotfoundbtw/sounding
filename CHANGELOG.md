# Changelog

Grouped as Added / Changed / Fixed. Every entry says what it means for someone
using the tool.

## Unreleased

### Fixed

- **The playground never ran.** `WHEEL_B64` was declared outside any `<script>`
  element, so the browser treated the embedded wheel as body text and every
  session died with `WHEEL_B64 is not defined`. The page had never been opened
  by anyone, which is how it shipped that way.
- **Terminal output was not UTF-8.** `print` used the console's codepage, so on
  Windows the `·)))` mark went out as a lone `0xB7` byte and a redirected report
  was mojibake. Under an ASCII stdout — `LC_ALL=C`, common in slim containers —
  a clean audit crashed with `UnicodeEncodeError`. Output is now UTF-8 on every
  platform, which is what the v0.9.3 note already claimed.
- **`pin` and `diff` crashed on skills and prompts.** They passed the path
  straight to the JSON loader regardless of kind, raising `PermissionError` on a
  skill directory and `JSONDecodeError` on a prompt. They now decline with a
  message and exit `1`. This matters most for `diff`, which exits `2` on real
  drift: a traceback in CI was indistinguishable from a changed tool contract.

### Changed

- **Every pasted README block is re-run in CI, not just `sounding audit .`.**
  Five of the six were unguarded, and four had drifted onto files that do not
  exist in the repo — `.mcp.json`, `answers.json`, `./skills`, `cases.json`.
  They now point at real fixtures and are reproduced command by command against
  a throwaway copy of the tree. A block may open with `[...]` to elide output
  shown elsewhere; everything kept still has to match exactly.
- The doc guard also checks that the playground's wheel constant is inside a
  script element. It previously matched the declaration as text and passed on a
  page that could not run — the failure its own comment warns about.
- CI runs the fuzz suite, which `CLAUDE.md` lists as a required gate but nothing
  enforced, and adds Python 3.13 to the matrix.
- The `eval` CI step asserted that the example skills collide. They do not, and
  never did, so the step could only have passed if the fixtures broke. Collision
  detection is covered in both directions in the test suite instead.

### Added

- `examples/notes-server-v2.json` — the drifted counterpart of
  `examples/clean-server.json`, so the pin-then-diff sequence in the README is
  two commands anyone can run.
- `examples/answers.json` and `examples/cases.json` — the inputs the `fix` and
  `eval` examples need. `answers.json` deliberately leaves one question open, so
  the "still unresolved" path is visible rather than described.
- Install from source in `README.md`, and a setup section in `CONTRIBUTING.md`,
  which told contributors to run `sounding selfaudit` without saying how to get
  `sounding`.

## 0.9.4

- The test suite made portable: two tests hardcoded `/tmp` and failed for every
  Windows user while an ubuntu-only matrix stayed green.

## 0.9.3

- Identical output on every platform.

## 0.9.2

- Docs enforced rather than remembered: pasted output and the embedded wheel are
  both re-checked in CI.

## 0.9.0

- Validated against third-party work. Running the rules over 35 skills written
  by other authors reported a false-positive rate near 46% and exposed four
  distinct defects, including a rule that flagged security guidance because it
  quoted an attack string.
