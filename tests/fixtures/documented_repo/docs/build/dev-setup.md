---
id: build.dev-setup
instance_id: null
title: Development setup
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
  - pyproject.toml
covers_digest: sha256:4da7e7087f5970257f48d35c7dfb3736b2406e58d5cdab0c503a4542ab56caea
drift_budget: 3
applies_to: null
satisfies: [diataxis:how-to]
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

# Development setup

The project is packaged with a PEP 621 table and requires Python 3.9 or newer
[`pyproject.toml#requires-python`].

## Dependencies

- Two runtime dependencies are declared, a web framework and a PostgreSQL driver
  [`pyproject.toml#dependencies`].
- One console script is declared, named after the project [`pyproject.toml#orderbook`].
- Tests are collected from a single directory [`pyproject.toml#testpaths`].

## Running the service

The application object is constructed at module import and served directly when the module is
run as a script [`src/api/routes.py#app`].

<!-- GAP id=DEV-001 kind=human-input sev=major owner=unassigned doc=build.dev-setup
     asks="Which PostgreSQL version should a new contributor run locally?" -->
> **GAP DEV-001** (major): no PostgreSQL version is pinned in the packaging metadata, in a
> compose file, or in CI. This is a decision, not a fact, and it must be made by a person.

## Document control

| | |
| --- | --- |
| Status | draft |
| Owner | unassigned (candidate: @platform-team, from CODEOWNERS, unconfirmed) |
| Last reviewed | 2026-07-31 by docdna v0.2.0 |
| Review cadence | on change to the files listed below |
| Next review | when `pyproject.toml` changes |
| Derived from | `pyproject.toml` |
| Open questions | 1, listed inline as a GAP marker |

This document was derived from the repository. It has not been reviewed by a person.
To adopt it, set `status: active` and name an `owner` in the frontmatter.
