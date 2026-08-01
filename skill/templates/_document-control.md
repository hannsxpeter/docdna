# Document control partial

Normative. Appended as the last section of every document docdna generates.

Frontmatter is invisible once Markdown is rendered, so a reader on GitHub, in Confluence, or in a PDF
export sees none of the lifecycle metadata. This block surfaces the fields a reader has to act on. It is
generated from the frontmatter, never authored separately, and `docdna_check.py` reports a mismatch
between the two as a lint error.

```markdown
## Document control

| | |
| --- | --- |
| Status | draft |
| Owner | unassigned (candidate: @platform-team, from CODEOWNERS, unconfirmed) |
| Last reviewed | 2026-07-31 by docdna v1.0.0 |
| Review cadence | on change to the files listed below |
| Next review | when `src/config/settings.py` or `.env.example` changes |
| Derived from | `src/config/settings.py`, `.env.example` at commit 639dfe7 |
| Open questions | 2, listed inline as GAP markers |

This document was derived from the repository. It has not been reviewed by a person.
To adopt it, set `status: active` and name an `owner` in the frontmatter.
```

## Rendering rules

- **`Next review` is a sentence, not a bare date, when the cadence is `on-change` or `on-release`.** A
  date implies a calendar obligation that does not exist for those cadences, and a stale-looking date is
  the fastest way to teach a reader that the metadata is decorative.
- **`Owner` always shows the candidate in parentheses with `unconfirmed`.** Never present a candidate as
  an assignment.
- **`Open questions` shows a count and points inline.** Do not restate the GAP text here; a reader who
  wants it will find it in place, and duplicating it means two copies that drift.
- **The closing two lines are fixed text.** They tell a reader exactly what to do to take ownership,
  which is the single action this whole block exists to prompt.

## Why the adoption instruction is here and not in the banner

The banner at the top says what this document is. This block at the bottom says what to do about it. A
reader who has just finished the document is the reader most likely to act, and they are not going to
scroll back up. Put the ask where the attention already is.
