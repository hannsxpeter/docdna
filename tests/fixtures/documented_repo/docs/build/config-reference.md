---
id: build.config-reference
instance_id: null
title: Configuration reference
stage: build
durability: durable
scope: repo
system_of_record: repo
classification: unclassified
status: draft
owner: unassigned
owner_candidate: "@platform-team (from CODEOWNERS, unconfirmed)"
reviewed_by: null
last_reviewed: 2026-07-31
review_cadence: on-change
next_review: null
retention: indefinite
valid_until: null
supersedes: []
superseded_by: null
not_applicable_reason: null
covers:
  - src/config/settings.py
covers_digest: sha256:ae38606f972c3540690cce7eb2ab1a20197a74f47b466cccc35d8f9cafbe2dcc
drift_budget: 3
applies_to: null
satisfies: [diataxis:reference]
audiences: [engineering]
traces_up: []
traces_down: []
derivation: derived
confidence: high
generated_by: docdna v0.2.0
generated_on: 2026-07-31
content_hash: null
open_questions: []
---

> Backfilled by docdna v0.2.0 from repository evidence at commit 0000000 on 2026-07-31.
> Claims are cited to files and symbols. Unknowns are tracked as GAP markers, not filled in.
> This is derived, not authoritative. Schedule a human review before relying on it.

# Configuration reference

Every setting is read from the process environment when the module is imported, so a missing
required variable fails at start rather than at first request [`src/config/settings.py#DATABASE_URL`].

## Variables

| Variable | Required | Default |
| --- | --- | --- |
| `DATABASE_URL` | yes | none, read with a bare subscript [`src/config/settings.py#DATABASE_URL`] |
| `REDIS_URL` | no | a localhost URL [`src/config/settings.py#REDIS_URL`] |
| `LOG_LEVEL` | no | `INFO` [`src/config/settings.py#LOG_LEVEL`] |
| `REQUEST_TIMEOUT_SECONDS` | no | parsed as an integer [`src/config/settings.py#REQUEST_TIMEOUT_SECONDS`] |
| `FEATURE_PARTIAL_REFUNDS` | no | off unless set to `1` [`src/config/settings.py#FEATURE_PARTIAL_REFUNDS`] |
| `ALLOWED_ORIGINS` | no | an empty list [`src/config/settings.py#ALLOWED_ORIGINS`] |

## Notes

- Only `DATABASE_URL` is read without a fallback, so it is the one variable that stops the
  process from starting [`src/config/settings.py#DATABASE_URL`].
- `ALLOWED_ORIGINS` is split on commas, so an empty value yields a single empty entry rather
  than an empty list [`src/config/settings.py#ALLOWED_ORIGINS`].

## Document control

| | |
| --- | --- |
| Status | draft |
| Owner | unassigned (candidate: @platform-team, from CODEOWNERS, unconfirmed) |
| Last reviewed | 2026-07-31 by docdna v0.2.0 |
| Review cadence | on change to the files listed below |
| Next review | when `src/config/settings.py` changes |
| Derived from | `src/config/settings.py` |
| Open questions | 0 |

This document was derived from the repository. It has not been reviewed by a person.
To adopt it, set `status: active` and name an `owner` in the frontmatter.
