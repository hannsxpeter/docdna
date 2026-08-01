# API contract template

Catalog id `design.api-contract`. Default path `docs/design/api-contract.md`. Producible Y. GAP prefix
`APC`.

Normative. This file is an instruction set, not prose to copy. **No sentence below may appear in the
document.** This document is about the contract, not about the endpoints. The endpoint list belongs to
`build.api-reference`; duplicating it here creates two lists that disagree within a quarter.

## Skeleton, in this order

1. The frontmatter block from the write plan's `frontmatter` object. See `_frontmatter.md`.
2. The reconstruction banner, verbatim from the write plan's `banner`. See `_banner.md`.
3. A single `#` heading.
4. The sections below, in order.
5. The document control block. See `_document-control.md`.

## Rules that outrank every section below

- Every claim block carries a citation or a GAP marker.
- **Never synthesize the contract artifact.** If this repository has no OpenAPI document, no proto, and no
  SDL, docdna does not write one. A generated specification looks authoritative, gets committed, gets
  imported into a client generator, and ships wrong types to a consumer. The absence is the finding.
- **No number is generated.** Version numbers, deprecation windows, support horizons, rate limits, and
  payload size caps come from a committed file or they are `human-input` GAPs.
- The gap between what the contract describes and what the code registers is the reason this document
  exists. Compute it, do not smooth it.
- **An exhaustive or negative claim is a claim about a search, not about a symbol.** "The contract covers
  every registered operation" and "no operation is missing" are carried by a `run` citation holding the
  command and its output, or they are narrowed to the named set actually inspected, or they are an
  `unverifiable` GAP. A `code` citation resolves one symbol in one file and cannot support either shape.
  See `references/evidence.md`.

## `## Contract of record`

**Evidence.** The contract artifacts in the tree: `openapi.yaml`, `openapi.json`, `schema.graphql`,
`*.proto`, `asyncapi.yaml`, and any build step that generates or validates one.

**Write.** One cited sentence naming which artifact is authoritative and how it stays that way: written by
hand, generated from code at build time, or generated from the artifact into code. Cite the generation or
validation step, because that step is the only thing that makes the claim true.

**Absent.** No contract artifact exists and the code exposes a network interface:
`kind=not-implemented sev=blocker asks="Where is the interface contract for this service? Consumers
currently have to read the router."` This is a product finding. Report it and do not fill the hole.

## `## Coverage`

**Evidence.** The registered routes or RPCs from the code, and the operations described in the contract
artifact. Compare the two sets by path and method.

**Write.** Three bullets, each cited on both sides: operations in both, operations in the code and not in
the contract, operations in the contract and not in the code. Name the operations. A count without names
is not actionable, and a count is a number, so it comes with a `run` citation or not at all.

A set difference is only as complete as the two lists behind it, and "these are all the routes the code
registers" is a negative universal that no `code` citation reaches. Carry each side with the `run`
citation that produced it, for example
``[run: `jq -r '.paths | keys[]' openapi.yaml | wc -l` -> 18 paths]`` beside the equivalent search over
the router. If you cannot run both, say which files each list came from and label the comparison as
covering those files only, or emit
`kind=unverifiable sev=major asks="Is this comparison complete on both sides? Neither the contract nor the
router was enumerated by a command."`

**Absent.** No contract artifact to compare against: omit this section rather than inventing a baseline.

## `## Versioning`

**Evidence.** The version field of the contract artifact, the version segment of route paths, a version
header read in middleware, and the package version if the contract ships as a package.

**Write.** One cited sentence per mechanism that exists. State which one clients actually select with, and
cite the code that reads it.

**Absent.** No version mechanism anywhere:
`kind=human-input sev=major asks="How will a breaking change to this interface be released? Nothing in the
repository versions it."`

## `## Compatibility commitments`

**Evidence.** Only a committed statement: a deprecation policy file, a support matrix, a
`Deprecation` header set in code, a proto `reserved` field, a `@deprecated` marker.

**Write.** One row per commitment with its citation. A `reserved` range in a proto is a real, checkable
commitment and belongs here.

**Absent.** Always, unless a committed file states it:
`kind=human-input sev=blocker asks="How long is a released version of this interface supported after a
new one ships?"` A support window is a number and a commercial commitment, and it is never derived.

## `## Error model`

**Evidence.** The error response construction sites, the error schema in the contract artifact, and the
exception-to-status mapping in middleware.

**Write.** One row per error shape: status or code, body shape, and where it is produced. Cite each to the
construction site. If the contract declares an error schema the code does not produce, that mismatch is a
row of its own.

**Absent.** Errors are constructed ad hoc at each handler:
`kind=not-implemented sev=major asks="Is there a single error shape for this interface, or does each
handler define its own?"`

## `## Authentication and authorization at the boundary`

**Evidence.** Middleware registration order, security schemes declared in the contract artifact, and
per-operation security requirements.

**Write.** One cited sentence naming the scheme, then one row per operation group with its requirement.
Where the contract declares a scheme the code does not enforce, that is a security finding and it goes in
its own row with both citations.

**Never.** Do not describe an endpoint as public or protected without a citation on that specific
endpoint. This is the cell where a wrong answer costs the most.

## `## What this contract does not cover`

**Evidence.** Interfaces present in the code and absent from the contract artifact: webhooks outbound,
message queue topics, scheduled jobs, and admin routes mounted separately.

**Write.** One bullet per uncovered surface, cited to its registration site.

## Refuse to write

- If no HTTP, gRPC, or GraphQL signal is present, this repository exposes no interface and owes no
  contract document.
- If the only interface is internal to the process, say so and write no file.
- If cited claim blocks come out fewer than GAP markers, record `status: not-started` with the blockers
  and create no file.
