# Data verification

Owner: Data maintainers. Boundary: schemas, migrations, repositories, storage, backup, and recovery tests.

Task checks remain risk-focused. `test_sqlite_schema.py` exercises the version-1
STRICT/WAL connection, schema, concurrency, restart, integrity, and denial
boundaries. Complete data and recovery profiles run once the integrated storage
slice is reviewed.
