# CAP-04.S01.T02 — complete-draft summary adapter

Increment from approved `b879150b1f0c6d618cbf835b5773a42b0eddeb5d`.
Task remains IN_PROGRESS. Implements the approved slice's complete counts,
field-coverage and within-preview duplicate-candidate groundwork over the v12
tables. It does not create SourceRecords or replace CAP-04.S03 reconciliation.

The repository computes bounded rows from the real draft, not worker-supplied
facts. Every row needs store/inspect permission, including excluded/malformed/
context rows. It checks actual running activity, capability, lease, cancellation,
accepted parse and current immutable revision. Projection occurs outside the
writer reservation and the same revision is rechecked atomically before append.
Counts derive from complete stored rows. Empty success is distinct from no
accepted summary; malformed, excluded and context counts remain explicit.

Raw-byte and normalized-DOI groups are candidates only, with coverage over
included parsed records. Overlapping reasons count each record once. Groups and
ordinal members use bounded keyset pages, with no pair expansion or raw copies.
Actual workflow receipts bind source/manifest, project/preview, immutable draft,
parse/summary attempt, job, algorithm and ordered-result digest. Reads require the
exact accepted output reference and current draft. Provisional/cancelled attempts
stay hidden; expired attempts restart at zero and cannot publish earlier rows.

The existing draft-page adapter resolves effective decision revisions once per
page, then streams exact-key payloads. This preserves undo branches, current and
historical permission checks, correction semantics and the 16 MiB early stop.
Read-only preflight recommended this bounded query to avoid repeated deep-history
traversal during summary scans; this is current feature integration, not a new
supplemental refactor or schema change.

Tests preceded implementation: the new module/adapter was absent and the
per-record-history prohibition failed. Exploratory checks then caught test-only
issues: comparing parser raw bytes against intentionally metadata-only stored IR,
a duplicate helper argument, and a shared fixture's different synthetic project
identity. Corrections preserve the intended assertions; initial failures remain
distinct from later qualifying results. Formatting/type findings and the required
packaging module inventory's sorted order were corrected.

Selected checks: new mechanical-domain and actual repository/queue/provenance
tests, affected historical/current draft/API tests, packaging inclusion, type,
lint, architecture and quality inventory. A query-only 100k-row fixture measures
group/count/digest behavior and Python buffering; it does not claim full-project
ingestion, protected-disk performance or worker/native/UI qualification. No W1
full-suite replay is selected. Commit-bound verification and independent review
follow. Runtime scheduling, activity authority, API/UI and native/packaged/actual
100k-project evidence remain CAP-04.S01.T02 work.
