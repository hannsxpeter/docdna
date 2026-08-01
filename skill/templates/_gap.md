# GAP marker partial

Normative. A GAP marker is what docdna writes instead of a plausible sentence.

Two paired lines, always both. The HTML comment is for machines and renders invisibly on GitHub. The
blockquote is for humans and cannot be scrolled past. `docdna_check.py` asserts the pair and reports an
orphan of either half as a lint error.

```markdown
<!-- GAP id=DR-004 kind=human-input sev=blocker owner=unassigned doc=operate.dr-bcp
     asks="What is the recovery time objective for the checkout service?" -->
> **GAP DR-004** (blocker): no recovery time objective is stated in code, config, or CI.
> This is a decision, not a fact, and it must be made by a person.
```

## Fields

| Field | Values |
| --- | --- |
| `id` | `<DOC>-<NNN>`. Stable, and never reused even after the gap closes. |
| `kind` | `human-input`, `not-implemented`, `unverifiable`, `out-of-scope`, `stale-evidence` |
| `sev` | `blocker`, `major`, `minor` |
| `owner` | A handle, or `unassigned` |
| `doc` | The catalog id |
| `asks` | One quoted sentence, phrased so it can be pasted into Slack unedited |

## The `kind` enum is load-bearing

It is the difference between five very different situations that all look like a hole:

- **`human-input`**: only a person knows. Every number lands here.
- **`not-implemented`**: the code does not do the thing. This is a product finding, not a documentation
  finding, and saying so is more useful than documenting an absence.
- **`unverifiable`**: the claim cannot be checked from this repository. This is where an honest document
  says so rather than reaching.
- **`out-of-scope`**: requires a reason, and converts a hole into a decision.
- **`stale-evidence`**: there was a citation and it no longer resolves.

## When a GAP replaces the whole document

**If a document's cited claim blocks are fewer than its GAP markers, the document is not written.** It is
listed in the manifest as `status: not-started` with its blockers attached, and no file is created.

A section whose body is entirely GAP markers and boilerplate is not a section, it is a request for
information wearing a heading. An empty file that exists is worse than a missing document that is tracked,
because the empty one stops anyone from noticing.

## The rule that generates most GAPs

**No number is ever generated.** Not a recovery time objective, a recovery point objective, an SLA, an
availability target, a capacity figure, a retention period, a support-window end date, an error budget, or
a review cadence. Every one of these appears in real templates as a slot, and every one is a decision a
human owns. A number is cited to a file that states it, or it is a `human-input` GAP. There is no third
option.
