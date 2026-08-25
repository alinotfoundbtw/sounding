# sounding `·)))`

**Governance for agent instructions.**

Tool descriptions and skill files are injected into a model's context on every
request. They decide which tool gets called, with what arguments, whether the
client asks before something is destroyed, and whether a skill fires at all.
They are production configuration — and almost nobody reviews them, versions
them, or notices when they change.

`sounding` audits them, scores them with a formula you can check, writes the
corrections, and pins them so you find out when they drift.

Three artifact types:

| | |
|---|---|
| **MCP servers** | permission, blast radius, injection surface, transport, secrets |
| **Agent Skills** | triggering, progressive disclosure, dangerous commands, portability |
| **Prompts** | output contract, failure behaviour, interpolation safety, contradictions |

They are the same problem. A skill and a tool description are both text handed
to a model, living in a repo, versioned, drifting — so they share one engine and
one report.

```
·)))  filekit

  HIGH   MCP003  tool:delete_file
         Description instructs the model rather than describing the tool
         (matched: 'Ignore previous'). This text enters the context window verbatim.
         ref  MCP security guidance — scan before installing, pin tool descriptions
         fix  Describe behaviour only. A tool description is API documentation,
              not a prompt.

  score  0/100   100 - [7xhigh(15) + 6xmedium(7)] = 0
  found  7 high · 6 medium · 0 low
```

## What makes this different

**Every finding carries a reference.** Not "this looks risky" — the spec section
or guidance that says why. A finding without a source is an opinion, and this
tool does not ship opinions.

**Every finding carries a fix, or a question.** When the correction is
unambiguous, it says what to change. When it depends on intent the tool cannot
infer, it asks — with options, capped at three per run:

```
  Three questions would let me write the fixes:
    1. `run` looks like it runs commands. How is the command constrained?
       allowlist of fixed commands / sandboxed / arbitrary — no constraint / not sure / skip
```

**And then it writes them.** Answers become edits to your descriptor, shown as a
diff before anything is touched:

```diff
- "url": "http://files.example.com/mcp",
+ "url": "https://files.example.com/mcp",
- "FILEKIT_API_KEY": "sk-live-9d2f8a1c4b7e0392"
+ "FILEKIT_API_KEY": "${FILEKIT_API_KEY}"
-   "readOnlyHint": true
+   "readOnlyHint": false
```

Anything generated that still needs a human is marked `TODO` in the output. The
tool does not write prose and present it as finished — and in a SKILL.md it
rewrites the frontmatter only. Body text is yours.

**The score shows its formula.** `100 - [7xhigh(15) + 6xmedium(7)] = 0`. A number
you cannot audit is a vibe.

**No model is involved.** Every rule is deterministic. Same input, same output,
every time — which is what a linter has to be.

## Install

```bash
pip install sounding
```

From a clone — which is also the only way to run it before the first release
lands on PyPI:

```bash
git clone https://github.com/alinotfoundbtw/sounding
cd sounding
pip install -e .
```

Python 3.10 or newer. No dependencies.

## Use

```bash
sounding audit server.json              # MCP: a descriptor or client config
sounding audit ./my-skill               # Skill: a directory or SKILL.md
sounding audit ./prompt.txt             # Prompt: a .txt or .md without frontmatter
sounding audit server.json --format md  # a report you can hand to someone
sounding audit server.json --interactive # answer the open questions
sounding fix server.json                 # dry run — show the diff
sounding fix server.json --write         # apply it (writes a .bak)
sounding fix server.json --answers a.json --write
sounding pin server.json                 # write sounding.lock.json
sounding diff server.json                # detect drift since the pin
sounding audit .                         # scan a whole project
sounding audit . --format sarif          # GitHub code scanning
sounding audit . --write-baseline        # adopt on an existing repo
sounding eval ./skills                   # do these skills trigger on the right tasks?
sounding rules                           # every rule set and the scoring formula
sounding serve                           # run as an MCP server (see MCP-SETUP.md)
sounding selfaudit                       # audit this tool's own MCP manifest
```

Accepts three input shapes, because these are what people actually have:

- a `tools/list` response — `{"tools": [...]}`
- a full server descriptor — `{"name":..., "transport":..., "tools":[...]}`
- a client config — `{"mcpServers": {...}}`

### Scanning a project

```
$ sounding audit .
·))) 11 artifact(s)

  ARTIFACT                            KIND    SCORE   FINDINGS
  examples/messy-server.json          mcp         0   7h 6m 0l
  examples/prompts/messy.txt          prompt      0   8h 4m 1l
  examples/skills/messy-skill         skill       0   6h 3m 2l
  examples/prompts/image-thin.txt     prompt     49   2h 3m 0l
  examples/clean-server.json          mcp       100   clean
  examples/notes-server-v2.json       mcp       100   clean
  examples/prompts/clean.txt          prompt    100   clean
  examples/prompts/image-good.txt     prompt    100   clean
  examples/skills/block-scalar-skill  skill     100   clean
  examples/skills/clean-skill         skill     100   clean
  examples/skills/defensive-skill     skill     100   clean

  mean score 68/100
  config: .sounding.json
```

Skills and MCP descriptors are found by shape, not filename — a `SKILL.md`, or
JSON carrying an `mcpServers` object or a `tools` array. Prompts are opt-in via
`promptGlobs`, because every repo is full of `.txt` files that are not prompts
and guessing would bury the real findings.

### In CI

```yaml
- run: pip install sounding
- run: sounding audit . --fail-on high
```

Or into GitHub's Security tab:

```yaml
- run: sounding audit . --format sarif > sounding.sarif
  continue-on-error: true
- uses: github/codeql-action/upload-sarif@v3
  with: { sarif_file: sounding.sarif }
```

Adopting on an existing project without four hundred findings on day one:

```bash
sounding audit . --write-baseline   # record what is already there
sounding audit . --baseline         # from now on, only what is new
```

Baselined artifacts show as `13 baselined`, never as `clean`. They are a
backlog, not a pass, and the output refuses to pretend otherwise.

Full options in [CONFIG.md](https://github.com/alinotfoundbtw/sounding/blob/main/CONFIG.md).

Exit codes: `0` clean · `1` medium findings, or a command that declined to run ·
`2` high findings, or drift in a tool contract. A refusal never borrows `2`, so
a failed `diff` in CI always means the contract actually changed.

## Drift

A server earns trust, then quietly changes what its tools claim to do. The
description is what the model reads, so changing it changes behaviour even when
the code is untouched.

`examples/notes-server-v2.json` is the same server one release later, with
`notes_search` now claiming to return note bodies too:

```
$ sounding pin examples/clean-server.json
·))) pinned 1 server(s), 2 tool(s) -> sounding.lock.json

$ sounding diff examples/notes-server-v2.json
·))) drift detected:

  ~ notes: version 1.2.0 -> 1.3.0
  ! notes.notes_search contract changed (8c54f6b4d84b91a7 -> 5d08119d9a3adf5a)
```

Commit the lockfile. Review the diff like you would any other change to
production config.

## Fixing

```bash
$ sounding fix examples/messy-server.json --interactive
  What values are valid for `path`?
    1) a fixed set (enum)
    2) matches a pattern
    3) any value within a sandboxed root
    4) genuinely unconstrained
  > 3
```

Answers can also come from a file — `examples/answers.json` answers four of the
five questions and leaves one open on purpose:

```
$ sounding fix examples/messy-server.json --answers examples/answers.json
[...]
·))) 8 change(s):
  tools[ping].description = 'Call an external service to ping. TODO: name the service, the data sent to it, and the failure behaviour.'  (TODO: finish this)
      description scaffold TODO
  tools[delete_file].annotations.readOnlyHint = False
      annotation contradicted the description
  env.FILEKIT_API_KEY = '${FILEKIT_API_KEY}'
      literal credential replaced with a reference — rotate the old value
  url = 'https://files.example.com/mcp'
      transport upgraded to https
  tools[delete_file].inputSchema.properties.path.pattern = '^(?!/)(?!.*\\.\\.).+$'
      relative paths only, no traversal
  tools[read_file].inputSchema.properties.path.pattern = '^(?!/)(?!.*\\.\\.).+$'
      relative paths only, no traversal
  tools[run].inputSchema.properties.cmd.enum = ['TODO_VALUE_1', 'TODO_VALUE_2']  (TODO: finish this)
      replace with the real allowed values TODO
  version = '0.1.0'  (TODO: finish this)
      starting version so consumers can pin TODO

  3 of these are scaffolds marked TODO. They are placeholders, not finished work — edit them before shipping.

  Still unresolved:
    shell:run: `run` looks like it runs commands. How is the command constrained?

  Dry run. Re-run with --write to apply.
```

Three rules hold here:

- **Dry run by default.** `--write` is explicit, and it leaves a `.bak`.
- **"not sure" and "skip" change nothing.** An unanswered question is reported,
  never guessed.
- **Scaffolds are labelled.** A generated description says `TODO` inside the
  text itself, so it cannot ship unnoticed.

## Rules

`sounding rules` lists them with the scoring weights.

**MCP (12)** — description quality, permission and blast radius, transport,
secrets, drift.

**Skills (13)** — frontmatter validity, name alignment, trigger quality,
progressive disclosure, broken reference files, host-override language,
dangerous commands, embedded secrets, machine-specific paths.

**Prompts (11 generic + profiles)** — missing output format, undefined failure
behaviour, undelimited interpolation, contradictions, vague quantifiers,
negation-heavy phrasing, repetition, embedded secrets, bloat.

Generic rules are true of every prompt, which is why they are shallow. **Profiles**
add the dimensions that actually decide quality for one kind of prompt: an image
prompt is checked for subject, medium, lighting, composition, colour and mood; an
extraction prompt for its schema and absent-value rule; an agent prompt for its
tool boundary, stopping condition, and untrusted-content handling. See
[PROFILES.md](https://github.com/alinotfoundbtw/sounding/blob/main/PROFILES.md).

Prompt rules are deterministic only. Whether a prompt *works* can be found only
by running it, and this tool runs nothing — so it checks the structural class of
problem instead, which is where most prompt failures actually live.

The adapter is chosen from the path; `--type` overrides it.

Severity weights: high 15 · medium 7 · low 3. Score is `100 - sum(weights)`,
floored at zero.

## Eval — the part determinism cannot answer

Static rules cannot tell you whether a skill *fires* on the tasks it is meant to
handle. That is a retrieval question, and retrieval is measurable without a model.

```
$ sounding eval examples/skills --cases examples/cases.json

·)))  eval — 4 skill(s) under examples/skills

  Measures trigger selection only: whether the right skill would be
  chosen, not whether its instructions work. Lexical proxy, not a model.

  routing   5/6 decisive and correct   (83%)

  WRONG   'book me a flight to Berlin'
          expected None, chose block-scalar-skill

  No description collisions.
```

The one failure is the interesting kind: a task no skill should handle gets
claimed by one anyway.

Collision analysis needs no cases at all — point it at a skills directory and it
reports which descriptions will fight over the same tasks. That is the most
common reason skills misfire once more than a handful are installed.

**What it measures:** trigger selection. **What it does not:** whether the
instructions work once the skill fires — that needs a model, and this tool runs
nothing. The scorer is BM25 lexical retrieval, which will disagree with a real
model at the margins. It is a smoke test, not an oracle, and every report says so.

`--scaffold cases.json` writes a starting case file. Every task in it is a TODO
on purpose: a case derived from a description only proves the description
matches itself.

## Playground

[playground/](https://github.com/alinotfoundbtw/sounding/tree/main/playground) is a single page that runs these rules in the browser
via Pyodide — the same wheel the CLI installs, so the web version cannot
silently disagree with CI.

**Nothing is uploaded.** MCP configs carry API keys; a security tool that shipped
them somewhere would be a contradiction.

## It audits itself

`sounding selfaudit` runs the MCP rule set against this server's own tool
manifest. The test suite asserts it scores 100, so the manifest cannot drift out
of compliance without CI failing.

Two rules in this repo were corrected *because* the self-audit caught them
firing wrongly — a description mentioning "system prompt" as its subject was
being read as an injection attempt. A linter that only ever runs on other
people's work never finds those.

## Scope, stated plainly

This is **static analysis of a declared tool contract**. Nothing is executed,
connected to, or scanned. It tells you what a server *claims* about itself.

A server that passes cleanly can still be malicious at runtime — the contract
and the implementation are different things, and no static tool can bridge that.
What this catches is the large class of problems that are visible in the
declaration and that nobody is currently looking at.

## Roadmap

- **v0.1** — MCP servers: audit, score, pin, diff
- **v0.2** — corrections written back to source from answered questions
- **v0.3** — Agent Skills (`SKILL.md`): same engine, second adapter
- **v0.4** — prompts: deterministic rules only
- **v0.5** — ships as an MCP server, so an agent can audit in-session
- **v0.6** — project scan, config, baseline, SARIF
- **v0.7** — eval layer, browser playground, hardened input handling
- **v0.8** — prompt profiles: domain dimensions, not just generic structure
- **v0.9** — validated against third-party work; hardened; one shared engine
- **v0.9.2** — docs enforced, not remembered: pasted output and the embedded
  wheel are both re-checked in CI
- **v0.9.3** — identical output on every platform
- **v0.9.4** — the test suite made portable too ← you are here
- **next** — `pin`/`diff` for skills and prompts; an eval layer beyond lexical

One engine, three adapters. Existing prompt tooling manages prompts *inside an
application*; nothing covers the agent-configuration layer, which is where
skills and tool contracts live.

## Contributing

Rules must be deterministic and carry a reference. A rule that fires on
well-written servers is a bug — false positives are how a linter loses its
audience, so `tests/` guards the clean fixture as hard as the messy one.

## Validated against work I did not write

Every rule and fixture in this repo was written by the same person, so of course
they agreed. The real test was running it against **35 professionally-written
skills by other authors**.

The first run was damning: **39 findings, a false-positive rate near 46%**, and
one skill scored 13/100. Four distinct defects:

| Defect | Scale | Cause |
|---|---|---|
| YAML block scalars unparsed | 11 of 35 | `description: \|` read as broken syntax, cascading into every other rule |
| Trigger detection too narrow | 16 of 35 | Required one blessed phrasing; real descriptions say "when building new UI" or list situations |
| Defensive prose read as attack | 1 of 35 | A skill quoting *"ignore previous instructions"* to warn about it was flagged for containing it |
| Length threshold below reality | 5 of 35 | 2,500 words; the corpus median is 916 and its p90 is 2,937 |

After: **7 findings, 28 of 35 clean, mean score 99.** The remainder are genuine
and all low severity.

The third defect is the one worth naming. A rule that fires on security guidance
*because it describes an attack* inverts its own purpose — the careful author
gets the finding and the careless one does not. No amount of self-review found
it; running the tool on someone else's careful work did.

Every one of the four is now a fixture in `examples/` and a test in
`tests/`, including a test asserting the trigger rule **still fires** on
genuinely vague descriptions — because tuning until nothing fires is the same
failure wearing a different mask.

## Robustness

Every rule is fuzzed against malformed input in the test suite: non-dict tools,
null names, integer descriptions, strings where objects belong, unterminated
regex bait, control characters, 20k-character fields.

Six crashes were real before those tests existed. A linter that dies on a
malformed file is useless precisely when it is most needed — malformed files are
the ones worth checking — so structural problems are reported as `MCP000`
findings rather than raised as exceptions.

MIT.

<sub>`·)))` alinotfound</sub>
