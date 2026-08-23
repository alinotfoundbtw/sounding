---
name: False positive
about: A rule fired on something that is actually fine
labels: false-positive
---

**Rule that fired**

<!-- e.g. SKL005 -->

**The artifact**

<!-- The smallest snippet that reproduces it. Redact anything private —
     and if it is an MCP config, remove the credentials first. -->

**Why it is not a defect**

<!-- What the rule missed about this case. -->

---

False positives are the highest-priority bug class here. A linter that fires on
good work stops being read.
