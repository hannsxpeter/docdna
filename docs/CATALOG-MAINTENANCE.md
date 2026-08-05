# Catalog reference maintenance

## Owner

Assign the dated regulatory reference files in `skill/references/regime-facts/` to the maintainer of record, @hannsxpeter. Require that owner to verify each retained fact against the linked primary source.

## Cadence

Re-verify every file quarterly. Update its top-level `verified: YYYY-MM-DD` line only after checking every retained claim. Delete unsupported claims or move them under `Unverified, do not rely on`.

## Aging

Compare the `verified` date with the current date. Treat the file as aged once three months have passed. Confirm aged facts before relying on them.

Delete a file that no owner will maintain. An unmaintained dated file is worse than none: it asserts current legal fact with confidence while it is stale.
