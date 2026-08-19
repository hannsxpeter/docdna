---
id: guide.runtime
title: Runtime guide
revision: 3
---

# Runtime guide

The worker starts after 3 retries and waits 20 seconds. [`src/runtime.py#start`]

The operator handbook records the limit. [ref: operator handbook, verified 2026-08-19]

Run `docdna check` to read [the registry](skill/catalog/proofs.json).

Open <https://docs.example.test/runtime> for the published guide.

[runtime-reference]: /docs/runtime
[transport-reference]: ftp://docs.example.test/runtime

The unresolved record is GAP RUN-001 in `skill/scripts/docdna_check.py`.

<!-- GAP id=RUN-001 kind=unverifiable sev=major owner=unassigned
     asks="Which service owns the retry limit?" -->
> **GAP RUN-001** (major): the owner is not recorded.

| Item | Value |
| --- | --- |
| Retry limit | 3 |
| Command form | `docdna check | prose` |
| Literal separator | \| |

```sh
python3 skill/scripts/docdna_check.py --only prose
```
