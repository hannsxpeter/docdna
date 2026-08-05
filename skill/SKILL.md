---
name: docdna
description: Decide which documents a codebase owes, name which it does not owe and why, expire those exclusions with tripwires, and write the documents the code can prove, with citations. Also raises leads where a document and the code disagree. Use for documentation backfill, missing or stale docs, "what docs does this project need", handover prep, audit readiness, drifted README or API docs, ADRs, or a doc inventory.
allowed-tools: Read, Glob, Grep, Bash, Write, Edit
---

# DocDNA

Version: 1.2.0

## What this is

The documents that would survive a handover were never written because nobody could say which ones this
project owes. **docdna is a selection engine.** It decides which documents a repository owes, names which
it does not owe and on what evidence, sets an expiry tripwire on every one of those exclusions, and writes
the ones the code can prove. Linters, doc generators and link checkers all check what already exists;
deciding what should exist and then defending an absence is the job here.

**Say what "decides" means.** Of 132 signals, the count coming back present ranged 4 to 46 across 51
repositories, median 19. No corpus figure exists for `unknown`, so quote the run in hand, printed under
`not looked at, or refused`, never a median. docdna decides what the code can settle and shows what it
assumed about the rest. Never narrate it as more.

**The one rule, and everything else follows from it:** nothing is asserted that the repository cannot
prove. Every claim carries a citation or a GAP marker. There is no third state.

## Three modes

Read the user's intent and pick one.

- **Survey** (default): scan, decide the document set, report drift leads, write the manifest. Writes no
  documents. Triggered by "what docs does this need", "survey the documentation", "docdna".
- **Backfill**: write selected documents from code evidence. Triggered by "backfill the docs", "write the
  config reference", "document this repo".
- **Check**: drift, lint, GAP rollup, stale exclusions. The CI gate. Triggered by "check the docs against
  the code", "are our docs still true".

**Routing, three rules in order:**

1. **A request naming a single document goes straight to Backfill for that document.** "Write the threat
   model for this repo" is maximum intent and must not be met with a questionnaire. Write the manifest row
   as a side effect.
2. **Survey requires nothing.** No prior run, no answers, no `DOCDNA.md`.
3. **Backfill and Check run Survey first if `.docdna/manifest.json` is absent**, silently, and continue.

## Mode: Survey

**1. Scan.** The scanner decides nothing; it reports signals, the document inventory, and drift.

```sh
python3 "<skill-dir>/scripts/docdna_scan.py" --json <target-dir>
```

Resolve `<skill-dir>` to the directory containing this `SKILL.md`.

**2. Select.** Turn signals plus the catalog into a manifest.

```sh
python3 "<skill-dir>/scripts/docdna_select.py" <target-dir>
```

This writes `.docdna/manifest.json` (canonical) and `DOCDNA.md` (the one-screen human view). Cheap to
re-run, not idempotent from run one: it reads the prior manifest for the coverage delta and `DOCDNA.md`
is a document the next scan adopts, so run two differs by design and settles from run three. Say so.

**3. Report, selection first.** Drift used to lead and does not earn it. `command-not-found`: 3.2 percent
precision, 1 of 31, 0 of its 27 HIGH rows true, across 51 repositories. `path-not-found`: 10.9 percent, 5
of 46, on a separate **five-repository** holdout, its only adjudication. Six sections, in render order:

1. **MISSING AND LOAD-BEARING**: absent documents with a strong selecting signal, naming it and its file.
2. **NOT APPLICABLE**: one line with a count, plus only the exclusions within one signal of firing.
3. **NOTE**: the boundary, that only documentation committed to this repository is visible.
4. **ASSUMED**: the assumed answers with their blast radius, and nothing else; the unknown counts come
   from `docdna_scan.py`, not from here. The assumption load is part of the answer, not a footnote.
5. **POSSIBLE STALE REFERENCES**: drift, as leads, fifth of six. All three kinds render under this one
   heading, `path-not-found`, `command-not-found` and `count-mismatch`; `WRONG NOW` was retired in 1.1.0
   and nothing renders under it, because its value was that every row could be acted on unread and no kind
   earns that. Narrate each as a lead worth a human read. Never call the documentation wrong, never open
   with a count of documents that "contradict the code", never present a command row as settled. Say once
   that a document names a command or a path for many reasons and only one is a claim about this repo now,
   that 28 of 30 adjudicated command false positives made no claim about it at all, and that a reference is
   dropped only when its parent and first path component are both absent, so a deleted `docs/` is invisible.
6. **NEXT**: two or three concrete actions. `ORPHANED` follows 1, `UNCERTAIN` and `OPEN` precede 4.

**Never render the full exclusion ledger to the user.** It lives in `.docdna/manifest.json`; a 120-row
annotated shame list in the human view is the theater this skill exists to prevent.

**4. State the boundary, always**, whether or not anything prompted it. Reporting "absent" for a document
that lives in a wiki loses the reader's trust in every other row.

> I only see documentation committed to this repo. If your docs live in Confluence, SharePoint, or Notion,
> say so and I will mark those rows present-elsewhere rather than missing.

**5. Do not interview.** Zero questions on the first run. Every answer is defaulted from signals, labelled
`assumed`, and shown with what changes if it is wrong. The user corrects in one sentence:

```sh
python3 "<skill-dir>/scripts/docdna_select.py" --answer q2_operator=separate-ops-team <target-dir>
```

**6. Emit the agent index** when the repository has documents worth pointing an agent at. It writes
`llms.txt` plus its sidecar at `.docdna/meta/build.llms-txt.yml`, since `llms.txt` has nowhere to put
frontmatter. It indexes only what is present, and says so when the profile needs none.

```sh
python3 "<skill-dir>/scripts/docdna_llms.py" <target-dir>
```

**A repository that vendors another repository** (fixtures, examples, a bundled dependency) otherwise has
that documentation read as its own, against the wrong root. Name them with `--exclude-dir`, repeatable on
the scanner, selector and checker, or as `exclude_dirs` in `.docdna/config.json`, which the last two read.

## Mode: Backfill

**Default to the derivable ten**, read off the code rather than reasoned about, so they carry near-zero
hallucination risk: `build.dev-setup` · `build.codebase-map` · `build.api-reference` ·
`build.config-reference` · `build.feature-flags` · `build.llms-txt` · `design.data-model` ·
`design.api-contract` · `frame.glossary` · `verify.dod`. Anything judgment-bearing is opt-in and named
explicitly by the user.

**Estimate before starting.** "6 documents, roughly 8 minutes." Never begin without one.

```sh
python3 "<skill-dir>/scripts/docdna_backfill.py" --limit 5 <target-dir>
python3 "<skill-dir>/scripts/docdna_backfill.py" --only build.config-reference <target-dir>
```

**Bounded at five documents per invocation** unless the user passes `--all`, which prints an estimate and
waits for `--yes`. A long run risks compaction dropping the manifest mid-run, and confident fiction after.

**`write_status` is updated in the manifest after every document**, so an interrupted run resumes rather
than restarting. `--branch` puts the run on its own branch with one commit per document.

### Writing a document

1. **Gather evidence first, structure second.** Read the files the catalog entry names in `covers`. If the
   evidence is thin, the document is thin. Do not pad it into shape.
2. **Open with the frontmatter** from `templates/_frontmatter.md`, then the banner from
   `templates/_banner.md`. Both are mandatory and neither is editable by you.
3. **Cite every claim block.** A claim block is a paragraph, a bullet, or a table row. Four classes only,
   defined in `references/evidence.md`: `code`, `run`, `ref`, `human`. Never a bare line number; a symbol
   name or a verbatim anchor survives reformatting and a line number does not.
4. **GAP everything else**, using the paired syntax in `templates/_gap.md`. Both lines, always.
5. **Close with the document control block** from `templates/_document-control.md`.
6. **Verify adversarially, with this command, once per document written:**

   ```sh
   python3 "<skill-dir>/scripts/docdna_backfill.py" --verify docs/build/config-reference.md <target-dir>
   ```

   It re-reads every citation against the code. Assume each claim is wrong until the file proves it right.
   FAIL means delete the claim, not soften it; a hedge still reads as documentation, and the auto-delete
   touches only text written in this run. A pass sets the row to `verified`; `--keep` leaves a stub. It
   cannot judge whether an anchor supports the sentence or execute a `run:` command, so an exhaustive
   claim can pass; `references/evidence.md` governs.

**If cited claim blocks are fewer than GAP markers, do not write the file.** Record it in the manifest as
`status: not-started` with its blockers. An empty file that exists is worse than a missing document that
is tracked, because the empty one stops anyone from noticing.

## Mode: Check

```sh
python3 "<skill-dir>/scripts/docdna_check.py" <target-dir>
python3 "<skill-dir>/scripts/docdna_check.py" --fail-on blocker --only drift <target-dir>
```

Six passes over one walk: drift, frontmatter lint, GAP rollup, traceability spine, **tripwires**, orphans.

**Lead with tripwires when any fire.** A tripwire is an exclusion whose `revisit_when` predicate has become
true: a document correctly skipped last quarter that the code now requires. It is the reason to re-run.
Firing is observed on a real repository: `docdna_check.py` on docdna itself fires `govern.ownership`, now
true on `users.is_oss` and `q1_users`. Every firing so far, there and in tests, is a **first evaluation**,
the predicate already true when first checked. Unobserved is the temporal case the feature rests on, one
flipping across elapsed time under an older manifest. Report a predicate true now, not one watched turn.

Drift is a **warning** by default. It gates CI only for documents the user names in `assurance_set` in
`.docdna/config.json`, typically three to five. A gate that turns everything red gets disabled in week two.

**Exit codes.** `docdna_check.py` exits 1 on a gated finding, 2 on a bad invocation. `docdna_backfill.py`
exits 3 for `--all` without `--yes` and 1 when `--verify` finds a document not clean; it,
`docdna_select.py` and `docdna_llms.py` otherwise exit 0 when they ran and 2 when they could not, while
`docdna_scan.py` and `docdna_wire.py` return no status of their own, so their 0 reports nothing.
**Planning or writing zero documents is exit 0**: a repository that owes none of the derivable ten is an
answer, and the refusals name their reasons.

## Script flags

The whole CLI surface. Every helper takes a positional `repo` (default `.`) and `--json`; `llms` takes no more.

| Script | Other flags |
| --- | --- |
| `docdna_scan.py` | `--family <f>` limit gated passes to one signal family, repeatable; `--deep` per-document git metrics; `--exclude-dir <dir>` repeatable; `--max-evidence <n>` evidence records kept per signal |
| `docdna_select.py` | `--answer key=value` record an interview answer, repeatable; `--unattended` take every unanswered question at its default and never ask; `--scan <path>` read scanner JSON instead of rescanning; `--exclude-dir <dir>` repeatable |
| `docdna_backfill.py` | `--only <id>` plan this catalog id instead of the derivable ten, repeatable; `--all` lift the five-document cap, prints an estimate and waits; `--yes` answer that confirmation; `--limit <n>` never above 5; `--branch` own branch, one commit per document; `--verify <path>` re-read a written document and check every claim, see Backfill step 6; `--keep` leave a refused stub on disk instead of removing it; `--confirm-sensitive` below |
| `docdna_check.py` | `--fail-on blocker\|major\|minor\|never` default `major`; `--only drift\|lint\|gaps\|spine\|tripwires\|orphans` repeatable; `--scan <path>`; `--no-write` never touch `DOCDNA.md`; `--exclude-dir <dir>` repeatable |
| `docdna_wire.py` | `--agent agents\|claude\|gemini\|copilot\|cursor\|cascade` repeatable; `--all` create or update every supported target |

**`--confirm-sensitive` is a decision, not a lever.** It records that a person knows this repository is
public or of unknown visibility and accepts that an `internal` or higher document in it can be read by
anyone. Never pass it to clear the refusal; a private repository says so once, with `--answer q1_users`.

## Evidence rules

Read `references/evidence.md` before writing anything. The rules that get violated most:

**No number is ever generated.** Not a recovery time objective, recovery point objective, SLA, availability
target, capacity figure, retention period, support-window end date, error budget, or review cadence. Each
is a decision a human owns. Numbers are cited to a file that states them, or they are `human-input` GAPs.
`code` and `ref` numbers bind only the four lines around the place cited, in a file inside the repository
under analysis; one naming no place binds nothing. A `run:` number is self-attested and supports nothing;
a `human:` one is shape-checked. Every line after the frontmatter is read, headings and table header rows
included, and the banner and control table answer to what docdna derived, not to a citation.

**An exhaustive or negative claim needs a `run` citation.** "Every declared key has a read site", "no flag
guards a write path": a `code` citation resolves one symbol in one file and carries neither. Cite the
search command with its output, narrow the claim to the set you inspected, or emit an `unverifiable` GAP.
The verifier cannot catch this one, because the anchor does resolve.

**Substitution test.** Swap the project name for a competitor's and the stack for a different one. If the
sentence survives it is not documentation: "the system follows a layered architecture" survives.

**Every selected document names what selected it.** A signal-selected row cites that signal and its file;
one selected by the catalog baseline, an interview answer, or a signal's absence names which instead and
has no path, none of the three being a place in the code. Read the row's `evidence` before promising a
path, and note a row naming no signal is not thereby unrequired: `govern.manifest` is required with none.

**Every exclusion carries a reason, a citation, and a tripwire.** An unexplained exclusion is worse than a
missing document, because it launders a gap into a decision.

## What this does not do

State these when asked, rather than attempting them.

1. **Does not write, fix, or change code.** It reports where code and document disagree, and never
   reconciles them by editing the code.
2. **Does not invent numbers, and does not claim the check catches every one.** The writing rule is
   absolute; the verifier reaches only `code` and `ref` numbers, since docdna never runs the documented
   repository's own commands (non-goal 7), so a `run:` number is never observed.
3. **Does not certify, attest, or sign.** No authority to operate, CE marking, declaration of conformity,
   or completed VPAT. It produces the inputs an assessor needs and names who must sign, empty.
4. **Does not draft legal or regulator-facing instruments.** No SSP, HIPAA risk assessment, BAA, SOC 2
   system description, PCI attestation, PIA, DPIA, AIA, FRIA, ACR, or AI Act Annex IV file. **Seventeen
   entries are `producible: R`**, so each is ruled on rather than absent: backfill declines it and prints
   its `refusal_reason` and `signed_by` role, which quote verbatim, since naming the signer is what makes
   a refusal actionable. Only an interview answer may raise an R entry to `required`, never a signal
   (I6); I1 fails the build if a template ships for one. It emits an evidence annex under
   `docs/assure/inputs/` instead, and the thirty-seven `M` entries name what a human must write.
5. **Does not give legal advice or assert that a regime applies.** It reports the signal, names the regime
   that signal might trigger, and says to confirm with counsel.
6. **Does not generate an SBOM.** Real dependency resolution is not a stdlib job. It detects the ecosystem,
   emits the exact `syft` or `cdxgen` command, and records that output as `run` evidence. A hand-written
   dependency list is a lie with a filename.
7. **Does not run tests, scanners, the application, or anything on the network.**
8. **Does not write a runbook procedure or a completed access-control matrix.** Inventory only: an alert
   list with "no documented remediation", a route-to-guard table with explicit unknown cells.
9. **Does not fabricate decision rationale.** Reconstructed ADRs live in a separate `adr-draft-` id space
   with the Considered Options section absent, not filled with "unknown".
10. **Does not maintain the documentation.** It backfills and it lints. It does not auto-commit, run on a
    schedule, or overwrite a document a human edited since generation.
11. **Does not emit a folder named `rfc/`.** In any ITSM-adjacent shop "RFC" reads as Request for Change.
    The debate artifact is a **design proposal**.
12. **Does not write an `internal` or higher document into a public or unknown-visibility repository**
    without `--confirm-sensitive`. Visibility is one of the things the scanner refuses to guess.
13. **Does not fingerprint code style.** Naming conventions and comment voice are a different problem.

## Wiring

A manifest no agent reads changes nothing. After a Survey:

```sh
python3 "<skill-dir>/scripts/docdna_wire.py" <target-dir>
```

Creates or updates `AGENTS.md` as the portable baseline and updates tool-specific files that already
exist. The block coexists with any other tool's block in the same file. Without the helper, add this by
hand to `AGENTS.md`, and to `CLAUDE.md` for Claude Code:

```
<!-- docdna:start -->
## Project documentation

The documentation set for this repo is indexed in [DOCDNA.md](DOCDNA.md): which documents exist, who owns them, when they were last verified against the code, and what is deliberately not applicable. Agent-readable index at [llms.txt](llms.txt). Before answering questions about how this system works, prefer a document listed there over inference. If a document contradicts the code, the code is correct and the document is stale; say so.
<!-- docdna:end -->
```

Keep the last sentence: without it, a pointer block makes stale documentation authoritative.

## Reference files

Load on demand, by name. Do not read them all.

| File | When |
| --- | --- |
| `catalog/SCHEMA.md` | Changing the catalog, or interpreting a predicate |
| `catalog/documents.json` | Every Survey. One read replaces ninety-six document lookups. |
| `references/evidence.md` | Every Backfill, before writing |
| `templates/_frontmatter.md`, `_gap.md`, `_banner.md`, `_document-control.md` | Every Backfill |
| `templates/<stage>-<slug>.md` | Only for the entry being written |
