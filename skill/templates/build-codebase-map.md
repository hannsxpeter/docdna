# Codebase map template

Catalog id `build.codebase-map`. Default path `docs/build/codebase-map.md`. Producible Y. GAP prefix `MAP`.

Normative. This file is an instruction set, not prose to copy. **No sentence below may appear in the
document.** A codebase map is the document most likely to degrade into a directory listing with adjectives.
Every rule here exists to stop that.

## Skeleton, in this order

1. The frontmatter block from the write plan's `frontmatter` object. See `_frontmatter.md`.
2. The reconstruction banner, verbatim from the write plan's `banner`. See `_banner.md`.
3. A single `#` heading naming the repository.
4. The sections below, in order.
5. The document control block. See `_document-control.md`.

## Rules that outrank every section below

- Every paragraph, bullet, and table row carries a citation or a GAP marker.
- **Cite an area to a named file inside it, never to the directory.** A directory is not a symbol and
  cannot be resolved. `[`skill/scripts/docdna_scan.py#build_index`]` is a citation; `[`skill/scripts/`]`
  is not.
- **No number is generated.** File counts, line counts, service counts, and module counts are `run`
  citations carrying the command that produced them, for example
  ``[run: `git ls-files 'src/*' | wc -l` -> 61 files]``, or they are absent. Never estimate a count from
  the write plan and never round one.
- **What an area is for is not derivable from its name.** `utils/`, `core/`, `common/`, `lib/`, and
  `services/` name nothing. If no module docstring, package README, or CODEOWNERS comment states the
  purpose, emit an `unverifiable` GAP rather than a plausible sentence.
- Substitution test: "the `src/` directory contains the application source" survives swapping every
  project on earth into it. Delete it.
- **An exhaustive or negative claim is a claim about a search, not about a symbol.** "These are all the
  areas", "these are all the edges between them", and "nothing outside `src/` is executable" are carried
  by a `run` citation holding the command and its output, or they are narrowed to the named set actually
  inspected, or they are an `unverifiable` GAP. A `code` citation resolves one symbol in one file and
  cannot support either shape. See `references/evidence.md`.

## `## Areas`

**Evidence.** The write plan's `evidence.areas` list, each with its entry candidates, plus the entry file
inside each area.

**Write.** One table row per area: path, the entry file that anchors it, and what that entry file does,
stated from a cited symbol in the file. Order rows by the area a newcomer meets first, which is the one
holding the declared entry point, not alphabetically.

**Absent.** An area with no readable entry file:
`kind=unverifiable sev=minor asks="What is <path> for? No module docstring or README in it says."`

**Numbers.** A file count per area is a `run` citation or it is omitted from the table.

## `## Entry points`

**Evidence.** The same declaration sites the development setup document uses: `scripts` in
`package.json`, `project.scripts` in `pyproject.toml`, `[[bin]]` in `Cargo.toml`, `func main` in Go,
`Procfile`, Dockerfile `CMD`, serverless handler keys, the `main` field of a manifest.

**Write.** One bullet per entry point: the command or handler, the file it resolves to, and the first
function it calls. Cite the declaration and the function separately. This is the single highest-value
section, because it is the one thing a reader cannot get from the file tree.

**Absent.** No declared entry point:
`kind=not-implemented sev=major asks="How does this code get executed, and by what?"`

## `## How the areas depend on each other`

**Evidence.** Import and require statements crossing an area boundary. Nothing else. A shared type, a
naming similarity, and a comment are not dependencies.

**Write.** One bullet per real edge, in the form "A imports B", citing one importing file and the
imported symbol. State the direction. If an edge runs both ways, say so; a cycle between areas is a
finding a reader wants. **Do not claim the edge list is complete without a `run` citation** carrying the
search that produced it, for example
``[run: `grep -rn "^from \|^import " src/ | wc -l` -> 214 import statements]``. Without it, open the
section by naming which areas were searched, which is the honest completeness statement this document can
make.

**Absent.** If imports are dynamic or the language does not make edges greppable:
`kind=unverifiable sev=minor asks="Which areas depend on which? Imports here are resolved at runtime."`

**Never.** Do not draw an architecture diagram from inference. A diagram carries more authority than
prose and is harder to check.

## `## Where a change lands`

**Evidence.** Commits touching more than one area for a single change, CODEOWNERS routing, and test file
locations relative to source files.

**Write.** One row per common change type that the evidence actually supports: the change, the files it
touches, and the test that covers it. A row here is only worth writing when it names a file pair.

**Absent.** Omit the section. A guessed change map sends a newcomer to the wrong file and costs more than
no map at all.

## `## Ownership`

**Evidence.** CODEOWNERS only, at its committed path.

**Write.** One row per CODEOWNERS rule: pattern and owner, cited to the file and the pattern as a verbatim
anchor. Present it as routing, which is what it is, not as accountability.

**Absent.** No CODEOWNERS:
`kind=human-input sev=major asks="Who reviews changes to each area? Nothing in the repository routes
review."`

**Never present a commit-derived name as an owner in this section.** Frequent committer is not owner, and
publishing that equivalence creates an obligation nobody agreed to. That is the thing that is wrong, and
it is the only thing forbidden here.

A commit-derived name is still useful as a **candidate**, and docdna does derive one: `owner_candidate` in
the frontmatter carries the top committer when CODEOWNERS is silent, suffixed `(unconfirmed)`. See
`_frontmatter.md`. That field is where it lives, and nowhere else. It never appears in this table, it
never appears without the `(unconfirmed)` suffix, `owner` stays `unassigned` until a person accepts it,
and if a commit-derived name is mentioned in the body at all it carries the git command that produced it
as a `run` citation, for example
``[run: `git shortlog -sne -- src/billing | head -1` -> 41 commits, A. Patel]``.

## `## Not in this map`

**Evidence.** Directories the scan pruned, vendored trees, generated output, and any path excluded from
the run.

**Write.** One bullet per excluded tree with the reason it is excluded. An unexplained absence reads as an
oversight and costs the reader trust in the rest of the map.

## Refuse to write

- If the repository has one source directory and one entry file, this document has nothing to add over the
  file tree. Report that and write no file.
- If cited claim blocks come out fewer than GAP markers, record `status: not-started` with the blockers
  and create no file.
