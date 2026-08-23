# LAUNCH

What to do to publish this, in order, and an honest account of what actually
produces visibility.

---

## Phase 1 — before anything is public

Nothing here is optional. Each one is a reason someone bounces.

- [ ] `python -m unittest discover -s tests` — all pass
- [ ] `sounding selfaudit` — 100/100
- [ ] `python tests/fuzz_manual.py` — 0 crashes
- [ ] **Clone into a temp directory and follow the README literally.** Whatever
      breaks is the highest-priority fix. This catches more than every other
      check combined, because it is the only one that tests the first minute.
- [ ] Open `playground/index.html` in a browser and click Sweep on all three
      samples. This has never been done by anyone.
- [ ] Real contact address in `site/.well-known/security.txt` — an invalid one
      is worse than none
- [ ] Confirm `sounding` is free on PyPI

---

## Phase 2 — the repository

```bash
gh repo create alinotfoundbtw/sounding --public --source=. --push \
  --description "Audit MCP servers, Agent Skills, and prompts. Findings carry a reference, a fix, and a score that shows its formula."

gh repo edit --add-topic mcp --add-topic model-context-protocol \
  --add-topic agent-skills --add-topic ai-agents --add-topic linter \
  --add-topic security --add-topic static-analysis
```

Then, in the web UI:

- [ ] Social preview image — 1280×640, `--abyss` ground, the mark, the name,
      one line. This is what renders on every shared link and most repos leave
      it blank.
- [ ] Pin the repo on the profile
- [ ] Upload the avatar to the account

---

## Phase 3 — package and registries

Order matters: the package README links to the repo, so the repo goes first.

- [ ] `python -m build && python -m twine upload dist/*`
- [ ] Verify `pip install sounding` works in a clean venv on another machine
- [ ] Submit to the MCP registry (`registry.modelcontextprotocol.io`)
- [ ] Submit to `mcp.so`, `smithery.ai`, `glama.ai/mcp`
- [ ] Open a PR adding it to `awesome-mcp-servers`

Registry listings are the highest-value distribution available here, because
they reach people **at the moment they are looking for exactly this**. That is
worth more than any amount of posting.

---

## Phase 4 — the write-up

This is the part that actually travels, and it is the part most people skip.

The post already exists as a fact and does not need inflating:

> I built a linter for agent instructions, then ran it against 35 skills written
> by other people. It reported a 46% false-positive rate and four distinct
> defects in my own rules — including one that flagged security guidance
> *because it quoted an attack string*. The careful author got the finding; the
> careless one did not.

That is a real story about a real mistake, and it teaches something. It is worth
more than a feature announcement, because a feature announcement asks for
attention and a lesson gives something in return.

Where it fits: a repo `WRITEUP.md`, a personal site post, and one link shared in
one place where the people who build agents already are. Not five places with
the same text.

**Do not:** buy or trade stars, ask friends to star, post identical text across
communities, or launch on a Monday for "engagement".

---

## Phase 5 — the first week

- [ ] Answer every issue within a day, even to say "not yet, here's why"
- [ ] Fix any install failure the same day — a broken install on day one is the
      one bug that ends a project
- [ ] Open issues for the known gaps yourself: `pin`/`diff` supports MCP only;
      the eval scorer is lexical, not a model; the playground rendering is
      unverified. A visible backlog reads as alive. Silence reads as abandoned.

---

## What is actually true about visibility

Most open-source projects get no attention, and the ones that do usually got it
for one of three reasons:

1. **They solved a specific person's specific problem** at the moment they had
   it. Narrow beats broad. "Lints MCP tool descriptions" reaches fewer people
   than "AI dev tools" and converts far more of them.
2. **They were findable at the point of need** — the right registry, the right
   topics, an accurate description.
3. **Someone wrote honestly about a hard problem** and the tool was attached.

Nothing on this list is a growth tactic, and there is no version of this where
posting harder substitutes for the tool being good. The realistic outcome of a
first release is a handful of installs and one or two issues from strangers.
That is not failure — that is the input to the next version.

The compounding goal is narrower than stars: **one inbound message from someone
who found the work on their own.** That is the thing that eventually replaces
bidding on freelance platforms, and it does not require anything here to go
viral.
