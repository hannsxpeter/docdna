# Catalog maintenance

Who owns the catalog, how to change it, what fails a bad change, and what this version deliberately does
not ship.

The catalog is the product. `SKILL.md` is a procedure and the scripts are plumbing, but the decision about
which documents a repository owes lives in five JSON files, and it is the only part of docdna that goes
stale on its own.

## Owner and cadence

**Maintainer of record: @hannsxpeter.** One name, not a team, because a catalog owned by everybody is
reviewed by nobody, and the failure this document exists to prevent is silent rot.

| Cadence | What happens |
| --- | --- |
| Every release | Entry counts reconciled with the tests. Any new signal pattern has a false-positive fixture. |
| Quarterly | Read the exclusion rules end to end. An exclusion whose `revisit_when` can never fire is a bug. |
| On any report of a false positive | Fixture first, then the fix. The fixture stays forever. |

A quarterly review that does not happen is worse than no stated cadence, because the stated cadence is what
a reader trusts. If the cadence lapses, say so in `CHANGELOG.md` rather than letting the claim stand.

## The five files

All five are JSON, never YAML. stdlib has no `yaml` module, and a hand-rolled parser breaks on the first
user who writes a comment or an anchor. Each is a single top-level object with `schema` plus one payload
array, so a version bump is detectable without parsing the payload.

| File | Holds | Shipped | Change it when |
| --- | --- | --- | --- |
| `signals.json` | Signal registry: families, gates, detectors, caps | 132 | Detection changes, or a new fact about a repo becomes worth reading |
| `documents.json` | Catalog entries: id, stage, durability, scope, producible, cadence, path | 61 | A document class is named, retired, or repathed |
| `rules.json` | Verdict rules: a predicate plus an effect | 88 | Selection changes, including every new exclusion |
| `archetypes.json` | 8 primaries, 5 overlays, the unknown floor | 13 | A project shape is genuinely not covered |
| `interview.json` | 8 questions, defaults, counterfactual text | 8 | Rarely. A ninth question needs an argument. |

[`skill/catalog/SCHEMA.md`](../skill/catalog/SCHEMA.md) is normative for all five. Read it before editing
any of them.

## How to change it

1. **Read SCHEMA.md first.** Every field is an enum or a predicate, and `docdna_select.py` rejects the file
   rather than degrading quietly.
2. **Keep every list sorted by id.** A catalog diff has to be readable, or nobody reviews it.
3. **Never rename an id. Deprecate and add.** Ids are the join key across all five files and across every
   user's `.docdna/manifest.json`. A rename is a breaking change to state you do not control.
4. **Adding a document entry is cheap. Adding a template is not.** Naming a document and ruling on it costs
   one JSON row, and naming a document as not-applicable-with-a-reason is most of the audit value. A
   template is an invitation to fill it, so a template is only correct where the content is genuinely
   derivable from code.
5. **Every new grep pattern ships with a false-positive fixture**, not just a positive one. The fixtures in
   `tests/fixtures/` exist because earlier versions of these patterns matched a French locale file, a
   client-side Vue router, a weather API's `latitude` column, and a GDPR library's README prose.
6. **New security patterns exclude locales, i18n bundles, `.po` files, and lockfiles**, globally, before
   matching. This is not tuning; a lexicon without those exclusions is a bug.
7. **Jurisdiction signals stay capped at `hint`.** A hint may open a question. It may never set a verdict,
   and invariant I4 enforces that.
8. **A new family is a schema bump.** The fifteen families are a fixed enum: `arch`, `deploy`, `iface`,
   `data`, `ai`, `users`, `sec`, `supply`, `ops`, `qual`, `jur`, `proc`, `docs`, `a11y`, `scale`.
9. **Change the counts and the tests in the same commit.** That is how the catalog stays a decision rather
   than a drawer.

## The invariants

`docdna_select.py` calls `check_invariants()` before it does anything else and **exits nonzero on any of
these**, listing every failure at once rather than the first.

| # | Fails when |
| --- | --- |
| I1 | A template file exists for a `producible` of `M` or `R` |
| I2 | A rule, overlay, or question references a document id absent from `documents.json` |
| I3 | A predicate or `cite` names a signal id absent from `signals.json` |
| I4 | A rule tests `{"is": "hint"}` and its effect is not `ask` or `note` |
| I5 | Any `default_from` entry exists on `q4_decides_about_people` |
| I6 | A rule sets `require` or `recommend` on a `producible: R` document with no `answer` term in `when` |
| I7 | A rule with `effect: exclude` lacks `because`, `cite`, or `revisit_when` |
| I8 | A document, rule, or answer sits outside its enum |
| I9 | Two documents share an id, or two rules share an id |
| I10 | A `product` or `org` scoped document does not set `system_of_record` to `ask` |

**These run on the user's machine, not only in our CI**, which is the point. A catalog that violates one
fails the next run rather than the next audit.

I6 is the compliance guardrail expressed in code rather than in prose: **no signal alone may make a legal
instrument required.** A human answering Q3 or Q5 is the only path, because prose guardrails lose to "just
fill it in, I will review it later".

Catalog tests belong in `tests/test_catalog.py`: the ten invariants against the shipped files, the entry
counts, and the sort order. The CI workflow parses every file under `skill/catalog/` and runs
`python -m unittest discover -s tests` on every push.

## What this version does not ship, and why

**docdna ships no dated regulatory reference files at this version. There is no `references/regime-facts/`
directory, and that is a decision, not a backlog item.**

Six files of dated regulatory facts (EU, US, Canada, standards, accessibility, AI) is a standing quarterly
commitment for as long as the project exists. Annexes get renumbered, transition dates move, guidance is
withdrawn and reissued. **An unmaintained regime file is worse than no regime file**, because it is
authoritative-looking, dated, and wrong, and every document that cites it inherits the error with
confidence. That is the exact failure mode this skill exists to prevent, so shipping it inside the skill
would be self-refuting.

Three consequences, stated plainly:

- **The `ref:` evidence class currently has nothing in this repository to point at.** The example in
  `references/evidence.md` (`[ref: docs/regime-facts/eu.md#annex-iv, verified 2026-07-31]`) shows the
  syntax, not a shipped file. A `ref:` citation points at a reference file the *user's* repository
  carries, and only there: `--verify` refuses as a blocker any `ref:` that resolves inside the docdna
  skill instead, because no author of the repository under analysis controls those files and a `ref:`
  that lands there laundered the same number into every install. A regulatory claim with no such file in
  the repository is a `human:` citation or a GAP. It is never model knowledge.
- **Compliance categories live in the catalog as manifest rows, not as generated documents.** Of 61
  entries, 41 are `producible: Y` and **20 are `producible: M`, which means named, ruled on, assigned an
  owner candidate, and stated as what a human must produce.** No file is created. That is the
  entire compliance offering at this version, and it is deliberately the useful half: knowing that a
  control mapping is owed, and by whom, is worth more than a generated control mapping that nobody signed.
- **The `R` tier ships zero entries.** The tier exists in the schema, and I1 and I6 are already enforced,
  so the day a regulator-facing instrument is added to the catalog it lands as `R`, cannot acquire a
  template, and cannot be escalated by a signal. The guardrail precedes the entries on purpose.

`SKILL.md` states the refusals in prose for the agent. This file states why the catalog behind them is
smaller than the design spec's target, which is that a 159-entry catalog with 16 refused legal instruments
implies regime data this project has not committed to maintaining.

## If regime facts are ever added

Do not add them casually. The conditions are all of the following, and they are cheaper to accept up front
than to retrofit:

- **Six files, not fifteen.** Six is what one maintainer will actually re-verify. A seventh file is a
  proposal to stop verifying all of them.
- **Every file carries `verified: YYYY-MM-DD`** at the top, and only facts that gate a decision. A regime
  file is not a summary of a regulation; it is the three sentences that change which document is required.
- **The aging lint reports "as of `<date>`, confirm before relying" as info, never as a failure.** A skill
  that puts itself into permanent red on day 181 has taught its user to ignore its own output.
- **CI reports aging references in the build log**, so the decay is visible before a user finds it.
- **If a file goes two cadences without verification, delete it.** Removing a stale fact and reverting the
  claims that cite it to GAPs is a smaller failure than leaving it in place, and it is the only version of
  this commitment that stays honest under neglect.
