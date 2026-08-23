---
name: clean-skill
description: Convert tabular data between CSV, TSV, and JSON Lines. Use whenever the user asks to reformat, convert, or clean a .csv, .tsv, or .jsonl file, or mentions converting between these formats.
---

# Tabular conversion

Convert between CSV, TSV, and JSON Lines while preserving types.

## Process

1. Detect the delimiter from the first two lines rather than the extension —
   files are routinely misnamed.
2. Read the header row. If the first row looks like data, treat the file as
   headerless and generate positional names.
3. Convert, writing to a new file. Never overwrite the input.

## Types

Preserve integers, floats, and ISO-8601 dates. Everything else stays a string —
guessing types is how silent corruption happens.

```bash
convert input.csv --to jsonl --out output.jsonl
```

## When not to use this

For files above ~500MB, stream instead of loading — see references/streaming.md.
