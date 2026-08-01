# Document lifecycle

How the catalog is partitioned, and what happens to a document after it is written. `catalog/SCHEMA.md` is
normative for the fields; `templates/_frontmatter.md` is normative for what docdna writes into them. This
file is why those shapes are what they are.

## 1. Durability is the primary axis

Three values, not two. The requested durable-versus-transient split is one value short, because compliance
evidence behaves like transient in one respect and like durable in another: it is never updated, and it
must be retained for a period somebody else sets.

| Value | Update contract | Backfill posture | Shipped |
| --- | --- | --- | --- |
| `durable` | Edited in place. `last_reviewed` and `covers_digest` bump. | Backfill these. This is the product. | 54 |
| `evidence` | **Never edited.** A new run produces a new dated file. | Backfill the index and the inputs. Never the evidence itself. | 6 |
| `transient` | Written once, dated, abandoned | Never generated. See `antipatterns.md`. | 1 |

**Collapsing `evidence` into `durable` is the failure this split prevents.** An SBOM, an operational
readiness review, a post-mortem, and a scan result are snapshots of a moment. Editing one in place destroys
the only property that makes it evidence, which is that it says what was true on a date. The six shipped
`evidence` entries are `assure.sbom`, `assure.acr-inputs`, `assure.scanning-index`, `operate.orr`,
`operate.postmortem`, and `retire.archive-manifest`. Set `valid_until` on all six and never rewrite one in
place.

**Collapsing `evidence` into `transient` is the other half.** A transient artifact can be thrown away. An
evidence artifact has a retention period that is a legal or contractual fact, not a preference, which is
why `retention` is a frontmatter field and never a guess.

## 2. Lifecycle stage is the organizing axis

Ten stages. A document belongs to the stage at which it first becomes load-bearing, not the stage in which
it is most often read. **Each stage answers exactly one question**, and a stage that needs two questions to
describe it is two stages.

| Stage | The one question | Shipped |
| --- | --- | --- |
| `frame` | Why does this exist, for whom, and what counts as success? | 4 |
| `decide` | What did we choose, and what did we reject? | 4 |
| `design` | What shape is it, and why that shape? | 5 |
| `build` | How do I work on it? | 15 |
| `verify` | How do we know it works? | 4 |
| `assure` | How do we prove to an outsider it is safe, lawful, and accessible? | 9 |
| `operate` | How do we run it and keep it alive? | 11 |
| `serve` | How does someone use it? | 2 |
| `govern` | How is the work itself managed? | 6 |
| `retire` | How does it end? | 1 |

**The list is an ordering of first authorship, not a waterfall.** A backfilled repository will have `build`
and `operate` documents years before anyone writes a `frame` document, and that is the normal case, not a
maturity failure. **The manifest must never scold the user for the shape of their history.** Report the
set, order by consequence, and leave the moralizing out.

The stage is also the unit of blast radius. Low archetype confidence blocks writes for a whole stage
(`assure`), because getting the archetype wrong changes which outside body you are writing for, and that
error is not recoverable by editing a sentence.

## 3. Audience is not the axis, and never was

The obvious partition is by reader: an executive set, an engineering set, an operations set, a compliance
set. Reject it.

**ISO/IEC/IEEE 42010:2022 settles this.** Audience is stakeholder plus concern. The document set is
partitioned by viewpoint, and cross-audience consistency is a **correspondence rule**, not a parallel tree.
The CTO's architecture view and the engineer's architecture view are the Building Block View at whitebox
level 1 and level 3: one artifact, two zoom levels.

Tiering by reader guarantees N parallel document sets covering the same system, and they drift inside one
quarter. Then the interesting question ("which of these is true?") has no answer, because each set was
written for a reader rather than from a system.

Every catalog entry still carries a populated `audiences` list, across eleven values from `engineering` to
`agents`, and **no audience renderer ships.** The data is there the day somebody asks for a projection.
Building a projection nobody has requested is exactly the theater this skill exists to prevent.

## 4. Status and the four staleness verdicts

`status` is one of `draft | active | deprecated | superseded | retired | not-applicable`. docdna writes
`draft` on everything it generates and never writes `active`; promotion is a human act, and it is the whole
content of the document control block at the foot of the file.

Staleness is four independent verdicts, computed separately and **never conflated into one red light**:

```
calendar-stale = review_cadence != none AND (today - last_reviewed) > review_cadence
drift-stale    = covers != [] AND recomputed_digest != covers_digest beyond drift_budget
expiry-stale   = valid_until != null AND today > valid_until
unverifiable   = covers == []
```

**`unverifiable` is the honest state for most `frame` and `govern` documents, and it is never a failure.**
A business case has no files to hash. Reporting one as drift-stale would be theater, and a reader who is
shown one piece of theater discounts the rest of the page.

Cadence is copied from the catalog entry, never invented. Fifteen shipped entries use `on-change`, seven
use `on-release`, and three use `none`; for those, `next_review` is a sentence, not a date, because a date
implies a calendar obligation that does not exist.

## 5. Supersession and retirement

**Immutable classes** are everything with `durability: evidence`, plus `decide.adr`. Never edit an accepted
file. Mint a new instance id, set `supersedes` on the new file and `superseded_by` plus `status:
superseded` on the old one. The old file stays where it is. **Numbers are never reused**, because a
citation to `adr-0014` written last year has to keep resolving to the same decision.

**Mutable classes** are everything else marked `durable`. Edit in place, bump `last_reviewed` and
`covers_digest`, leave the id alone.

**Retirement is `status: retired` plus `retired_on`.** Retired is not deleted. Deletion is a
records-management decision with a retention period attached to it, and it is not one a documentation tool
gets to make. A retired document that stays in the tree also answers the question a deleted one leaves
open, which is whether the thing was ever documented at all.

Supersession is also how a wrong reconstruction gets fixed. A generated ADR that turns out to have invented
its rationale cannot be corrected, only superseded, which is why `references/evidence.md` puts reconstructed
decisions in a separate `adr-draft-` id space and leaves Considered Options absent rather than filled.

## 6. Non-Markdown documents get a sidecar

Frontmatter needs a Markdown file to live in. Several catalog entries do not have one:

| Entry | Path | Shape |
| --- | --- | --- |
| `assure.sbom` | `sbom/` | Generated artifacts, machine format |
| `build.llms-txt` | `llms.txt` | A plain text index |
| `decide.adr` | `docs/adr/` | A directory of numbered instances |
| `decide.design-proposal` | `docs/decide/proposals/` | A directory of dated instances |
| `operate.postmortem` | `docs/operate/postmortems/` | A directory of dated instances |
| `operate.runbook` | `docs/runbooks/` | A directory of instances |

**Sidecar convention: `.docdna/meta/<id>.yml`.** A catalog entry whose `path` is not a Markdown file must
have one, and the lint enforces it rather than treating the missing frontmatter as an absent document.

**For a single-file entry** such as `llms.txt`, the sidecar carries the whole frontmatter block, `status`
included, exactly as it would appear inside a Markdown file.

**For a directory of instances**, the sidecar describes the class and never a member: `id`, `stage`,
`durability`, `scope`, `system_of_record`, `owner`, `review_cadence`, `covers`, `covers_digest`,
`satisfies`. Each instance still carries its own frontmatter. An ADR's `status` belongs to that ADR; the
ADR class's review cadence belongs to the sidecar.

Two rules follow, and both are lint errors when broken:

- **A sidecar never contradicts an instance.** A class sidecar carries no instance status at all, so
  `docs/adr/0014-use-postgres.md` saying `status: superseded` is the only record of that fact.
- **A sidecar is not a substitute for the artifact.** `.docdna/meta/assure.sbom.yml` existing while `sbom/`
  is empty is state `absent`, not `present`. Metadata about a document that does not exist is the purest
  form of paper theater available.
