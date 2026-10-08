# Plan

## Goal
Bring docdna back into a clean, consistent state after 1.4.0: fix the verified correctness and security
bugs from a fresh review, remove duplication that has already drifted into bugs, and make every document,
sample, and repository setting agree with the code.

## Requirements
- R1: Check never passes a document-controlled value to `git` as an option. Done when: a frontmatter
  `last_validated_commit: --output=<path>` creates no file, under test.
- R2: A document stamped by Backfill is not reported drift-stale by Check. Done when: an end-to-end test
  stamps with Backfill's digest and Check reports it current.
- R3: Scan parses real-world manifests correctly. Done when: tests cover non-object OpenAPI JSON,
  non-ASCII paths in git history, TOML comments, `]` and commas inside quoted TOML strings, and
  `optional-dependencies` tables.
- R4: The installer never destroys the last working install. Done when: a failing copy leaves the previous
  install intact, under a test or CI probe.
- R5: Documentation matches the code. Done when: every count, flag, path, version, and name the drift audit
  flagged is corrected, no `P-MUST` markers remain, and the sample test passes.
- R6: Repository metadata matches the product. Done when: the GitHub description and topics describe what
  the README claims, without overclaiming.

## Non-goals
- Signed releases and authenticated installed bytes (the two remaining Medium risks). They need a release
  process change and stay tracked in STATE.md.
- New features or catalog changes.

## Design
- Shared helpers live in `skill/scripts/docdna_fs.py`; the Check and Backfill claim engine lives in one
  module so the two cannot drift again.
- Output bytes for committed fixtures stay unchanged except where a listed bug fix requires a change.

## Slices
- [x] 1. Scan, select, fs, llms fixes and consolidation: full suite plus new regression tests
- [x] 2. Check, backfill, prose, unicode fixes and claim-engine consolidation: full suite plus dogfood gate
- [x] 3. Installer staging and rollback, CI cleanup: shellcheck plus installer failure probe
- [x] 4. Documentation drift, naming, and P-MUST marker removal: sample test and link check
- [x] 5. CHANGELOG, GitHub description and topics, merge to main, push

## Open questions
- none
