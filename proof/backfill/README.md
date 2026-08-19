# Backfill proof bundle

## Raw evidence

- `tests/fixtures/documented_repo/docs/build/dev-setup.md`
- `skill/scripts/docdna_backfill.py`
- `tests/test_regression.py`
- `proof/replay/golden-workflows.json`, workflow `golden.backfill`

The golden fixture intentionally contains unsupported claims. Verification exits 1 and reports a
blocked verdict. That refusal is the saved outcome.

## Reproduce

```sh
python3 skill/scripts/docdna_backfill.py --json --verify docs/build/dev-setup.md tests/fixtures/documented_repo
python3 skill/scripts/docdna_proof.py --json
```

## Non-claims

- The replay does not write or plan a new document.
- A blocked fixture does not prove every unsupported claim can be detected.
- Repository evidence, human attestation, and self-attested run output remain distinct states.
