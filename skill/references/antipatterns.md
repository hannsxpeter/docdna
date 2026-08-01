# Antipatterns

Named so they can be invoked in review by name. "This section is checkbox headings" ends an argument in one
sentence; "this feels a bit thin" starts one that nobody wins. The names are the point.

`references/evidence.md` is normative for the rules. This file is the field guide: what each failure looks
like in a diff, the test that catches it, and what to do instead.

## 1. Paper theater

**A sentence that is true of any project.**

The test is substitution: swap the project name for a competitor's and the stack for a different one. If
the sentence survives, it is not documentation.

| Survives substitution, therefore worthless | Does not survive, therefore documentation |
| --- | --- |
| "The system follows a layered architecture with separation of concerns." | "Requests enter through `cmd/api/main.go`, which mounts four route groups and no middleware other than request logging." |
| "Secrets are managed securely." | "`config.load()` reads six variables from the environment; `.env` is gitignored and `.env.example` lists five of the six." |
| "The project follows industry best practices for testing." | "`pytest.ini` sets `--cov-fail-under=0`; CI runs `pytest -q` with no coverage gate." |

**Why it happens:** a heading exists, the section must not be empty, and a general sentence is always
available. Paper theater is what a model writes when it has nothing and a slot to fill.

**Instead:** cite it or GAP it. A section with two cited sentences is a better document than the same
section with two cited sentences and four true-of-anything ones, because the filler teaches a reader to
skim, and a skimmed document is an unread document.

## 2. Checkbox headings

**A section whose body is entirely GAP markers and boilerplate.** It is a request for information wearing a
heading.

The test is a count, which is why it is enforceable: **if a document's cited claim blocks are fewer than
its GAP markers, the document is not written.** It is recorded in the manifest as `status: not-started`
with its blockers attached, and no file is created.

**Why it happens:** a template ships with twelve headings and the code supports four of them. The other
eight get GAP markers and the document goes out looking complete-ish.

**Instead:** ship the four. **An empty file that exists is worse than a missing document that is tracked**,
because the empty one stops anyone from noticing that the work was never done. A tracked absence generates
a task. A stub generates a false sense of coverage.

This is also why the catalog is large and the writing surface is small. Naming a document and ruling on it
costs one JSON row. Shipping a template invites the model to fill it, so `producible: M` and `producible:
R` entries ship no template and invariant I1 fails the build if one ever appears.

## 3. Regime cosplay

**A document whose form implies an obligation the project does not have.** A privacy impact assessment for
a project with no personal data. An operational readiness review for a library with no runtime service. A
control mapping for a repository nobody outside the team can reach.

The test is one question: **which signal selected this, and what file is that signal standing on?** Every
document in the manifest names its triggering signal with a path. A document that cannot name one is not
required.

**Why it happens:** compliance documents are the ones people ask for by name, and their shape is easy to
imitate. Structural fidelity is precisely what makes a fake submittable, which is why a refused entry is
never emitted with its real section structure even as a draft.

**Instead:** report the signal and name the regime that signal might trigger, then say to confirm with
counsel. Emit the evidence annex under `docs/assure/inputs/` and a named list of who must sign, with the
signature line empty.

**The mirror image is just as bad.** An exclusion with no reason is regime cosplay run backwards: it makes
a gap look like a decision. `not-applicable` requires `because`, `cite`, and `revisit_when`, and invariant
I7 enforces all three. See `selection.md` section 7.

## 4. Confident fiction

**The killer, and the one specific to this skill: a generated number.**

Not a recovery time objective, a recovery point objective, an SLA, an availability target, a capacity
figure, a retention period, a support-window end date, an error budget, or a review cadence. Every one of
these appears in a real template as a slot, and every one is a decision a person owns.

**No number is ever generated.** Numbers are cited to a file that states them, or they are `human-input`
GAPs. There is no third option and the rule is absolute.

Confident fiction is worse than the other three because it is actionable. Paper theater wastes a reader's
time. A fabricated RTO of four hours gets copied into a contract, and the first real outage discovers that
nobody ever built for it.

Three shapes it takes, all of which pass a casual read:

- **The plausible default.** "Backups are retained for 30 days." Nothing in the repo says 30.
- **The inherited number.** A figure lifted from a similar project, or from a template's own example.
- **The hedge.** "The system targets approximately 99.9% availability." A hedge still reads as
  documentation, which is why FAIL means delete the claim rather than soften it.

**Instead:** the GAP, phrased so it can be pasted into Slack unedited. "What is the recovery time objective
for the checkout service?" is a better artifact than any number docdna could invent, because it routes to
the one person who can answer it.

## 5. Transient artifacts

**A transient artifact is written once, dated, and abandoned.** Reconstructing one is fabricating a record
of a meeting that happened, which is the only failure mode here worse than fabricating a number.

Named so the omission is a stated decision rather than an oversight. Each row carries the durable artifact
that absorbs whatever lasting content the transient one had.

| Transient artifact | Absorbed by |
| --- | --- |
| Sprint backlog, sprint goal | `frame.requirements`. The requirement survives; the sprint does not. |
| Standup notes, status reports | `govern.raid`, and `decide.adr` when something was actually decided |
| Meeting minutes, decision emails | `decide.adr` |
| Burndown and velocity charts | Nothing. Their only durable content is a scope or capacity decision, which belongs in `govern.raid`. |
| Design proposals and technical design docs | `decide.adr`, linked from More Information |
| Spike reports | `decide.adr` |
| Wireframes and comps | `design.diagrams` where the layout is load-bearing. Otherwise nothing; no design-system or UI-spec entry ships at this version. |
| Hypercare daily logs | `operate.postmortem`, `operate.runbook` |
| Marketing copy variants | `serve.changelog` |

**When the user asks for one of these: name it, state why it is not reconstructable, and offer the durable
artifact.** Do not quietly generate a plausible-looking fake. "I cannot reconstruct last quarter's sprint
goals, and nothing in the repo records them. What I can write is the requirements set they were drawn from"
is a better answer than nine invented sprint goals, and it takes one sentence.

`decide.design-proposal` is the single `transient` entry in the catalog, and it is `producible: M`. It
exists so that proposals a team already writes can be found, tracked, and pointed at from an ADR. docdna
never writes one. It also never emits a folder named `rfc/`: in any ITSM-adjacent shop "RFC" reads as
Request for Change, and a directory that means one thing to engineering and another to change management is
a bug with a filename.

## Using these in review

Four questions, in this order, against any document docdna produced:

1. **Substitution.** Would this sentence be true of a competitor's project on a different stack?
2. **Count.** Are there more GAP markers than cited claim blocks?
3. **Signal.** Which signal selected this document, and what file is it standing on?
4. **Numbers.** Is every number in this document cited to a file that states it?

A document that answers all four cleanly is derived. One that does not is a draft of something, and the
honest move is to say which of the four it failed.
