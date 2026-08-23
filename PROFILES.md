# Prompt profiles

The generic prompt rules apply to every prompt, which is exactly why they are
shallow. Output format, failure behaviour, contradictions — true of everything,
deep about nothing.

An image prompt lives or dies on lighting and composition. An extraction prompt
lives or dies on the schema and the absent-value rule. An agent prompt lives or
dies on its stopping condition. Nothing general can check any of those.

A **profile** is a checklist of dimensions for one kind of prompt.

## Built in

| Profile | Required dimensions |
|---|---|
| `image` | subject, medium/style, lighting, composition, colour, mood |
| `extraction` | field schema, absent-value handling |
| `agent` | tool boundary, stopping condition, failure escalation, untrusted content |

Optional dimensions exist too — camera/lens, aspect ratio, exclusions — and
never raise a finding on their own. Over-specification is a failure mode as
well.

```
$ sounding audit lighthouse.txt

  HIGH   PRF:image:lighting  lighting
         Lighting is not addressed. Lighting carries mood more than any other
         single choice, and it is the dimension most often left silent.

  score  49/100
  profile   text-to-image prompt — 1/6 dimensions addressed
```

Answering a question appends a real clause:

```diff
+ low golden-hour sun, long shadows, warm rim light along the edges, hazy air
+ extreme close-up, subject fills the frame, shallow depth of field
+ TODO_SUBJECT: describe who — age, build, clothing, expression, and what they are doing
```

## What a profile can and cannot do

**It can tell you a dimension is unaddressed.** That is the common failure, and
it is what an experienced person notices first reading someone else's prompt.

**It cannot tell you whether what you wrote is any good.** `lighting: nice light`
passes the lighting check. The checklist finds silence, not weakness.

**It is deliberately quiet.** Detection requires clear signals and a tie counts
as no match, because guessing wrong buries the author in findings about
dimensions they never meant to address. Refinement dimensions are optional so a
classifier does not get lectured about verbatim copying.

## Suppression

A profile can switch off generic rules that make no sense for its kind. The
image profile suppresses output format, failure behaviour, and length bound —
an image prompt has no output contract — and the negation-heavy rule, because a
list of exclusions is correct practice there rather than a smell.

## Control

```bash
sounding audit p.txt                    # auto-detect
sounding audit p.txt --profile image    # force one
sounding audit p.txt --profile none     # generic rules only
```

## Adding one

Profiles are data. A new one is a `Profile` in `rules/profiles.py` with
detection patterns and a list of `Dimension`s, each carrying vocabulary that
indicates the dimension was addressed, a reason it matters, and options whose
clauses get appended.

Two rules for a good dimension:

1. **It must have a reason.** A dimension without a `why` is an opinion, and the
   test suite fails on one.
2. **Its vocabulary must be generous.** Text wraps mid-phrase and hyphenation
   varies — `warm rim\nlight` and `golden-hour` are the same words as `rim
   light` and `golden hour`. Telling a careful author their careful work is
   missing is worse than saying nothing.
