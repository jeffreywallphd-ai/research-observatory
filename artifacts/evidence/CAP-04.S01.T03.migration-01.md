# CAP-04.S01.T03 — additive commit storage increment

Parent implementation checkpoint: `6596136cdb268aa3391fc09c782f00fac9f4da87`.
This is migration/relational groundwork, not task completion or a usable import
commit. Repository, atomic worker completion, API and governed UI remain pending.

## Scope and adverse observations

- Added v13 forward migration, exact current profile/recovery contracts and
  packaging inventory. Existing v12 fingerprint and literal fixture remain
  unchanged. Migration creates empty commit tables, not historical imports.
- Initial v12 upgrade test failed because no v13 migration existed. After
  implementation, backup/preservation/reopen passed. Rollback fixture setup then
  failed before migration because the parent directory was created twice; only
  the new test's redundant mkdir was removed. All eight rollback steps passed.
- SQLCipher encrypted rollback/retry/backup/reopen passed with synthetic
  in-memory key authority. This is not Windows DPAPI/principal qualification.
- The first affected compatibility run (37 tests, 29.418 seconds) had five stale
  latest-history expectation failures, four packaging errors from the missing
  new module in the build inventory, and one skip. Exact predecessor fixtures
  were not changed. The five expected successor histories and packaging inventory
  were updated; eight targeted retry tests passed in 1.090 seconds. The full
  packaged executable build is deferred until the runtime commit path is ready.
- Lint found long lines and test-loop binding/context issues; these were fixed.
  A patch-construction mistake initially placed two inventory additions at file
  starts; syntax/JSON inspection caught it and the entries were moved to their
  actual lists before subsequent tests. SQL formatting changed fingerprints;
  only new v13 pins were recalculated, never historical endpoints.

## Advisory review and added acceptance rows

Independent read-only schema review identified two previously missed relational
invariants: manifest decisions must equal staged bytes, and comparison references
must belong to the explicitly chosen sealed predecessor. Root cause: original
constraints verified valid individual identities/counts but not the complete
relationship across staging and publication.

Added production-DDL unit tests with explicitly synthetic parent rows. The tests
first demonstrated seven failed denial assertions, then passed after constraints
were added for selected/excluded decisions, exact decision/warning/raw/DOI bytes,
sealed predecessors and included predecessor membership. Positive comparison,
append-only denial and FK checks remain. One initial negative-test loop allowed
the first unexpected insert to contaminate later probes; savepoint rollback now
isolates every substitution and exposed all seven failures before remediation.

Final exploratory migration plus constraint group: nine tests passed in 2.470
seconds. These observations are not commit-bound qualification. Fresh focused
candidate checks and independent bounded review follow; full task evidence must
also prove current rights/draft/lease checks, atomic canonical/provenance/output
publication, replay and end-to-end user behavior.
