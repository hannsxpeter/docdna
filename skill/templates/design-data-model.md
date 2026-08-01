# Data model and dictionary template

Catalog id `design.data-model`. Default path `docs/design/data-model.md`. Producible Y. GAP prefix `DM`.

Normative. This file is an instruction set, not prose to copy. **No sentence below may appear in the
document.** The shape of the data is derivable and the meaning of the data is not, and this document must
keep those two apart on every row.

## Skeleton, in this order

1. The frontmatter block from the write plan's `frontmatter` object. See `_frontmatter.md`.
2. The reconstruction banner, verbatim from the write plan's `banner`. See `_banner.md`.
3. A single `#` heading.
4. The sections below, in order.
5. The document control block. See `_document-control.md`.

## Rules that outrank every section below

- Every table row carries a citation to the declaration: a model class, a migration statement, a schema
  block, or a DDL statement.
- **Shape is evidence, meaning is not.** Column name, type, nullability, default, and index are read from
  the declaration. What a column is for, what its values mean, and which are valid in combination are read
  from a docstring, a comment, a check constraint, or an enum, or they are `unverifiable` GAPs.
- **No number is generated.** Row counts, growth rates, retention periods, size limits, and archival
  windows come from a committed file or they are `human-input` GAPs. A retention period is a legal
  commitment and it never comes from a model file.
- **Personal data is marked, never assessed.** Mark a field as holding personal data when the declaration
  or a comment says so. Do not decide whether a category is sensitive, whether a lawful basis exists, or
  whether a regime applies. Those are the refused documents, and they belong to a person.
- **An exhaustive or negative claim is a claim about a search, not about a symbol.** "These are every
  entity", "no field holds personal data", and "every relationship is enforced by a foreign key" are
  carried by a `run` citation holding the command and its output, or they are narrowed to the named set
  actually inspected, or they are an `unverifiable` GAP. A `code` citation resolves one symbol in one file
  and cannot support either shape. "No field is marked as personal data" is the highest-cost instance of
  this in the catalog: write it only as an observation about the files in `covers`, never about the
  repository. See `references/evidence.md`.

## `## Entities`

**Evidence.** Model classes, schema blocks, `CREATE TABLE` statements, and generated schema snapshots.
Prefer the declaration the application actually reads over a snapshot, and say which you used.

**Write.** One table row per entity: name, physical table or collection, the declaring file, and what it
represents. The last column is filled only from a docstring or a comment on the declaration.

**Absent.** No docstring or comment on an entity:
`kind=unverifiable sev=minor asks="What real thing does <entity> represent? Its declaration carries no
comment."` Do not answer this from the entity's name. "The User entity represents a user" is a tautology
wearing a table row.

## `## Fields`

**Evidence.** The field declarations of each entity: type, nullability, default, uniqueness, index, and
foreign key.

**Write.** One subsection per entity, one table row per field, columns: field, type, null, default, meaning.
Cite each row to the field declaration. Copy the type as declared, including the length or precision, and
do not normalize it into a generic type name.

**Numbers.** A column length, a precision, or a numeric default is a character-for-character copy of the
declaration. Never round `varchar(255)` to "a string".

**Absent per cell.** Meaning not stated anywhere:
`kind=unverifiable sev=minor asks="What does <entity>.<field> hold, and which values are valid?"`

## `## Relationships`

**Evidence.** Foreign key declarations, relation attributes in the ORM, and join tables. A shared column
name is not a relationship.

**Write.** One bullet per relationship: the two entities, the cardinality as the declaration states it, the
on-delete behaviour if declared, and the citation. Cardinality that the declaration does not state is a
GAP; do not infer it from a plural attribute name.

**Absent.** Relationships enforced only in application code:
`kind=unverifiable sev=major asks="Which of these relationships are enforced by the database and which
only by application code?"`

## `## Enumerations and constrained values`

**Evidence.** Enum types, check constraints, and validator declarations.

**Write.** One row per enumerated field with its full value set, copied exactly and cited. This is the
highest-value section for a reader debugging a data question, and it is fully derivable.

## `## Migrations`

**Evidence.** The migration directory and its committed history.

**Write.** State which tool owns the schema, cited to its configuration. State how the current schema is
produced from the history, cited. A count of migrations is a `run` citation carrying its command, for
example ``[run: `ls migrations/versions | wc -l` -> 41 files]``, or it is omitted.

**Absent.** Schema changes are applied by hand with no migration tool:
`kind=not-implemented sev=blocker asks="How does a schema change reach a running environment? Nothing in
the repository manages migrations."`

## `## Fields the code treats as personal data`

**Evidence.** Field names that a corroborated signal marked, plus any comment, decorator, or annotation
that marks a field.

**Write.** One row per marked field: entity, field, and the marking evidence. Nothing else. No category
judgment, no lawful basis, no retention.

**Absent.** Fields look personal and nothing marks them:
`kind=human-input sev=blocker asks="Which of these fields hold personal data, and who decided? The code
does not say."` Then stop. Classification, retention, and impact assessment are documents docdna refuses
to write for exactly this reason.

## Refuse to write

- If no schema signal is present, there is no data model to document.
- If the only schema artifact is a generated snapshot with no declaring source, say so and write no file:
  a snapshot documents a state, not a model.
- If cited claim blocks come out fewer than GAP markers, record `status: not-started` with the blockers
  and create no file.
