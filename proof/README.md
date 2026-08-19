# DocDNA proof bundles

Implements: P-MUST-02

These bundles connect product claims to committed evidence. The registry in
`skill/catalog/proofs.json` is authoritative. A bundle is a route to raw evidence and an exact
reproduction command, not a hand-edited transcript.

Run the complete registry and golden workflow check:

```sh
python3 skill/scripts/docdna_proof.py
python3 skill/scripts/docdna_proof.py --json
```

From a source checkout, the command reads project files and runs only the bounded, read-only commands
declared in `proof/replay/golden-workflows.json`. It does not write to the repository under inspection.
An installed skill reports its narrower `installed-registry` mode and skips checkout-only path and replay
checks.

## Bundles

- `survey/README.md` covers repository survey evidence.
- `backfill/README.md` covers backfill verification evidence.
- `check/README.md` covers checker evidence.
- `runtime/README.md` covers the local runtime and host boundary.
- `replay/golden-workflows.json` records stable expected outcomes for all four modes.
- `replay/expected-proof-output.json` and `expected-proof-output.txt` pin cross-version output.

No bundle claims host parity, external service behavior, certification, or correctness beyond the
named evidence boundary.
