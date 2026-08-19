# Check proof bundle

## Raw evidence

- `tests/fixtures/documented_repo`
- `skill/scripts/docdna_check.py`
- `tests/test_check.py`
- `tests/test_drift.py`
- `proof/replay/golden-workflows.json`, workflow `golden.check`

The check replay uses `--no-write` and `--fail-on never`. It confirms the committed fixture remains
inspectable while leaving its gated policy outside the replay outcome.

## Reproduce

```sh
python3 skill/scripts/docdna_check.py --json --no-write --fail-on never tests/fixtures/documented_repo
python3 skill/scripts/docdna_proof.py --json
```

## Non-claims

- The replay does not certify the fixture documents.
- It does not turn human attestation or self-attested run output into verified evidence.
- The recorded command-reference adjudication does not apply to unrelated checker passes.
