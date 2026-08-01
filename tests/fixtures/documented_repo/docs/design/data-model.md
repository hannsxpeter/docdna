---
id: design.data-model
instance_id: null
title: Data model
stage: design
durability: durable
scope: repo
system_of_record: repo
classification: unclassified
status: draft
owner: unassigned
owner_candidate: "@platform-team (from CODEOWNERS, unconfirmed)"
reviewed_by: null
last_reviewed: 2026-05-04
review_cadence: on-change
next_review: null
retention: indefinite
valid_until: null
supersedes: []
superseded_by: null
not_applicable_reason: null
covers:
  - schema/orders.sql
covers_digest: sha256:f434e944e29bb6fb6872dc72be58f5a8f5bc7462cb7f11d9a5533ee3b5d5e357
applies_to: null
satisfies: [diataxis:explanation]
audiences: [engineering]
traces_up: []
traces_down: []
derivation: derived
confidence: high
generated_by: docdna v0.2.0
generated_on: 2026-05-04
content_hash: null
open_questions: []
---

> Backfilled by docdna v0.2.0 from repository evidence at commit 0000000 on 2026-05-04.
> Claims are cited to files and symbols. Unknowns are tracked as GAP markers, not filled in.
> This is derived, not authoritative. Schedule a human review before relying on it.

# Data model

Three tables are declared, all keyed on a UUID primary key
[`schema/orders.sql#customer`].

## Tables

| Table | Key | Notes |
| --- | --- | --- |
| `customer` | `id` | Email is unique [`schema/orders.sql#email`] |
| `orders` | `id` | References the customer [`schema/orders.sql#customer_id`] |
| `refund` | `id` | References the order [`schema/orders.sql#order_id`] |

## Money

Amounts are stored in minor units as a signed 64-bit integer, on the order and on the refund
[`schema/orders.sql#total_minor`], [`schema/orders.sql#amount_minor`].

Currency is a fixed three-character column on the order and is absent from the refund, so a
refund inherits the currency of its order [`schema/orders.sql#currency`].

## Document control

| | |
| --- | --- |
| Status | draft |
| Owner | unassigned (candidate: @platform-team, from CODEOWNERS, unconfirmed) |
| Last reviewed | 2026-05-04 by docdna v0.2.0 |
| Review cadence | on change to the files listed below |
| Next review | when `schema/orders.sql` changes |
| Derived from | `schema/orders.sql` |
| Open questions | 0 |

This document was derived from the repository. It has not been reviewed by a person.
To adopt it, set `status: active` and name an `owner` in the frontmatter.
