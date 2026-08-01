# Feature flag register template

Catalog id `build.feature-flags`. Default path `docs/build/feature-flags.md`. Producible Y. GAP prefix
`FLG`.

Normative. This file is an instruction set, not prose to copy. **No sentence below may appear in the
document.** A flag register is only useful if it is complete and current; a partial one gives a reader
confidence to delete code that is still live.

## Skeleton, in this order

1. The frontmatter block from the write plan's `frontmatter` object. See `_frontmatter.md`.
2. The reconstruction banner, verbatim from the write plan's `banner`. See `_banner.md`.
3. A single `#` heading.
4. The sections below, in order.
5. The document control block. See `_document-control.md`.

## Rules that outrank every section below

- Every table row carries a citation to an evaluation site, meaning the line that asks whether the flag is
  on.
- **The register lists flags this repository evaluates.** A flag configured in a vendor dashboard and
  never evaluated here is out of scope; a flag evaluated here and absent from the committed config is a
  finding. Say which situation each row is in.
- **No number is generated.** Rollout percentages, cohort sizes, and expiry dates come from a committed
  config file or they are `human-input` GAPs. A rollout percentage invented in a document has been acted
  on before.
- **Removal is a decision, not a fact.** When a flag should be removed is always a `human-input` GAP
  unless a committed file states a date or a ticket.
- **An exhaustive or negative claim is a claim about a search, not about a symbol.** "Every evaluated key
  has a committed default" and "no flag guards a dependency or a write path" are carried by a `run`
  citation holding the command and its output, or they are narrowed to the named set actually inspected,
  or they are an `unverifiable` GAP. A `code` citation resolves one symbol in one file and cannot support
  either shape. See `references/evidence.md`.

## `## Live flags`

**Evidence.** Evaluation sites: every call to the flag client, every read of a flag constant, every
conditional on a flag key. Plus the committed default for each key if a config file declares one.

**Write.** One table row per flag, columns: key, default in the repository, evaluation sites, what turning
it on changes. Cite the key to its declaration and each evaluation site to its symbol. Sort by key.

**Absent per cell.** The effect of a flag is not visible from its evaluation site:
`kind=unverifiable sev=major asks="What does <key> turn on? It gates a call whose behaviour is not
traceable from the call site."`

**Numbers.** A default is `true`, `false`, or a copied literal. A percentage appears only if a committed
file states it, cited to that file.

## `## Flags evaluated with no committed default`

**Evidence.** Keys evaluated in code with no matching entry in any committed flag configuration.

**Write.** One bullet per key, cited to the evaluation site. "The repository declares no default for this
key" is a negative claim about the whole tree, so each bullet also carries the search behind it as a `run`
citation, for example ``[run: `grep -rn "checkout_v2" -- . | grep -v src/` -> no matches]``. This is the
section that finds the flag whose behaviour in a fresh environment nobody can predict, which is worth
nothing if the absence was assumed rather than searched for.

**Absent.** "Every evaluated key has a committed default" is a negative universal: it asserts that the
search for an undeclared key came back empty. Write it only with a `run` citation holding that search, for
example
``[run: `comm -23 <(sort evaluated-keys.txt) <(jq -r 'keys[]' flags.json | sort)` -> no output]``.
If the search is not runnable here, narrow the sentence to the closed set in the table above ("each of the
nine keys listed above has a committed default, cited in its row") or emit
`kind=unverifiable sev=minor asks="Is any flag key evaluated somewhere outside the sites listed here? The
tree was not searched exhaustively."`

## `## Flags configured and never evaluated`

**Evidence.** Keys in a committed flag configuration with no evaluation site in the tree.

**Write.** One bullet per key, cited to the configuration entry, plus a `run` citation for the search that
found no evaluation site, for example ``[run: `grep -rn "legacy_pricing" src/` -> no matches]``. Each one
is either dead configuration or a flag another service reads. State that both readings are open rather
than choosing one.

## `## Kill switches`

**Evidence.** Only flags whose evaluation site guards a call to an external dependency, a write path, or a
whole request handler. This is a structural test, not a naming test: a key with `kill` in its name that
guards a log line is not a kill switch.

**Write.** One row per flag that passes the structural test: key, what it disables, and the evaluation
site. Cite both the flag and the guarded call.

**Absent.** "No flag guards a dependency or a write path" is a negative universal and one `code` citation
cannot carry it. Two honest forms. Narrow it to the closed set this document already enumerates: "none of
the twelve evaluation sites listed above guards an external call, a write, or a request handler", which
the cited rows themselves prove, since every evaluation site in the repository is supposed to be in that
table. Or carry the search as a `run` citation, for example
``[run: `grep -rn -A4 "flags.is_enabled(" src/ | grep -c "session.commit\|requests.\|httpx."` -> 0]``.
If neither is available, emit
`kind=unverifiable sev=minor asks="Does any flag guard an external dependency or a write path? The
evaluation sites were not all traced to what they gate."` Do not propose kill switches. That is a design
recommendation and this is a reference document.

## `## Owner and lifecycle`

**Evidence.** CODEOWNERS coverage of the file holding each evaluation site. Nothing else.

**Write.** One row per flag with its owning CODEOWNERS pattern, marked unconfirmed. If no CODEOWNERS
covers it, the cell is a GAP, not a guess.

**Absent.** Always, unless a committed file states a removal date or a ticket:
`kind=human-input sev=major asks="Which of these flags are permanent configuration and which are
temporary rollouts that should be removed? Nothing in the repository records the difference."`

**Never.** Do not derive an owner from commit history and do not derive an age from the first commit that
introduced the key unless you capture it as a `run` citation with the exact git command.

## Refuse to write

- If no flag system signal is present, this repository has no flags. A flag register for a project with no
  flags is regime cosplay. Report it and write no file.
- If cited claim blocks come out fewer than GAP markers, record `status: not-started` with the blockers
  and create no file.
