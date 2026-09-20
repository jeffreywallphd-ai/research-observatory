# CAP-04.S01.T03 — predecessor lookup correction

Candidate `8c314560e2d5fafb1d89716181a3475e3de21908` passed 48 fresh focused
schema/migration/constraint and packaging-contract tests in 29.784 seconds,
product mypy over three affected files, and the architecture check. HEAD and
source stayed fixed during those checks. This is bounded storage evidence,
not completed task, native principal, full packaging or Wave qualification.

Independent review nevertheless identified a missing exact-record index for
the new predecessor-member binding trigger: the query plan scanned all included
members of a predecessor for every changed-file comparison. Root cause was
adding a per-row relational guard without checking its large-manifest lookup
shape. This would be quadratic in the worst case.

Added acceptance row: exact prior-record lookup must use all three keys
(project, manifest, source-record revision), not a residual manifest scan.
The new query-plan regression first failed with the existing DOI index, then
passed with the partial included-member composite index. All six relational
tests passed in 0.012 seconds; this exploratory result is not final-candidate
qualification. Only the new v13 fingerprint/profile pins change. No historical
schema, fixture, approval or performance threshold is rewritten.

Selected successor checks: new constraint regression, exact v12 migration and
SQLCipher backup/rollback, current profile/schema, affected format/lint/type and
architecture. Prior-v1-through-v11 chain behavior was checked at 8c314560; the
additive index does not modify those revision implementations. Full task and
slice runtime qualification remains pending.
