# CAP-04.S01.T02 — explicit delimiter authority

Increment from approved `f44e175c70e3cb5f2ef7efe3bf551192c8c645c2`.
Task remains IN_PROGRESS; no approved-scope or database-schema change.

Read-only preflight selected one immutable reserved settings record per new
preview instead of a migration for a scalar parsing option. The record is
atomic with creation, revision zero only, identity/format/encoding-bound, and
has no public updater. Legacy absence means comma with no backfill. The existing
v11 schema, migrations and fingerprints are unchanged.

The preflight also identified generated workflow-schema identity as a restart
risk. A literal synthetic comma-job fixture was captured from the predecessor
before edits; its persisted definition, configuration and queue claim still
bind. A golden effective-draft digest preserves the exact comma `/1` bytes.
Non-comma CSV inputs use explicit workflow version 1.1 and effective-draft `/2`
identity. Native intake, Core, worker, receipt, completion and generated review
summary all carry the persisted choice. Other formats reject non-comma options.

Material proofs: literal queued-job reload; delimiter substitution denial;
immutable/atomic settings, malformed/foreign settings and extra-revision denial;
legacy no-backfill; wrong-delimiter parser completion rejection; actual Core,
encrypted-object and worker tab/semicolon round trips across project reopen;
generated-client decoder, native request validation and actual built UI/Core
journey with explicit native-host doubles. UI changes reuse shared fields and
explain that changing parsing starts a new preview.

Before implementation the golden comma-job test passed, while new alternative
delimiter model/API cases failed and wrong-delimiter completion was accepted.
After implementation the 30-case exploratory selection had passing product
assertions but two new fixture teardown errors: addCleanup runs after fixture
tearDown, leaving SQLite handles open during disposal. Explicit try/finally
closure fixed the fixture; the two affected cases plus the new malformed-setting
case passed (three cases, 0.281s). These errors are not counted as qualification.
An added receipt assertion initially compared SQLite Row containers to tuples;
it now compares their fingerprint values, retaining the exact receipt check.

Selected candidate checks cover the changed persistence, identity, API, native
request and renderer boundaries, affected types/lint/contracts and product build.
Exact-candidate verification and independent review follow the commit. Unchanged
migration/full W1 suites are not rerun. Native-window/packaging, complete 100k
project qualification, count/duplicate projection and undo remain task work.
