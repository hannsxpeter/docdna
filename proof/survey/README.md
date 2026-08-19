# Survey proof bundle

## Raw evidence

- `tests/fixtures/internal_service`
- `skill/scripts/docdna_scan.py`
- `tests/test_scan.py`
- `proof/replay/golden-workflows.json`, workflow `golden.survey`

The measured corpus for the registered fixture claim is the committed
`tests/fixtures/internal_service` tree. The replay checks three inventory documents and two drift
observations. It omits timestamps, commit ids, absolute paths, and other volatile fields.

## Reproduce

```sh
python3 skill/scripts/docdna_scan.py --json tests/fixtures/internal_service
python3 skill/scripts/docdna_proof.py --json
```

## Non-claims

- This bundle does not measure every repository archetype.
- It does not prove results on a different filesystem or host.
- A saved fixture outcome is not a claim that every emitted observation is correct.
