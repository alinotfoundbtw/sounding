# Running sounding as an MCP server

`sounding` audits MCP servers. It is also one — so an agent can review a skill
or a tool contract mid-conversation instead of you switching to a terminal.

## Claude Desktop / Claude Code

Add to your MCP config:

```json
{
  "mcpServers": {
    "sounding": {
      "command": "sounding",
      "args": ["serve"]
    }
  }
}
```

If the `sounding` command isn't on your PATH (common on Windows), use:

```json
{
  "mcpServers": {
    "sounding": {
      "command": "python",
      "args": ["-m", "sounding.cli", "serve"]
    }
  }
}
```

Restart the client. Then ask it things like:

- *"Audit the skill in ./my-skill and tell me what's wrong with it."*
- *"Check .mcp.json — anything dangerous in there?"*
- *"What does sounding check for in prompts?"*

## The tools

| Tool | What it does |
|---|---|
| `sounding_audit` | Findings, score, and the open questions, for any of the three kinds |
| `sounding_answer` | Applies chosen answers and returns a diff — **never writes to disk** |
| `sounding_rules` | The rule set and scoring weights for one kind |

All three are marked `readOnlyHint: true`. Nothing this server exposes can
modify a file, so no client will ever need to prompt you before a call.

## Verify before you trust it

The rules this tool enforces are ones it has to satisfy first:

```
sounding selfaudit
```

That runs the MCP rule set against this server's own manifest. It exits
non-zero below 100/100, and the test suite asserts the same thing — so the
manifest cannot drift out of compliance without CI failing.

Two of the rules in this repo exist *because* the self-audit caught them being
wrong. A tool that only ever runs on other people's work never finds those.
