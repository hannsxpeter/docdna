# Frontmatter partial

Normative. Every document docdna writes opens with this block. Every field below is either derivable from
the repository or is left at its stated default. **No field is ever guessed.**

There is no standard for document lifecycle metadata, so this does not invent one. It generalizes the two
ratified precedents that put document status in YAML frontmatter: MADR 4.0.0 (`status`, `date`,
`decision-makers`, `consulted`, `informed`) and ODCS 3.1.0 (`status: proposed|draft|active|deprecated|
retired`, a Linux Foundation standard). Two independent bodies converging is enough precedent to follow
rather than replace.

```yaml
---
id: build.config-reference
instance_id: null
title: Configuration reference
stage: build
durability: durable
scope: repo
system_of_record: repo
classification: unclassified

status: draft
owner: unassigned
owner_candidate: "@platform-team (from CODEOWNERS, unconfirmed)"
reviewed_by: null
last_reviewed: 2026-07-31
review_cadence: on-change
next_review: null
retention: indefinite
valid_until: null
supersedes: []
superseded_by: null
not_applicable_reason: null

covers:
  - src/config/settings.py
  - .env.example
covers_digest: sha256:9f2a1c...
drift_budget: 3
last_validated_commit: 639dfe7
applies_to: null

satisfies: [diataxis:reference]
audiences: [engineering]
traces_up: []
traces_down: ["module:src/config/settings.py"]

derivation: derived
confidence: high
generated_by: docdna v1.0.1
generated_on: 2026-07-31
content_hash: sha256:a1b2c3...
open_questions: []
---
```

## Field rules

| Field | Rule |
| --- | --- |
| `id` | The catalog id. Must exist in `catalog/documents.json`. |
| `instance_id` | Only for numbered classes: `adr-0014`, `inc-20260714-01`. Null otherwise. |
| `status` | `draft` on everything docdna writes. A human promotes to `active`. Never write `active`. |
| `owner` | Always `unassigned`. See below. |
| `owner_candidate` | A candidate, never an assignment. From CODEOWNERS, or from the top committer when CODEOWNERS is silent. Always suffixed `(unconfirmed)`. Never restated as an owner in a document body. |
| `last_reviewed` | The generation date. This is honest: docdna did look at it today. |
| `review_cadence` | Copied from the catalog entry. Never invented. |
| `next_review` | `last_reviewed` plus `review_cadence`, or null when the cadence is `none`, `on-change`, or `on-release`. |
| `covers` | **Files, never directories, never globs.** The lint rejects a directory with a hard error. |
| `covers_digest` | sha256 over the extracted declaration names from those files, not over a commit sha. |
| `drift_budget` | 1 for `assure` and `design`, 3 elsewhere. |
| `derivation` | `derived` when written from code evidence, `stub` when the document was created with fewer cited claims than GAP markers, `human-authored` when docdna only adopted it. |
| `confidence` | `high`, `medium`, or `low`, per section. Low requires a stated reason in `open_questions`. |

## Two rules that are not negotiable

**`covers` names interface-defining files.** A schema, a route table, a config struct, `openapi.yaml`, a
public export surface. Naming a directory makes the drift test saturate: at twenty commits a week a
directory-scoped `covers` is stale within a week with near-certainty, every document goes permanently red,
and the gate gets disabled in week two. Drift is computed over declaration names precisely so a reformat,
an added import, or a comment change does not fire it.

**`owner` is always `unassigned`, and the lint never fails on it.** Writing `owner: @platform-team` into a
disaster recovery plan that team never agreed to own, and then failing CI until somebody is named, is a
social failure mode. Social failure modes get a tool banned from a team faster than technical ones do.
Report it as an open question addressed to a human, which is what it is.

**`owner_candidate` may come from commit history, and it is a candidate for exactly that reason.**
`docdna_select.py` prefers CODEOWNERS and falls back to the top committer, rendered as
`"A. Patel (top committer, unconfirmed)"`. A frequent committer is not an accountable owner, and the whole
distance between those two things is carried by one word, so the `(unconfirmed)` suffix is not optional
and the field name is not interchangeable with `owner`. A document body never restates the candidate as
the owner; `build-codebase-map.md` forbids exactly that. Deriving the candidate is honest, because a
reader who needs to ask someone has to start somewhere. Publishing it as an assignment is not.

## Non-Markdown documents

Roughly a dozen catalog entries point at `openapi.yaml`, `CODEOWNERS`, `.well-known/security.txt`, or
`NOTICE`, where frontmatter has nowhere to go. Those use a sidecar at `.docdna/meta/<id>.yml` carrying the
same fields. A catalog entry whose path is not Markdown must have a sidecar, and `docdna_check.py`
enforces it.
