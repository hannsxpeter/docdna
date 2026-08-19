# Product claim proofs

<!-- Implements: P-MUST-02 -->

`proofs.json` is the machine-readable registry for claims DocDNA makes about itself. It does not turn a
claim into a binary promise. It records what kind of evidence exists, where that evidence can be
inspected, and the boundary beyond which the evidence says nothing.

## Compatibility

Schema 1 requires the exact evidence-level vocabulary and promotion requirements defined in
`SCHEMA.md`. The mapping compiled into `docdna_proof.py` is normative; `proofs.json` must match it rather
than redefining it. Claim ids are stable, lowercase, dot-separated join keys. Consumers may add display fields
only after a schema change. They must not infer a stronger level from the order of the vocabulary because
the levels are evidence types, not a maturity ladder.

A producer may add a claim without breaking schema 1. Renaming or removing a claim id, changing the
meaning of an evidence level, changing an evidence kind, or changing the golden workflow shape requires
a schema review. Claim order remains lexical by id so text and JSON output stay stable.

## Reading a level

- `shipped` says code is present.
- `unit-tested` and `install-tested` say which execution boundary a test crossed.
- `artifact-proven` says the saved artifact is inspectable.
- `replay-tested` says selected saved outcomes were reproduced.
- `measured` and `adjudicated` require a named corpus, boundary, and limitations.
- `host-capture-ready` says a procedure exists. It is not a host result.
- `host-captured` requires an actual inspectable capture.
- `external-tool-dependent` marks a dependency that local proof does not settle.

Levels do not inherit from one another. For example, `unit-tested` does not imply `install-tested`, and
`host-capture-ready` does not imply `host-captured`. The registry currently makes no `install-tested` or
`host-captured` claim.

## Inspect and reproduce

```sh
python3 skill/scripts/docdna_proof.py
python3 skill/scripts/docdna_proof.py --json
```

Both forms validate the same registry and replay the same four golden workflows. Text is for inspection;
JSON is the stable machine contract. Exit 0 means registry and replay success. Exit 1 means a valid golden
workflow no longer matches its saved outcome. Exit 2 means the registry, evidence, or workflow declaration
is invalid.

The complete expected text and JSON live in `proof/replay/expected-proof-output.txt` and
`proof/replay/expected-proof-output.json`. Both Python versions in CI compare live output byte for byte
with those fixtures.

Proof bundles live under `proof/`. Each bundle names raw evidence, exact reproduction commands, and
explicit non-claims. The bundle text never substitutes for the referenced test, fixture, implementation,
measurement, adjudication, or host capture.

An installed skill carries the registry and proof command but not the source checkout's proof bundles or
test fixtures. The command detects that layout, reports `installed-registry`, validates the schema and
promotion contract, and explicitly skips checkout-only evidence paths and replay. It never presents that
portable check as a host capture, installation test, or golden replay.
