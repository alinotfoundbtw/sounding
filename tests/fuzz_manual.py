# Standalone fuzz harness. The permanent versions live in test_sounding.py
# (TestRuleRobustness). Run directly: python tests/fuzz_manual.py
"""Throw hostile input at every rule and see what breaks."""
import sys, json, random, string, itertools
sys.path.insert(0, "src")
from sounding.model import Server
from sounding.rules import mcp, skill as skill_rules, prompt as prompt_rules
from sounding.skillfile import Skill, _parse_frontmatter
from sounding.rules.prompt import Prompt

crashes = []

def try_(label, fn):
    try:
        fn()
    except Exception as e:
        crashes.append((label, type(e).__name__, str(e)[:120]))

WEIRD = [
    "", " ", "\n"*50, "\x00", "a"*50000, "🔥"*500, "\\", "((((", "[[[",
    "{{unclosed", "%s%s%s", "\r\n\r\n", "..\\..\\..", "<script>", "'\"`",
    "\u202e", "ＦＵＬＬＷＩＤＴＨ", " signal\u0000null", "-"*1000, "?"*300,
]

# --- MCP: weird tool shapes
for w in WEIRD:
    try_(f"mcp desc={w[:12]!r}", lambda w=w: mcp.run_all(
        Server(name=w, version=w, url=w, env={w: w},
               tools=[{"name": w, "description": w,
                       "inputSchema": {"type":"object","properties":{w:{"type":"string"}}}}])))

# --- MCP: structurally invalid tools
BAD_TOOLS = [
    [None], ["string"], [{}], [{"name": None}], [{"description": 5}],
    [{"name":"x","inputSchema":"notadict"}], [{"name":"x","inputSchema":{"properties":"nope"}}],
    [{"name":"x","annotations":"nope"}], [{"name":"x","inputSchema":{"properties":{"p":"nope"}}}],
    [{"name":"x","inputSchema":{"properties":{"path":None}}}],
]
for i, t in enumerate(BAD_TOOLS):
    try_(f"mcp bad tools #{i}", lambda t=t: mcp.run_all(Server(name="x", version="1.0.0", tools=t)))

# --- MCP: bad env / url types
for bad in [{"K": None}, {"K": 5}, {None: "v"}, {"K": {"nested": 1}}]:
    try_(f"mcp env {bad}", lambda b=bad: mcp.run_all(Server(name="x", env=b)))
for u in ["http://", "http:///", "://x", "http://[", "https://", "ftp://x"]:
    try_(f"mcp url {u}", lambda u=u: mcp.run_all(Server(name="x", url=u)))

# --- Skills
for w in WEIRD:
    try_(f"skill body={w[:12]!r}", lambda w=w: skill_rules.run_all(
        Skill(name=w, description=w, body=w, base_dir=None)))
for fm in ["", "---", "---\n---", "a"*10000, ":\n", "k:\n  \n", "[]: v", "k: [unclosed",
           "k:\n v1\n v2\nk: again", "\x00: \x00"]:
    try_(f"frontmatter {fm[:14]!r}", lambda fm=fm: _parse_frontmatter(fm))

# --- Prompts
for w in WEIRD:
    try_(f"prompt {w[:12]!r}", lambda w=w: prompt_rules.run_all(Prompt(name="x", text=w)))
# regex-hostile prompts
HOSTILE = [
    "always " + "a "*5000, "never "*3000, "{{"*2000, "do not "*2000,
    "Always be. Never be. " * 500, "(" * 5000, "a" * 100000,
]
for h in HOSTILE:
    try_(f"prompt hostile len={len(h)}", lambda h=h: prompt_rules.run_all(Prompt(name="x", text=h)))

print(f"inputs tried: many | crashes: {len(crashes)}")
for c in crashes[:25]:
    print("  ", c)
