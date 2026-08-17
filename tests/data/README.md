# Data verification

Owner: Data maintainers. Boundary: schemas, migrations, repositories, storage, backup, and recovery tests.

Task checks remain risk-focused. `test_sqlite_schema.py` exercises the current version-2
STRICT/WAL connection, schema, concurrency, restart, integrity, and denial
boundaries. `test_sqlite_migrations.py` exercises the exact supported version-1
fixture, mutation-free planning, writer-locked verified backup, transactional
upgrade/rollback, recovery records, and idempotent current-schema detection.
Complete data and recovery profiles run once the integrated storage
slice is reviewed.
