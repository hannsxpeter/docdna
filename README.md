# docdna

[![CI](https://github.com/hannsxpeter/docdna/actions/workflows/ci.yml/badge.svg)](https://github.com/hannsxpeter/docdna/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](#install)
[![Agent skill](https://img.shields.io/badge/agent%20skill-SKILL.md-8A2BE2)](skill/SKILL.md)

**Derived from the code. Nothing asserted that the repo cannot prove.**

Point docdna at a repository. It reads the code, decides which documents that project owes, names which
ones it does not owe and on what evidence, sets a tripwire on every one of those exclusions, and writes
the documents the code can prove.

It is a portable coding-agent skill. No service, no account, no build step, stdlib Python only.

**docdna stands alone.** It needs nothing but Python 3.8, and no relationship to any other tool is
required or assumed. If you also use [codedna](https://github.com/hannsxpeter/codedna), which fingerprints
how a repo writes code, the two run side by side: separate repositories, separate installs, no shared
code, and their agent-instruction blocks sit in one `AGENTS.md` without touching each other. If you do
not, nothing on this page changes.

## The problem

The documents that would actually survive a handover, an audit, or somebody leaving were never written,
because nobody could say which ones this particular project owes. Generating eighty documents is easy and
worthless. Deciding this repo needs eleven of them, naming which eleven and why, saying out loud which
forty-nine were excluded and on what evidence, and arranging for those exclusions to report themselves
when they stop being true, is a different job.

Linters, doc generators, and link checkers all operate on what already exists. They will tell you that a
document is malformed, or that a link in it is broken. None of them decides what should exist, and none of
them defends an absence. That gap is what docdna is for.

## The selection engine

This is the part to look at first.

Selection runs off signals detected in the repository, an archetype (eight primaries, five overlays), and
an eight-question interview **of which none is asked on the first run**. Every answer is defaulted from
signals, labelled `assumed`, and printed with its blast radius, so you correct in one sentence instead of
answering a form. Every selected document names what selected it. A document selected by a signal cites
that signal and the file that carries it. A document selected by the catalog baseline, by an interview
answer, or by a signal's absence names which of those instead, and has no file path to give, because none
of the three is a place in the code: 13 of the 48 rows on this repository's own manifest are in that
group, `govern.manifest` and `verify.dod` among them. Every exclusion carries a reason, a citation, and a
`revisit_when` tripwire, so a document correctly skipped last quarter reports itself the moment the signal
that justified skipping it stops being true.

**Be clear about what "decides" means here.** The registry holds 132 signals. Across the 51 repositories
measured below, the count coming back present ranged from 4 to 46, with a median of 19; how many come back
`unknown` has never been measured across a corpus, and no median for it is published here. So the honest
description is not that docdna decides your documentation set. It decides what the code can settle, and it
shows you what it assumed about the rest. Every unknown is printed, by family. A family the scanner
refused to guess at names the question to ask. A family whose gate never fired sometimes names a question
that would resolve it and sometimes names none, because a pass that never ran can leave nothing to ask
about. This is that section of `docdna_scan.py` run against this repository, whole, regenerated and
compared byte for byte by `tests/test_readme_samples.py`:

<!-- docdna:sample cmd="python3 skill/scripts/docdna_scan.py TARGET" target="." section="not looked at, or refused" -->
```
not looked at, or refused
  a11y     : 2 signals unknown: gate did not fire
  ai       : 2 signals unknown: gate did not fire
  data     : 1 signals unknown: refuses to guess; ask q5_markets; resolved by q5_markets
  docs     : 1 signals unknown: refuses to guess; ask q8_doc_location; resolved by q8_doc_location
  jur      : 6 signals unknown: gate did not fire; resolved by q3_authorizer, q5_markets
  ops      : 4 signals unknown: refuses to guess; ask q6_downtime; resolved by q2_operator, q6_downtime
  sec      : 1 signals unknown: gate did not fire
  users    : 2 signals unknown: refuses to guess; ask q1_users; resolved by q1_users
```

That block is the product as much as the manifest is. **Absence of evidence is never encoded as false.** A
detector that did not run reports `unknown`, and `unknown` never silences a document. That is the
difference between "we decided this does not apply" and "we did not look", and it is the only reason the
manifest is worth showing an assessor.

## What a first run looks like

Zero questions.

The block below is not an illustration. It is stdout from `docdna_select.py`, pasted unedited, run against
`tests/fixtures/internal_service`, a small repository that ships in this repo so that you can reproduce it
in one line. Copy it out first, because a run writes a manifest into its target:

```sh
cp -R tests/fixtures/internal_service /tmp/svc && python3 skill/scripts/docdna_select.py /tmp/svc
```

The sample that stood here before was written by hand, and every visible thing about it was wrong. It
printed a `Drift` label and the word `confirmed`; the renderer's label is `Leads` and the word `confirmed`
appears nowhere in it. It said "none confirmed" directly above nine stale references. It put
`POSSIBLE STALE REFERENCES` second, where `render_report` puts it second to last. A hand-written sample in
the README of a tool whose whole thesis is derived-from-the-code is the sharpest own goal available, and
that is how it got there. A generated one cannot drift from the renderer without the renderer changing.

Two things to hold while reading it. It is a fixture, built small on purpose, so the counts are small; a
real repository produces the same sections with larger numbers, and a few conditional ones this profile
does not trigger. And the two rows at the bottom are leads, which is what the heading calls them, not
findings: this fixture was constructed so both are true drift, and on a repository nobody built for the
purpose most rows in that section are not.

<!-- docdna:sample cmd="python3 skill/scripts/docdna_select.py TARGET" target="tests/fixtures/internal_service" -->
```
docdna  solo-utility  ·  335 lines Python  ·  no license  ·  CI only

Documentation  0 of 20        Leads  2 possible stale references

MISSING AND LOAD-BEARING  (18, showing 3)
  design.api-contract   Selected by iface.http. [config/urls.py]
  design.data-model     This code owns a persistent schema and the meaning of its columns lives ...
  govern.manifest       The catalog selects this document for every repository.

NOT APPLICABLE  23 documents. No external body audits, certifies, or authorizes this before it
                ships, and no compliance workspace exists in the repository. Full ledger:
                .docdna/manifest.json
                assure.acr-inputs is one signal away: users.ui or arch.webapp

NOTE            I only see documentation committed to this repo. If your docs live in Confluence or
                Notion, say so and I will mark those rows present-elsewhere rather than missing.

ASSUMED         assumed q2_operator=not-deployed, q3_authorizer=none, q1_users=nobody.
                If a separate ops team runs this, up to 9 documents become required.

POSSIBLE STALE REFERENCES  (2)
  README.md             says `python manage.py runserver`; Procfile runs `gunicorn`; this document ...
  docs/api.md           says `11 endpoints`; 18 lines matched by the iface.http route pattern in ...
                A document may name a command without claiming this repository runs it: a comparison
                table, a task template, a case study about another repository. These are leads for a
                human to read, not findings. Full list: .docdna/manifest.json

NEXT            write 4 derivable documents  ·  refresh 1 drifted document  ·  --answer q2_operator
```

## What has been measured, and what has not

Two claims on this page were published before they were measured, and both were later falsified by
measurement. So here is the evidence position, stated in full, for the thing now carrying the headline.

**What exists.** Across 51 repositories the signal layer discriminated strongly and never errored. Present
signals per repository ranged from 4 to 46, with a median of 19. The inputs to selection genuinely vary by
repository rather than emitting a constant list, which is the necessary condition for selection to mean
anything.

**What does not exist.** Nobody has judged whether the selected set is correct for any repository. There
is no ground truth, no adjudicated sample, and no measurement of agreement with a human. Exclusion
reasons are unchecked: the mechanism that requires one is enforced, the reasons themselves have never been
read for soundness.

Tripwires need the same care, because the sentence that used to sit here was true in a way that misled.
A tripwire does fire correctly on a real repository: run `docdna_check.py` on this one and
`govern.ownership` fires, on `users.is_oss` and `q1_users` becoming true. Every firing observed so far,
here and in the tests, is a **first evaluation**: the predicate was already true the moment it was first
checked. What has never been observed is the temporal case the feature actually rests on, an exclusion
written when its predicate was false and a later run catching it after the repository changed. That is
the claim to hold open, and it is narrower and more useful than saying no tripwire has ever fired.

So selection ships qualitatively, with no percentage attached, and this paragraph stays in the README
until somebody adjudicates it. The alternative is a sixth round in which the next measurement overturns
this claim the way it overturned the last two.

## Drift: two passes, both leads

Drift needs no setup, no frontmatter, and no prior run, and it works on documents docdna has never
touched. Neither pass is a headline feature. Both produce leads, and the numbers are published here rather
than buried.

**Commands: 3.2 percent precision.** Across 51 repositories the command pass produced 31 findings and 1
was true drift. Of the 27 rows it then rated HIGH confidence, 0 were true, and that rating no longer
exists. Recall is stranger: across 77 documented commands in 5 maintained repositories, not one had a
missing script name. There was nothing to find. The base rate of the defect this pass hunts is
approximately zero, so its measured recall is too.

**Paths: 10.9 percent precision.** On an earlier five-repository holdout, all 46 path findings were
adjudicated by hand and 5 were real drift. The failures are not extraction bugs. Across those 46 the
extractor produced no token that was not a genuine path reference.

**One reason covers both.** A document names a command or a path for many reasons, and only one of them is
a claim about this repository right now. 28 of the 30 command false positives were documents making no
claim about the repository at all: comparison tables with metasyntactic placeholders, task templates, case
studies about external repositories, and one hypothetical drift example inside an instruction about
detecting drift. On the path side, 16 were install targets in a host capability matrix, naming where a
file goes rather than where it is, 10 were CHANGELOG entries describing the tree as it was, and the rest
were prospective paths in a fix recommendation, references into a sibling repository, hypothetical
examples, and reports of files deleted on purpose. Every one of those paths is correctly absent. No test
that asks whether a string is a file on disk can tell them apart.

Volume is lopsided in the same direction: across all 51 repositories, drift output was 93.6 percent path
rows and 6.4 percent command rows.

What the command pass does do is resolve through the manifest chain rather than the walk order. `npm run
dev` written in `services/api/` is checked against `services/api/package.json`, not against whichever
`package.json` the walk reached first, and when the command is declared in some other manifest in the tree
the row says where it lives rather than claiming the command does not exist. That fix is real and it
removed a class of silent false positives and false negatives. It did not make the question decidable.

**What the path pass does not look at.** A reference is dropped before anything is reported when neither
its parent directory nor its first path component exists in the repository. Either one is enough to keep
it, so a reference naming a file under a directory that does not exist inside `skill/` is still reported,
because `skill/` itself is there. When no part of the path is rooted here there is nothing left to
distinguish a stale document from a path that was never rooted here, so the check declines to guess. The
cost is that deleting an entire
`docs/` directory makes every reference into it invisible rather than glaring. The drop is at least
counted rather than silent: the scan reports how many candidates each recall gate discarded, under
`scan.drift.discarded`, so the reported findings can be read as the filtered view they are.

Every drift row is treated accordingly. Command rows and path rows alike carry `confidence: low` and a
note saying a document names commands and paths for many reasons, which makes them minor findings in
`docdna_check.py`, and drift of any kind gates CI only for the documents named in `assurance_set`.

## Three modes

| Mode | Does | Writes |
| --- | --- | --- |
| **Survey** (default) | Scan, decide the document set, report drift leads, write the manifest | `.docdna/manifest.json`, `DOCDNA.md` |
| **Backfill** | Generate selected documents from code evidence, with citations and GAP markers | `docs/**`, updates the manifest |
| **Check** | Drift, frontmatter lint, GAP rollup, stale exclusions. The CI gate. | The open-gaps block in `DOCDNA.md`, unless `--no-write` |

Survey needs nothing to run. Backfill and Check run Survey first if the manifest is missing. A request
naming one document ("write the config reference for this repo") goes straight to Backfill for that
document, because that is maximum intent and it must not be met with a questionnaire.

## Install

```sh
git clone https://github.com/hannsxpeter/docdna.git
cd docdna
./install.sh claude      # or: all | codex | cursor | windsurf
```

Then, in a session: "survey the documentation for this repo."

## What it writes

Backfill defaults to the **derivable ten**, the documents with near-zero hallucination surface because
they are read off the code rather than reasoned about:

`build.dev-setup` · `build.codebase-map` · `build.api-reference` · `build.config-reference` ·
`build.feature-flags` · `build.llms-txt` · `design.data-model` · `design.api-contract` ·
`frame.glossary` · `verify.dod`

Everything judgment-bearing is opt-in and named explicitly. Runs are capped at five documents, estimated
up front, and resumable, because an interrupted twenty-document run that loses its manifest degrades into
exactly the confident fiction this tool exists to prevent.

`verify.dod` is the sleeper. docdna emits enforced and claimed as two columns, and the gap between them is
the finding. Be exact about which column it can fill from evidence. What the signal registry observes here
is what is committed to the repository: CI workflow definitions (`deploy.ci`), a pull request template
(`proc.pr_template`), and a CODEOWNERS file (`proc.codeowners`). Whether a check is *required*, whether a
branch is protected, whether a merge queue exists, and whether a reviewer can actually block a merge are
forge settings, and none of the 132 signals can see them. Unless a committed settings file declares one,
that cell is an `unverifiable` GAP carrying the exact command a human can run to settle it, which is what
[`skill/templates/verify-dod.md`](skill/templates/verify-dod.md) requires. A workflow that runs and does
not gate is a signal, not enforcement.

## What it refuses

The refusals are the product. A tool that refuses nothing gets asked for everything.

- **No number is ever generated.** Not an RTO, RPO, SLA, availability target, capacity figure, retention
  period, or error budget. Every one is a decision a person owns. Numbers are cited or they are GAPs.
  The rule is absolute for the writer; enforcement is narrower and the difference is stated rather than
  papered over. A number resting on a `code` or `ref` citation is checked mechanically, against the four
  lines around the symbol or anchor the citation names, in a reference file that lives in the repository
  under analysis. A citation that names a file and no place inside it resolves and binds nothing. A number
  resting on a `run:` citation is **self-attested** and supports nothing: docdna never runs the documented
  repository's own commands, its tests, its scanners, its application, or anything on the network, so
  neither the command nor its output was ever observed, both are written by the model, both tools report
  the citation as
  SELF-ATTESTED, NOT VERIFIED, and `--verify` never calls such a document clean. A `human:` attestation is
  checked for shape only and is recorded as an attestation rather than a verification. Those limits are
  structural, not a backlog item, and
  [`skill/references/evidence.md`](skill/references/evidence.md) names all four in its second section.
- **No legal instrument.** No System Security Plan, PIA, DPIA, AIA, VPAT, or AI Act Annex IV file. docdna
  produces the evidence an assessor needs, under `docs/assure/inputs/`, and names who must sign. The
  signature line stays empty. At this version the refusal holds by absence: the catalog does not carry
  those instruments, so there is no id to select and no template to fill. The enforcement exists for when
  one is added. `producible: R` is in the schema, `docdna_backfill.py` refuses every entry marked it, and
  catalog invariant I1 fails the build if a template ever ships for an entry that is not `producible: Y`.
  Separately, nineteen of the sixty entries are `producible: M`, manifest-only: docdna tracks the row,
  states which signal made it required, and names what a human has to supply. Those nineteen are where the
  threat model, the runbook, and the data classification register live.
- **No runbook procedure.** An alert-to-runbook coverage table is derivable and safe. A remediation
  executed at 03:00 by somebody who did not write the system is the highest-consequence hallucination in
  the catalog, so docdna writes the index and leaves the procedure to a human.
- **No SBOM.** Real dependency resolution is not a stdlib job. docdna detects the ecosystem, emits the
  exact `syft` or `cdxgen` command, and records that command's output as evidence. A hand-written
  dependency list is a lie with a filename.
- **No code changes.** It reports where code and document disagree. It will not reconcile them by
  editing the code.

## How it decides

A 60-entry catalog organized by **lifecycle stage**, not by audience. Audience is not a partition: the
CTO's architecture view and the engineer's architecture view are one artifact at two zoom levels, and
tiering by reader guarantees four parallel document sets that drift.

Ten hard invariants are enforced at catalog load time rather than stated in prose, so a catalog change
that violates one fails the build instead of degrading quietly. They include the guardrail that no signal
alone may make a legal instrument required, and a semantic check that refuses every path from a
jurisdiction hint to a verdict rather than matching the syntax of one.

## Documentation

- [`skill/SKILL.md`](skill/SKILL.md), the entrypoint
- [`skill/catalog/SCHEMA.md`](skill/catalog/SCHEMA.md), normative catalog schema and the ten invariants
- [`skill/references/evidence.md`](skill/references/evidence.md), the citation and GAP rules
- [`CONTRIBUTING.md`](CONTRIBUTING.md)

## License

MIT. See [LICENSE](LICENSE).
