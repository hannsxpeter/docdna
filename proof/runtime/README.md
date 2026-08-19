# Runtime proof bundle

## Raw evidence

- `skill/scripts/docdna_proof.py`
- `skill/catalog/proofs.json`
- `tests/test_proofs.py`
- `proof/replay/golden-workflows.json`, workflow `golden.runtime`

The local runtime check confirms that the registry and workflow fixture exist and declare schema 1.
The proof command then validates every claim, evidence path, promotion requirement, and replay
outcome.

The installed skill contains the registry and proof command, but not this top-level bundle or the test
fixtures. There the command reports `installed-registry`, validates the closed schema and normative
promotion mapping, and skips checkout-only evidence paths and golden replay with an explicit boundary.

## Reproduce

```sh
python3 -m unittest tests.test_proofs
python3 skill/scripts/docdna_proof.py
python3 skill/scripts/docdna_proof.py --json
```

## Host capture procedure

Run the two proof commands from an isolated installed skill, record the host name and skill path,
and preserve unedited stdout, stderr, exit status, Python version, and the installed file inventory.
Register that artifact with evidence kind `host-capture` before promoting any claim to
`host-captured`.

## External dependencies

Golden replays call the shipped Python commands with the current Python interpreter. Survey and
checker behavior can also depend on repository and POSIX filesystem semantics. Such a dependency
is labeled `external-tool-dependent` until separate evidence names and captures it.

## Non-claims

- `host-capture-ready` means a procedure exists. It does not mean a host run occurred.
- No current registry claim is `host-captured` or `install-tested`.
- Local replay does not prove parity across Claude Code, Codex, Cursor, or Windsurf.
