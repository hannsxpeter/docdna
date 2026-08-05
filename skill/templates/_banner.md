# Reconstruction banner partial

Normative. Every document docdna generates carries this immediately under the frontmatter, before the
first heading. It is not decoration and it is not removable by the generator.

```markdown
> Backfilled by docdna v1.2.0 from repository evidence at commit 639dfe7 on 2026-07-31.
> Claims are cited to files and symbols. Unknowns are tracked as GAP markers, not filled in.
> This is derived, not authoritative. Schedule a human review before relying on it.
```

Substitute the real version, the real short commit sha, and the real date. If the working tree is dirty at
generation time, append ` (working tree dirty)` to the first line, because a citation resolved against
uncommitted code cannot be reproduced by anyone else.

## Per-section confidence

Where a section rests on inference rather than on a direct reading, label it. Put the label on its own
line immediately under the section heading.

```markdown
## Deployment topology

_Confidence: medium. Derived from `infra/main.tf` resource names; no deployment manifest is committed._
```

| Label | Means |
| --- | --- |
| `high` | Every claim in the section resolves to a cited symbol or a captured command output |
| `medium` | The shape is evidenced but at least one connecting claim is inferred, and the inference is stated |
| `low` | The section is mostly structure around GAP markers. Requires an entry in `open_questions`. |

Omit the label entirely on a `high` section. A confidence note on every heading is noise, and noise is how
a reader learns to skip the `low` ones.

## What the banner is for

A generated document that does not say it is generated will be read as though a person wrote it and
checked it. Six months later nobody remembers which is which, and the derived document has the same
authority as the reviewed one. That is the failure this banner exists to prevent, and it is why the banner
outranks the aesthetics of a clean opening.
