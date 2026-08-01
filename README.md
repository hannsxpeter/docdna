# docdna

[![CI](https://github.com/hannsxpeter/docdna/actions/workflows/ci.yml/badge.svg)](https://github.com/hannsxpeter/docdna/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](#install)
[![Agent skill](https://img.shields.io/badge/agent%20skill-SKILL.md-8A2BE2)](skill/SKILL.md)

**Derived from the code. Nothing asserted that the repo cannot prove.**

Point docdna at a repository. It reads the code, works out which documents that project actually owes,
tells you which of the documents you already have are now false, and writes the ones the code can prove.

It is a portable coding-agent skill. No service, no account, no build step, stdlib Python only.

**docdna stands alone.** It needs nothing but Python 3.8, and no relationship to any other tool is
required or assumed. If you also use [codedna](https://github.com/hannsxpeter/codedna), which fingerprints
how a repo writes code, the two run side by side: separate repositories, separate installs, no shared
code, and their agent-instruction blocks sit in one `AGENTS.md` without touching each other. If you do
not, nothing on this page changes.

## The problem

Documentation lies. Not by malice, by drift. The README says `npm run dev` and the script was renamed
fourteen months ago. The API doc lists eleven endpoints and the router registers twenty-three. The threat
model was written before the service went multi-tenant.

Meanwhile the documents that would actually survive a handover, an audit, or somebody leaving were never
written at all, because nobody could say which ones this particular project owes. Generating eighty
documents is easy and worthless. Deciding this repo needs eleven of them, naming which eleven and why, and
saying out loud which fifty were excluded and on what evidence, is the part that does not exist yet.

## What a first run looks like

Zero questions. Under fifteen seconds.

```
docdna  internal-service  ·  24k LOC Python/Django  ·  3 contributors  ·  GH Actions to k8s

Documentation  7 of 19       Drift  3 of your 7 documents contradict the code

WRONG NOW
  README.md            says `python manage.py runserver`;
                       Procfile and Dockerfile both run gunicorn
  docs/setup.md        last touched 2024-03-11; requirements.txt changed 47 times since
  docs/api.md          documents 11 endpoints; urls.py registers 23

MISSING AND LOAD-BEARING
  runbook coverage     12 alerts in ops/alerts.yml, 0 with a documented response
  on-call escalation   .pagerduty.yml exists; no escalation path written down
  decision records     0 ADRs; git log shows 3 framework swaps

NOT APPLICABLE  42 documents. Nothing ships to the EU, no AI, no external customers,
                no government buyer. Full ledger: .docdna/manifest.json

ASSUMED         the authors operate this. If a separate ops team does, 11 more
                documents become required.

NOTE            I only see documentation committed to this repo. If your docs live in
                Confluence or Notion, say so and I will mark those rows present-elsewhere
                rather than missing.

NEXT            write the 6 derivable documents (about 8 minutes)  ·  full manifest  ·  deep check
```

The drift section needs no setup, no frontmatter, and no prior run. It works on documents docdna has never
touched, which is why it comes first.

## Three modes

| Mode | Does | Writes |
| --- | --- | --- |
| **Survey** (default) | Scan, detect drift, decide the document set, write the manifest | `.docdna/manifest.json`, `DOCDNA.md` |
| **Backfill** | Generate selected documents from code evidence, with citations and GAP markers | `docs/**`, updates the manifest |
| **Check** | Drift, frontmatter lint, GAP rollup, stale exclusions. The CI gate. | Nothing |

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

`verify.dod` is the sleeper. The Definition of Done that is *actually enforced* is derivable from required
CI checks, branch protection, PR template checklists, and required reviewers. docdna emits enforced and
claimed as two columns. The gap between them is the finding.

## What it refuses

The refusals are the product. A tool that refuses nothing gets asked for everything.

- **No number is ever generated.** Not an RTO, RPO, SLA, availability target, capacity figure, retention
  period, or error budget. Every one is a decision a person owns. Numbers are cited or they are GAPs.
  The rule is absolute for the writer; enforcement is narrower and the difference is stated rather than
  papered over. A number resting on a `code` or `ref` citation is checked mechanically, against the four
  lines around the symbol or anchor the citation names, in a reference file that lives in the repository
  under analysis. A citation that names a file and no place inside it resolves and binds nothing. A number
  resting on a `run:` citation is **self-attested** and supports nothing: docdna is read-only and executes
  nothing, so the command and its output are both written by the model, both tools report the citation as
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
- **No code changes.** It will tell you the code contradicts the document. It will not reconcile them by
  editing the code.

## How it decides

A 60-entry catalog organized by **lifecycle stage**, not by audience. Audience is not a partition: the
CTO's architecture view and the engineer's architecture view are one artifact at two zoom levels, and
tiering by reader guarantees four parallel document sets that drift.

Selection runs off signals detected in the repo, an archetype (eight primaries, five overlays), and an
eight-question interview **of which none is asked on the first run**. Every answer is defaulted from
signals, labelled `assumed`, and shown with its blast radius, so you correct in one sentence instead of
answering a form.

Two properties do the real work:

**Exclusions expire.** Every not-applicable carries a `revisit_when` tripwire. When the signal that
justified skipping a document stops being true, Check says so and leads with it. No documentation
framework tells you when a document you correctly skipped last year became required.

**Absence of evidence is never encoded as false.** A detector that did not run reports `unknown`, and
`unknown` never silences a document. That is the difference between "we decided this does not apply" and
"we did not look", and it is the only reason the manifest is worth showing an assessor.

## Documentation

- [`skill/SKILL.md`](skill/SKILL.md), the entrypoint
- [`skill/catalog/SCHEMA.md`](skill/catalog/SCHEMA.md), normative catalog schema and the ten invariants
- [`skill/references/evidence.md`](skill/references/evidence.md), the citation and GAP rules
- [`CONTRIBUTING.md`](CONTRIBUTING.md)

## License

MIT. See [LICENSE](LICENSE).
