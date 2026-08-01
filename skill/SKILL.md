---
name: docdna
description: Backfill a project's documentation from its codebase. Decides which documents the repo actually owes and which it does not, flags docs that now contradict the code, and writes the ones the code can prove, with citations. Use for documentation backfill, missing or stale docs, "what docs does this project need", handover prep, audit readiness, drifted README or API docs, ADRs, or a doc inventory.
allowed-tools: Read, Glob, Grep, Bash, Write, Edit
---

# DocDNA

Version: 1.0.0

## What this is

Documentation lies, not by malice but by drift, and the documents that would survive a handover were never
written because nobody could say which ones this project owes. docdna answers three questions from the
code: **which documents does this project owe, which of the ones you have are now false, and what can I
write without asking anyone.** It is a selection engine and a drift detector first, a generator third.

**The one rule, and everything else follows from it:** nothing is asserted that the repository cannot
prove. Every claim carries a citation or a GAP marker. There is no third state.

## Three modes

Read the user's intent and pick one.

- **Survey** (default): scan, detect drift, decide the document set, write the manifest. Writes no
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

---

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

This writes `.docdna/manifest.json` (canonical, machine-readable) and `DOCDNA.md` (the one-screen human
view). It is a pure function of the scan plus the catalog, so re-running it is free and idempotent.

**3. Report, drift first.** Lead with what is wrong, not what is missing. A document the code proves false
is concrete and undeniable; a missing document is abstract and arguable. Order every report:

1. **WRONG NOW**: documents that contradict the code, with the contradiction quoted.
2. **MISSING AND LOAD-BEARING**: absent documents whose selecting signal is strong.
3. **NOT APPLICABLE**: one line with a count, plus only the exclusions within one signal of firing.
4. **ASSUMED**: the assumed answers with their blast radius.
5. **NEXT**: two or three concrete actions.

**Never render the full exclusion ledger to the user.** It lives in `.docdna/manifest.json`. A 120-row
annotated shame list in the human view is the theater this skill exists to prevent.

**4. State the boundary, always.** Print this whether or not anything prompted it:

> I only see documentation committed to this repo. If your docs live in Confluence, SharePoint, or Notion,
> say so and I will mark those rows present-elsewhere rather than missing.

Reporting "absent" for a document that lives in a wiki loses the reader's trust in every other row.

**5. Do not interview.** Zero questions on the first run. Every answer is defaulted from signals, labelled
`assumed`, and shown with what changes if it is wrong. The user corrects in one sentence:

```sh
python3 "<skill-dir>/scripts/docdna_select.py" --answer q2_operator=separate-ops-team <target-dir>
```

**6. Emit the agent index** when the repository has documents worth pointing an agent at. This writes
`llms.txt` plus its metadata sidecar at `.docdna/meta/build.llms-txt.yml`, because `llms.txt` is not
Markdown and has nowhere to put frontmatter. It indexes only what is present, and says so when nothing in
the profile requires an `llms.txt`.

```sh
python3 "<skill-dir>/scripts/docdna_llms.py" <target-dir>
```

**A repository that vendors another repository** (fixtures, examples, a bundled dependency) will otherwise
have that repository's documentation read as its own, and its citations resolved against the wrong root.
Name them once with `--exclude-dir tests/fixtures`, repeatable on `docdna_scan.py`, `docdna_select.py`, and
`docdna_check.py`, or as `exclude_dirs` in `.docdna/config.json`, which the latter two read.

---

## Mode: Backfill

**Default to the derivable ten.** These are read off the code rather than reasoned about, so they carry
near-zero hallucination risk:

`build.dev-setup` · `build.codebase-map` · `build.api-reference` · `build.config-reference` ·
`build.feature-flags` · `build.llms-txt` · `design.data-model` · `design.api-contract` · `frame.glossary`
· `verify.dod`. Anything judgment-bearing is opt-in and named explicitly by the user.

**Estimate before starting.** "6 documents, roughly 8 minutes." Never begin without one.

```sh
python3 "<skill-dir>/scripts/docdna_backfill.py" --limit 5 <target-dir>
python3 "<skill-dir>/scripts/docdna_backfill.py" --only build.config-reference <target-dir>
```

**Bounded at five documents per invocation** unless the user passes `--all`, which prints an estimate and
waits for `--yes`. The failure a thirty-document run causes is not that the user stops; it is that
compaction mid-run drops the manifest and the run degrades into confident fiction.

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

   It re-reads every citation and resolves it against the code. Assume each claim is wrong until the file
   proves it right. FAIL means delete the claim, not soften it; a hedge still reads as documentation, and
   this auto-delete applies only to text written in this run. A pass sets the manifest row to `verified`.
   `--keep` leaves a refused stub on disk. What it cannot do: judge whether an anchor supports the
   sentence, or execute a `run:` command. So an exhaustive claim can pass and still be false, and a `run:`
   citation is the writer's own transcript. Both are why `references/evidence.md` governs at write time.

**If cited claim blocks are fewer than GAP markers, do not write the file.** Record it in the manifest as
`status: not-started` with its blockers. An empty file that exists is worse than a missing document that
is tracked, because the empty one stops anyone from noticing.

---

## Mode: Check

```sh
python3 "<skill-dir>/scripts/docdna_check.py" <target-dir>
python3 "<skill-dir>/scripts/docdna_check.py" --fail-on blocker --only drift <target-dir>
```

Six passes over one walk: drift, frontmatter lint, GAP rollup, traceability spine, **tripwires**, orphans.

**Lead with tripwires when any fire.** A tripwire is an exclusion whose `revisit_when` predicate has
become true: a document correctly skipped last quarter that the code now requires. Nothing else in the
documentation world tells you this, and it is the reason to re-run the tool.

Drift is a **warning** by default. It gates CI only for documents the user names in `assurance_set` in
`.docdna/config.json`, typically three to five. A gate that turns everything red gets disabled in week two.

**Exit codes.** `docdna_check.py` exits 1 on a gated finding and 2 on a bad invocation. Every other helper
exits 0 when it ran and 2 when it could not. `docdna_backfill.py` also exits 3 for the single case where
`--all` was passed without `--yes`, so the run never started. **Planning or writing zero documents is exit
0**: a repository that owes none of the derivable ten is an answer, and the refusals carry their reasons
in the JSON.

---

## Script flags

The whole CLI surface. Every helper takes a positional `repo` (default `.`) and `--json`; `docdna_llms.py`
takes nothing else. Flags marked repeatable may be passed more than once.

| Script | Other flags |
| --- | --- |
| `docdna_scan.py` | `--family <f>` limit gated passes to one signal family, repeatable; `--deep` per-document git metrics; `--exclude-dir <dir>` repeatable; `--max-evidence <n>` evidence records kept per signal |
| `docdna_select.py` | `--answer key=value` record an interview answer, repeatable; `--unattended` take every unanswered question at its default and never ask; `--scan <path>` read scanner JSON instead of rescanning; `--exclude-dir <dir>` repeatable |
| `docdna_backfill.py` | `--only <id>` plan this catalog id instead of the derivable ten, repeatable; `--all` lift the five-document cap, prints an estimate and waits; `--yes` answer that confirmation; `--limit <n>` never above 5; `--branch` own branch, one commit per document; `--verify <path>` re-read a written document and check every claim, see Backfill step 6; `--keep` leave a refused stub on disk instead of removing it; `--confirm-sensitive` below |
| `docdna_check.py` | `--fail-on blocker\|major\|minor\|never` default `major`; `--only drift\|lint\|gaps\|spine\|tripwires\|orphans` repeatable; `--scan <path>`; `--no-write` never touch `DOCDNA.md`; `--exclude-dir <dir>` repeatable |
| `docdna_wire.py` | `--agent agents\|claude\|gemini\|copilot\|cursor\|cascade` repeatable; `--all` create or update every supported target |

**`--confirm-sensitive` is a decision, not a lever.** It records that a person knows this repository is
public or of unknown visibility and accepts that an `internal` or higher document written into it can be
read by anyone. Never pass it to clear the refusal. If the repository is private, say so once with
`docdna_select.py --answer q1_users=<value>` and every later run inherits the answer.

## Evidence rules

Read `references/evidence.md` before writing anything. The rules that get violated most:

**No number is ever generated.** Not a recovery time objective, recovery point objective, SLA, availability
target, capacity figure, retention period, support-window end date, error budget, or review cadence. Each
is a slot in a real template and a decision a human owns. Numbers are cited to a file that states them, or
they are `human-input` GAPs. The rule is absolute for you; enforcement is narrower and says so. `code` and
`ref` numbers bind only the four lines around the place cited, in a file inside the repository under
analysis; one naming no place binds nothing. A `run:` number is self-attested and supports nothing; a
`human:` one is shape-checked. Every line after the frontmatter is read, headings, table header rows,
banner and control table included; the last two answer to what docdna derived, not to a citation.

**An exhaustive or negative claim needs a `run` citation.** "Every declared key has a read site", "no flag
guards a write path", "there are no collisions": a `code` citation resolves one symbol in one file and
cannot carry any of them. Run the search and cite the command with its output, or narrow the claim to the
named set you actually inspected, or emit an `unverifiable` GAP. The verifier cannot catch this one after
the fact, because the anchor does resolve.

**Substitution test.** Swap the project name for a competitor's and the stack for a different one. If the
sentence survives, it is not documentation. "The system follows a layered architecture" survives and is
worthless; "requests enter through `cmd/api/main.go`, which mounts four route groups" does not.

**Every selected document names its triggering signal, with a file path.** A document that cannot name
what selected it is not required.

**Every exclusion carries a reason, a citation, and a tripwire.** An unexplained exclusion is worse than a
missing document, because it launders a gap into a decision.

---

## What this does not do

State these when asked, rather than attempting them.

1. **Does not write, fix, or change code.** It reports that the code contradicts the document. It does not
   reconcile them by editing the code.
2. **Does not invent numbers, and does not claim the check catches every one.** The writing rule is
   absolute. The verifier reaches `code` and `ref` numbers, bound to the place cited; a `run:` number is
   self-attested because docdna executes nothing (non-goal 7), a `human:` one is shape-checked.
3. **Does not certify, attest, or sign.** No authority to operate, CE marking, declaration of conformity,
   or completed VPAT. It produces the inputs an assessor needs and names who must sign, empty.
4. **Does not draft legal or regulator-facing instruments.** No System Security Plan, PIA, DPIA, AIA,
   FRIA, ACR, or AI Act Annex IV file. It emits a differently-named evidence annex under
   `docs/assure/inputs/` and a list of who must sign. The catalog carries no such instrument at this
   version, so there is no id to ask for; `producible: R` in `docdna_backfill.py` and invariant I1 hold
   the line for when one is added, and the twenty `producible: M` entries name what a human must write.
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

---

## Wiring

A manifest no agent reads changes nothing. After a Survey:

```sh
python3 "<skill-dir>/scripts/docdna_wire.py" <target-dir>
```

Creates or updates `AGENTS.md` as the portable baseline and updates tool-specific files that already
exist. The block coexists with any other tool's block in the same file.

If you cannot run the helper, add this block by hand to `AGENTS.md`, and to `CLAUDE.md` for Claude Code:

```
<!-- docdna:start -->
## Project documentation

The documentation set for this repo is indexed in [DOCDNA.md](DOCDNA.md): which documents exist, who owns them, when they were last verified against the code, and what is deliberately not applicable. Agent-readable index at [llms.txt](llms.txt). Before answering questions about how this system works, prefer a document listed there over inference. If a document contradicts the code, the code is correct and the document is stale; say so.
<!-- docdna:end -->
```

The last sentence is not decoration: a pointer block that does not state precedence makes stale
documentation authoritative.

## Reference files

Load on demand, by name. Do not read them all.

| File | When |
| --- | --- |
| `catalog/SCHEMA.md` | Changing the catalog, or interpreting a predicate |
| `catalog/documents.json` | Every Survey. One read replaces sixty document lookups. |
| `references/evidence.md` | Every Backfill, before writing |
| `templates/_frontmatter.md`, `_gap.md`, `_banner.md`, `_document-control.md` | Every Backfill |
| `templates/<stage>-<slug>.md` | Only for the entry being written |
