# API reference template

Catalog id `build.api-reference`. Default path `docs/build/api-reference.md`. Producible Y. GAP prefix
`API`.

Normative. This file is an instruction set, not prose to copy. **No sentence below may appear in the
document.** This is a reference, in the Diataxis sense: it is a complete list, ordered for lookup, with no
narrative. A reference that omits a route is worse than no reference, because a reader stops looking.

## Skeleton, in this order

1. The frontmatter block from the write plan's `frontmatter` object. See `_frontmatter.md`.
2. The reconstruction banner, verbatim from the write plan's `banner`. See `_banner.md`.
3. A single `#` heading.
4. One section per interface kind the write plan's `signal_evidence` proves is present, in this order:
   HTTP, GraphQL, gRPC, MCP tools, command line, library exports. Omit every kind with no evidence.
5. The document control block. See `_document-control.md`.

## Rules that outrank every section below

- Every table row carries a citation. A row is a claim about a thing that exists.
- **One row per registration site, and no row without one.** The list is built by reading the router, the
  parser, or the schema, never by reading an existing document. A route in the old document and not in
  the router is drift, and it belongs in the drift report, not in this document.
- **No number is generated.** Rate limits, page sizes, timeouts, maximum payload sizes, and retry counts
  come from the file that sets them or they are `human-input` GAPs. A default page size invented here
  becomes a client bug six months later.
- **Undocumented behaviour is not the same as absent behaviour.** If a handler's error path is not
  visible, emit an `unverifiable` GAP for that row rather than leaving the cell blank. A blank cell reads
  as "none".
- **An exhaustive or negative claim is a claim about a search, not about a symbol.** This whole document
  makes one: that the list is complete. Carry it with a `run` citation holding the command that enumerated
  the registration sites, for example
  ``[run: `grep -rnc "@router\." src/api/routes.py` -> 23 routes]``, or state in `## Not covered here`
  which files were read and that the list is complete for those files only. Never assert completeness from
  a `code` citation: it resolves one symbol in one file. See `references/evidence.md`.

## `## HTTP endpoints`

**Evidence.** The registration site: decorator, route table, router mount, or URL conf. For each route,
the handler function, the declared method, the request schema type, the response schema type, and any
auth or permission decorator on the same handler.

**Write.** One table row per route: method, path, handler, auth, and what it returns. Cite the row to the
handler symbol. Group by router mount, in mount order, because that is the order the code registers them
and it makes the table diffable against the router.

**Absent per cell.** Auth not visible on the handler:
`kind=unverifiable sev=major asks="Which endpoints require authentication? The handlers carry no
decorator that says."` Never write "public" into an auth cell that the code does not prove is public.
An endpoint wrongly documented as authenticated is a security finding created by documentation.

**Numbers.** Status codes are copied from the response construction in the handler and cited. Never list
a status code the handler cannot return.

## `## GraphQL operations`

**Evidence.** The schema definition file, the resolver map, and the directive set.

**Write.** One row per query, mutation, and subscription: name, arguments with their declared types, return
type, resolver symbol. Cite each to the schema or the resolver.

**Absent.** A field with no resolver in the tree:
`kind=not-implemented sev=major asks="Which service resolves <field>? Nothing in this repository does."`

## `## gRPC services`

**Evidence.** `.proto` service blocks only.

**Write.** One row per RPC: service, method, request message, response message, streaming mode. Cite each
to the proto service block by name.

**Numbers.** Field numbers are part of the wire contract. Copy them exactly from the proto or omit the
column.

## `## MCP tools`

**Evidence.** The tool registration call, its name, its input schema, and its description string where one
is declared in code.

**Write.** One row per registered tool: name, purpose taken from the declared description, and required
input fields taken from the schema. Cite each to the registration symbol.

**Absent.** A tool registered with no description:
`kind=human-input sev=minor asks="What does the <name> tool do? Its registration declares no
description."`

## `## Command line`

**Evidence.** The argument parser: every `add_argument`, `flag.String`, `clap` derive, `commander`
`.option`, or equivalent, plus the declared entry point that reaches it.

**Write.** One row per command and one nested row per flag: flag, type, default, and what it changes.
Cite each to the parser call. Copy the help string verbatim rather than paraphrasing it; a paraphrase is
a second source of truth that drifts.

**Numbers.** A default value is copied from the parser call and cited. Never state a default the parser
does not set.

**Absent.** A flag whose effect is not visible from its parse site:
`kind=unverifiable sev=minor asks="What does <flag> change? It is parsed but its effect is not traceable
from the parse site."`

## `## Library exports`

**Evidence.** The declared public surface: `__all__`, the `exports` map of `package.json`, the `pub`
items of the crate root, the exported identifiers of the package index module.

**Write.** One row per exported symbol: name, kind, signature copied from the declaration, and stability
if a decorator or a comment declares it. Cite each to the declaration.

**Never.** Do not document an internal symbol as public because it is reachable. Reachable and public are
different claims, and conflating them creates a compatibility obligation nobody accepted.

## `## Not covered here`

**Evidence.** The write plan's `covers` list against the interface signals present.

**Write.** One bullet per interface kind that exists in the code and is not in this document, with the
reason. An honest gap list is what stops a reader treating a partial reference as complete.

## Refuse to write

- If no interface signal is present, this repository exposes no API. Say so in the report and write no
  file. A reference for an interface that does not exist is regime cosplay.
- If the only interface is a single entry point with no flags, the development setup document already
  covers it.
- If cited claim blocks come out fewer than GAP markers, record `status: not-started` with the blockers
  and create no file.
