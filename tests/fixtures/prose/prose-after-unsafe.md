---
id: guide.runtime
title: Runtime guide
revision: 4
---

# Runtime guide

After 4 retries, the worker waits 30 seconds. [`src/runtime.py#stop`]

The limit appears in the deployment handbook. [ref: deployment handbook, verified 2026-08-19]

Use `docdna verify` to inspect [the registry](skill/catalog/claims.json).

Read <https://docs.example.test/verification> for the published guide.

[runtime-reference]: /docs/verification
[transport-reference]: ftp://docs.example.test/verification

GAP RUN-002 remains unresolved in `skill/scripts/docdna_verify.py`.

<!-- GAP id=RUN-002 kind=unverifiable sev=major owner=unassigned
     asks="Which service owns the retry limit?" -->
> **GAP RUN-002** (major): no owner is recorded.

| Item | Value | Owner |
| --- | --- | --- |
| Retry limit | 4 | Unknown |
| Command form | `docdna verify | prose` | Current |
| Literal separator | \| | Current |

```sh
python3 skill/scripts/docdna_verify.py --only prose
```
