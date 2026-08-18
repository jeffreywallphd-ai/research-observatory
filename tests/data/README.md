# Data verification

Owner: Data maintainers. Boundary: schemas, migrations, repositories, storage, backup, and recovery tests.

Task checks remain risk-focused. `test_sqlite_schema.py` exercises the current version-2
STRICT/WAL connection, schema, concurrency, restart, integrity, and denial
boundaries. `test_sqlite_migrations.py` exercises the exact supported version-1
fixture, mutation-free planning, writer-locked verified backup, transactional
upgrade/rollback, recovery records, and idempotent current-schema detection.
`test_sqlite_repositories.py` exercises typed aggregate projections, explicit
unit-of-work commit/rollback, optimistic conflict, not-found behavior, atomic
revision/provenance/outbox publication, and the no-SQL-outside-data-layer
boundary. Deterministic draft/event helpers supply fixed IDs and timestamps
without weakening production validation. Hostile cases also cover dependency-
neutral port imports, indirect SQL, bounded writer contention and incompatible
authority, exact idempotent replay, and changed payload/precondition conflict.
Complete data and recovery profiles run once the integrated storage
slice is reviewed.
