# Frozen populated schema-v17 predecessor

These JSON documents freeze the T01 database authority at commit
`5e33b15f7e4267d27cadb46b288524872467b032`, before CAP-04.S04.T02 rights
storage changes. `schema-v17-authority.json` contains literal SQLite schema
objects. The two populated files contain every table row from separate synthetic
projects created through existing T01 repositories:

- `schema-v17-import-corpus-populated.json`: a published local import, its
  retained source assertion and Work, and an import-member corpus discovery path.
  The source test fixture uses the explicit plaintext migration-test profile.
- `schema-v17-connector-corpus-populated.json`: an accepted connector query and
  page, reconciled source/Work, and a connector-record corpus discovery path.
  This history came from the protected SQLCipher connector project fixture.

Both include their real provenance, outbox, workflow, and material-dependency
rows. They are separate projects; the fixture does not pretend that one project
executed both source paths. All content is synthetic test data, not a scholarly
observation or a licensed-source entitlement. Each corpus aggregate retains
`rights_status='unknown'`; earlier `ImportRights` observations are not new
action-specific grants.

`tests/rights/test_migration.py` pins the three fixture byte hashes, the v17
schema/profile fingerprints, and complete order-independent row fingerprints.
Its loader creates the literal predecessor without consulting current storage
DDL, then verifies project identity, source path, populated row counts, foreign
keys, and integrity after reopen. The v18 test checks backup-first migration of
both histories, exact preservation of every predecessor row outside migration
metadata, no fabricated rights grant, restart, and idempotent reopen. Every
material v18 failpoint rolls back to v17 and retries from the retained verified
backup. A protected SQLCipher test checks encrypted failure/backup/retry/reopen.

The original `sqlite-migration-recovery.schema.json` bytes are retained in
`packages/contracts/storage/sqlite-migration-recovery-v17.snapshot.json` for
historical target-v17 manifests. The current recovery schema binds v18 and
adds v17 as an exact supported source. Do not change predecessor fixture bytes
or the frozen v17 recovery contract to make a successor migration pass.
