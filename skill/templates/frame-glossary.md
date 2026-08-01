# Glossary template

Catalog id `frame.glossary`. Default path `docs/frame/glossary.md`. Producible Y. GAP prefix `GLO`.

Normative. This file is an instruction set, not prose to copy. **No sentence below may appear in the
document.** A glossary is the easiest document to fake and the easiest fake to detect: the tell is a
definition that restates the term.

## Skeleton, in this order

1. The frontmatter block from the write plan's `frontmatter` object. See `_frontmatter.md`.
2. The reconstruction banner, verbatim from the write plan's `banner`. See `_banner.md`.
3. A single `#` heading.
4. The sections below, in order.
5. The document control block. See `_document-control.md`.

## Rules that outrank every section below

- Every table row carries a citation to where the term is defined in the repository, not to where it is
  used.
- **A definition may not restate the term.** "A Tenant is a tenant of the system" and "The Ingest Service
  ingests data" are the canonical failures. A definition names the thing in words that do not appear in
  the term, or it is a GAP.
- **The source of a definition is a docstring, a comment, an enum value set, a schema description, a type
  declaration, or a constant's value.** A term's own identifier is never its definition.
- **No number is generated.** Term counts, thresholds inside a definition, and limits come from the code
  that sets them, cited, or they are `human-input` GAPs.
- Include a term only if the code uses it as a domain concept. A framework class name is not a domain
  term, and a glossary padded with framework vocabulary buries the words a newcomer actually needs.
- **An exhaustive or negative claim is a claim about a search, not about a symbol.** "No collisions were
  found" and "the repository never expands this abbreviation" are carried by a `run` citation holding the
  command and its output, or they are narrowed to the named set actually inspected, or they are an
  `unverifiable` GAP. A `code` citation resolves one symbol in one file and cannot support either shape.
  See `references/evidence.md`.

## `## Terms`

**Evidence.** Domain-shaped identifiers: entity and model names, enum type names, state machine state
names, event and message type names, error class names, and directory names inside a domain package. For
each, the docstring, comment, or schema description attached to its declaration.

**Write.** One table row per term, columns: term, definition, where it is defined. Sort alphabetically.
Cite each row to the declaration that carries the definition.

**Absent.** The term is a real domain concept and nothing defines it:
`kind=human-input sev=major asks="What does <term> mean in this product? The code names it but never
defines it."` Emit the GAP and leave the definition cell empty. An empty cell with a GAP is a working
document; a filled cell with a guess is a wrong document that nobody will re-check.

## `## Terms the code uses in two ways`

**Evidence.** One identifier declared in more than one module with materially different shape: two
different `Account` classes, an `Order` in the API layer and an `Order` in the warehouse export, a status
enum whose value sets differ between two services.

**Write.** One row per collision: the term, each meaning, and a citation for each. State that both are
live. This is the section a reader remembers, and it is fully derivable.

**Absent.** "No collisions were found" is a claim about a search, so it is written as one. Carry the
search as a `run` citation, for example
``[run: `grep -rhn "^class \|^type \|^enum " src/ | awk '{print $2}' | sort | uniq -d` -> no output]``,
and name the modules the search covered. If the search is not runnable here, narrow the sentence to the
terms in the table above ("no two of the thirty-one terms listed above are declared twice with different
shape") or emit
`kind=unverifiable sev=minor asks="Is any domain term declared twice with different meaning? The tree was
not searched exhaustively."` The sentence is worth its line only when it names the search behind it.

## `## Terms in the code and not in the product`

**Evidence.** Identifiers whose declaration carries a deprecation marker, a rename comment, or a
compatibility shim mapping an old name to a new one.

**Write.** One row per stale term: the term, what replaced it, and the citation for the mapping. A reader
meeting an old name in a log line needs exactly this row.

## `## Abbreviations`

**Evidence.** Short identifiers whose expansion appears verbatim in the repository: a comment, a constant
name, a README line, an environment variable that spells it out.

**Write.** One row per abbreviation with its expansion and citation.

**Absent.** The abbreviation is used and no expansion was found:
`kind=human-input sev=minor asks="What does <abbreviation> stand for? A search of the tree found no
expansion."` The GAP is the right home for this, because "the repository never expands it" is a negative
universal and a GAP is not a claim. Never expand an abbreviation from general knowledge. A wrong expansion propagates into every document a
reader writes afterwards.

## `## Terms deliberately not defined here`

**Evidence.** Vocabulary owned elsewhere: a standard's terms, a framework's terms, a partner system's
terms.

**Write.** One bullet per source with a pointer to where its vocabulary is defined, cited to the
dependency declaration that brings it in.

## Refuse to write

- If fewer than five terms have a definition source in the repository, a glossary is premature. Report the
  terms found and write no file.
- If cited claim blocks come out fewer than GAP markers, record `status: not-started` with the blockers
  and create no file. A glossary that is mostly GAP markers is a vocabulary interview, and it should be
  run as one.
