---
id: guide.runtime
title: Runtime guide
revision: 3
---

# Runtime guide

After 3 retries, the worker waits 20 seconds. [`src/runtime.py#start`]

The limit appears in the operator handbook. [ref: operator handbook, verified 2026-08-19]

Use `docdna check` to inspect [the registry](skill/catalog/proofs.json).

Read <https://docs.example.test/runtime> for the published guide.

[runtime-reference]: /docs/runtime
[transport-reference]: ftp://docs.example.test/runtime

GAP RUN-001 remains unresolved in `skill/scripts/docdna_check.py`.

<!-- GAP id=RUN-001 kind=unverifiable sev=major owner=unassigned
     asks="Which service owns the retry limit?" -->
> **GAP RUN-001** (major): no owner is recorded.

| Item | Value |
| --- | --- |
| Retry limit | 3 |
| Command form | `docdna check | prose` |
| Literal separator | \| |

```sh
python3 skill/scripts/docdna_check.py --only prose
```
