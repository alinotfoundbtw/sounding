# Playground

One page. Paste a SKILL.md, an MCP config, or a prompt; get the report.

## Nothing leaves the browser

MCP configs contain API keys. A security tool that uploaded them would be a
contradiction, so this one does not upload anything: the rules run locally as
WebAssembly via Pyodide. No server, no logging, nothing to trust me about — the
page is 500 lines and the network tab shows two CDN requests and the wheel.

## Why Pyodide rather than rewriting the rules in JavaScript

JavaScript would load faster. It would also mean two implementations that drift
apart, and a web version quietly disagreeing with CI is worse than a slow one.
The wheel here is the same package the CLI installs, so the playground cannot
be wrong in a way the tests do not catch.

Cost: the engine downloads on first Sweep, not on page load. Nobody pays for it
unless they use it.

## One file

`index.html` is self-contained — the wheel is embedded in it as base64 and
written into Pyodide's virtual filesystem, so nothing is fetched except Pyodide
itself from the CDN.

That means it works by double-clicking it. An earlier version fetched the wheel
from a relative path, which fails under `file://` because the browser treats it
as a cross-origin request. Anyone who downloads a single HTML file expects it to
open.

## Deploying

Copy `index.html` anywhere. Cloudflare Pages, Netlify, GitHub Pages, or an email
attachment.

Rebuild after a version bump:

```bash
python -m build --wheel --outdir playground/
python - <<'EOF'
import base64, pathlib, re
whl = next(pathlib.Path("playground").glob("*.whl"))
b64 = base64.b64encode(whl.read_bytes()).decode()
p = pathlib.Path("playground/index.html")
p.write_text(re.sub(r'const WHEEL_B64 = "[^"]*"', f'const WHEEL_B64 = "{b64}"', p.read_text()))
EOF
```

## Browser testing status

Written and shipped from an environment with no browser. The Python it runs is
covered by the test suite and was executed against every sample and against
malformed input. The loading path was exercised once by a real user and failed —
a relative wheel fetch under `file://` — which is why the wheel is now embedded.

The rendering and question wiring still have not been exercised in a browser.
Open it once before publishing.
