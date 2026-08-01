# Agent documentation index template

Catalog id `build.llms-txt`. Default path `llms.txt`. Producible Y. GAP prefix `LLM`.

Normative. This file is an instruction set, not prose to copy. **No sentence below may appear in the
document.** This is the one document in the catalog whose format is set by an external specification, so
the specification wins over docdna's usual layout in the two places they conflict.

## Where the format differs from every other document

`llms.txt` must open with an H1 and it must not open with a YAML block, so:

1. **The frontmatter goes in a sidecar** at `.docdna/meta/build.llms-txt.yml`, carrying every field from
   the write plan's `frontmatter` object unchanged. See `_frontmatter.md`. The lint requires the sidecar
   for any catalog entry whose path is not Markdown, and this is that case.
2. **The banner stays in the file**, as a plain paragraph immediately after the summary blockquote, not as
   a blockquote of its own and not as a heading. Same three lines from the write plan's `banner`, with the
   leading `> ` removed from each. See `_banner.md`.
3. **The document control block goes in the sidecar**, under a `document_control` key, because an H2
   section that is not a link list breaks a strict `llms.txt` parser. See `_document-control.md`.

Everything else, including the citation rule and the GAP rule, applies unchanged.

## Skeleton, in this order

1. `# ` plus the project name, taken from the `name` key of the package manifest, cited in the sidecar's
   `open_questions` if no manifest declares one.
2. A blockquote of one or two sentences saying what this project is.
3. The banner, three plain lines.
4. One H2 per audience-shaped group, each a markdown link list.
5. An `## Optional` H2 last, holding links a reader may skip. The specification gives this section that
   exact meaning, so do not use it as a miscellaneous bin.

## Rules that outrank every section below

- **Every link resolves.** A link to a path that does not exist in this repository is a broken index, and a
  broken index is worse than no index because an agent will follow it and report the content as missing.
  Check every path against the tree before writing it.
- **Every note after the colon is derived from the linked document**, not from its filename. The note comes
  from the linked document's frontmatter `title` plus its first heading, or from its own summary line.
- **No number is generated.** Not a document count, not a version, not a coverage figure.
- **An exhaustive or negative claim is a claim about a search, not about a symbol.** This index never
  claims to be complete and never says a document does not exist: it lists what was found at a path, and
  the manifest carries the rest. If a note or a section heading would assert coverage ("all documentation
  for this project"), narrow it to what is linked or drop it. See `references/evidence.md`.
- The summary blockquote is the hardest line in this document to write honestly. It must come from the
  README's own first descriptive sentence or the package manifest's `description` field, quoted or closely
  paraphrased and cited in the sidecar. **If neither exists, do not compose one.** Emit
  `kind=human-input sev=blocker asks="What is this project, in one sentence?"` in the sidecar and write no
  file, because an index whose one-line summary is invented misdescribes the whole repository.

## `> summary blockquote`

**Evidence.** The `description` key of the package manifest, or the first non-heading, non-badge sentence
of the README.

**Write.** One or two sentences, quoted from that source. Cite the source in the sidecar's
`open_questions` when the two sources disagree, and prefer the manifest, because it is the one users see.

## `## Docs`

**Evidence.** The write plan's `evidence.index_rows`, which lists every manifest document that actually
exists at a path, with its title and audiences.

**Write.** One link per row: `- [Title](path): note`. Include only rows whose `found_at` is set. A document
the manifest wants and the repository does not have is not linked; it is a gap in the manifest, and the
manifest already tracks it.

**Absent.** No document in the manifest exists on disk:
`kind=not-implemented sev=blocker asks="This repository has no documentation to index yet. Backfill at
least one document before writing an index."`

## `## Reference`

**Evidence.** The same index rows, filtered to entries whose catalog `satisfies` list carries
`diataxis:reference`, plus any generated API description file such as an OpenAPI document.

**Write.** One link per file that exists, with a note naming what a reader finds there.

## `## Source`

**Evidence.** The entry points and the area list, if a codebase map exists in the manifest.

**Write.** Link the codebase map and the entry files by path. Do not restate the map here; two copies of an
area list drift within a month.

## `## Optional`

**Evidence.** Documents whose audience does not include `agents` or `engineering`, plus long-form material
a reader can skip.

**Write.** One link per file. The specification's meaning of this heading is "safe to skip when the context
window is short", so a file that is essential must not be here.

## Refuse to write

- If no manifest document exists on disk, there is nothing to index.
- If neither the package manifest nor the README yields a summary sentence, write no file. The summary is
  the one line every consumer reads.
- If cited claim blocks come out fewer than GAP markers, record `status: not-started` with the blockers
  and create no file.
