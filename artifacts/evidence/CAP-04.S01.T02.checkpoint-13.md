# CAP-04.S01.T02 — protected summary storage groundwork

Increment from approved `67786af5de38a5644e40f975ba04eda1c9f17a80`.
Task remains IN_PROGRESS. The approved slice requires complete counts, coverage
and duplicate candidates. Read-only preflight found no existing bounded group
store: settings are scalar/size-limited; arbitrary object hashes do not acquire
retention references. A narrow additive v12 migration supplies four protected
relations while reusing existing project storage and durable-worker authority.
This is planned feature work, not a new database or supplemental refactor.

Attempts bind project/preview, immutable draft, accepted parse attempt and worker
attempt. Ordinal rows carry only bounded classification/coverage and grouping
digests; groups support indexed member paging without quadratic pair expansion.
Foreign keys retain exact parse record keys. Append-only and membership triggers
deny mutation, gaps, orphan/wrong-attempt inputs and incomplete completion.
Repository runtime rights, lease fencing, receipt dependency validation and
accepted-output visibility are still required next; DDL alone does not prove them.

Exact v11 metadata/preview DDL was captured from the predecessor before product
edits into `tests/fixtures/imports/schema-v11-authority.json`. The fixture passed
its historical fingerprint before implementation; the new migration expectation
failed and the not-yet-present migration import errored, as expected. Migration
preserves a populated preview/event and prior settings, invents no summaries and
retains an exact backup. All eight new material failpoints roll back and retry.
Actual SQLCipher tests prove encrypted predecessor/backup and failure recovery
using isolated in-memory test key authority, not the user's vault or DPAPI.

Exploratory checks caught stale profile/recovery-schema constants and one old
conditional migration-chain expectation; these are advanced to v12 while every
historical fingerprint and migration remains unchanged. An encrypted test omitted
the fixture key provider's required `create=False` argument; the corrected check
passed. None of these initial failures is represented as qualifying success.
The packaging-contract check also caught the new migration missing from the
builder's exact module allowlist; the contract, builder and test now agree.

Verification selection: affected migration-chain tests because the registry and
successor endpoints changed; new relational and protected-backup checks; current
profile/bootstrap/sealed-connection controls; prior draft/API smoke on the new
schema; affected lint/type/architecture/packaging-contract checks. Full W1 and
product release profiles are deferred. Commit-bound checks and independent
migration review follow. This increment exposes no summary service/UI yet and
does not complete CAP-04.S01.T02 or qualify full-project scale/packaging.
