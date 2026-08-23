# Configuration

Optional. Put `.sounding.json` at your project root; the nearest one above the
audited path wins. A missing config means defaults. A malformed one means
defaults too — a broken config file should never stop an audit.

```json
{
  "disable": ["MCP012", "SKL009"],
  "severity": { "MCP002": "low", "PRM003": "off" },
  "exclude": ["vendor", "fixtures"],
  "promptGlobs": ["prompts/*.txt", "src/**/*.prompt"],
  "minScore": 70,
  "failOn": "high"
}
```

| Key | Effect |
|---|---|
| `disable` | Rule codes to skip. A bare prefix (`"MCP"`) disables that whole adapter. |
| `severity` | Re-grade a rule: `high`, `medium`, `low`, or `off`. |
| `exclude` | Extra directory names to skip, added to the built-in list. |
| `promptGlobs` | Which files count as prompts. **Required** — see below. |
| `minScore` | Fail if any artifact scores below this. |
| `failOn` | `any`, `high`, or `never`. |

## Why prompts need a glob

Skills and MCP descriptors are detected by shape: a `SKILL.md`, or JSON with an
`mcpServers` object or a `tools` array. Those are unambiguous.

A prompt is just text. Every repo is full of `.txt` and `.md` files that are
not prompts, and guessing would produce noise on the first run — which is how a
linter gets uninstalled. So prompts are opt-in, by path.

## Baseline

For adopting this on an existing project without drowning in findings:

```bash
sounding audit . --write-baseline
sounding audit . --baseline
```

The first records what is already there. The second reports only what is new.
Existing findings appear in the table as `13 baselined` rather than `clean` —
they are a backlog, not a pass, and the output says so.

Commit the baseline. Remove entries as you fix them.

## GitHub code scanning

```yaml
- run: pip install sounding
- run: sounding audit . --format sarif > sounding.sarif
  continue-on-error: true
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: sounding.sarif
```

Findings then appear in the Security tab and as annotations on the pull request
that introduced them. Fingerprints are stable across reworded rule messages, so
improving a rule's wording does not resurface every old finding as new.
