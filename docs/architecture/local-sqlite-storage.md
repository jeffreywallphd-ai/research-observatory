# Local SQLite storage profile

The local Core service is the sole authority that opens
`state/project.sqlite3`. The desktop renderer, native shell, workers, and
business modules do not receive filesystem paths or SQLite connection objects.
ADR-0014 governs the first database profile; the portable machine record is
[`sqlite-profile.v1.json`](../../packages/contracts/storage/sqlite-profile.v1.json).

## Current version-2 authority

| Concern | Current rule |
|---|---|
| Database identity | application ID `0x524f4253`, `user_version=2`, profile `sqlite-wal-v1` |
| Durable identities | lowercase UUIDv7 text; project UUIDv4 bridge is explicitly tagged |
| Time | UTC RFC 3339 text at fixed millisecond precision |
| Types | STRICT `INTEGER`, `REAL`, and `TEXT`; no `ANY` or `BLOB` columns |
| Concurrency | WAL, normal locking, one writer, concurrent reader snapshots, 5-second busy timeout |
| Durability | `synchronous=FULL`; 1000-page passive auto-checkpoint |
| Trust | foreign keys on, trusted schema off, defensive mode on, DQS and extensions off |
| Integrity | exact table/trigger inventory, immutable-row denial triggers, `quick_check`, and `foreign_key_check` |

Every connection is created by the canonical storage factory and re-verifies
these controls. WAL activation is accepted only when SQLite returns `wal`.
Project creation builds and checks the database before the staging directory is
published. Compatible project open validates application, profile, exact schema
fingerprint, and project identity before creating the session lock or appending
the open audit record. Full `quick_check` and `foreign_key_check` scans are
explicit integrity operations so interactive open cost does not scale with the
database; T02/T03 must schedule them at startup/maintenance and surface recovery.

## Normalized table inventory

| Table | Authority |
|---|---|
| `schema_metadata` | immutable singleton schema/profile/application identity |
| `schema_migrations` | append-only successful forward-migration identity, backup-manifest binding, and source/target fingerprints |
| `projects` | immutable project identity anchor; mutable lifecycle remains manifest-owned until repository integration |
| `object_records` | content digest, size, media type, rights, protection, retention, and verification metadata; never object bytes or paths |
| `aggregate_identities` | immutable project-scoped aggregate identity and kind |
| `aggregate_revisions` | immutable common scholarly aggregate revision envelope |
| `scholarly_records`, `documents`, `workflows`, `evidence`, `ontologies`, `decisions` | immutable kind extension rows keyed to a common revision |
| `provenance_events` | append-only typed event metadata and record digest |
| `settings` | append-only versioned, exactly-one-of typed scalar project settings |
| `outbox_events` | transaction-outbox metadata/digest seam for the later unit of work |

Object bytes, document content, indexes, models, caches, and other derived
binary artifacts remain in the classified project-package locations. The
database may retain a SHA-256 reference; it does not admit arbitrary payload or
derived blob columns.

Every row in `schema_metadata`, `projects`, `aggregate_identities`,
`aggregate_revisions`, the six kind-extension tables, `provenance_events`, and
`settings`, and `schema_migrations` deny UPDATE and DELETE in fingerprinted DDL. New revisions and
setting values are inserts. `object_records` may advance availability and
verification state, while `outbox_events` may advance delivery state; these are
the only intentionally mutable current-profile tables.

## Evolution and recovery boundary

T01 established schema version 1 and its sealed ordinary connection factory.
T02 advances the current schema to version 2 and owns forward migrations,
backup-before-migrate, checkpointed snapshots, the exact supported version-1
fixture, and failure recovery. The migration runner validates and checkpoints
version 1, reserves SQLite's writer lock, creates and verifies an online backup
through a second held connection, and only then runs the reviewed Alembic
revision in one transaction. The immutable recovery manifest binds the backup
bytes and both schema fingerprints; a failed transaction rolls back while the
verified backup remains available. A current version-2 database is detected
idempotently and is never backed up or rewritten. T03 owns SQLAlchemy repositories, optimistic
concurrency, transaction/outbox publication, and units of work. Central
bootstrap/migration code is the only allowed source of schema SQL; domain and UI
code must use the repository ports. Ordinary canonical access returns a
restricted connection/cursor capability rather than a raw `sqlite3.Connection`:
authorizer, configuration, extension-loading, raw-cursor, backup, serialization,
and callback escape hatches are not exposed. Its underlying authorizer denies
schema DDL plus write-form identity, security, and durability PRAGMAs. T02
uses a separate, tightly scoped migration connection that is never returned to
ordinary code, operates only after verified backup, replaces the affected denial
triggers as part of the successor DDL, and publishes the new exact fingerprint
before normal access resumes.

WAL and SHM files are live database state. A backup or relocation implementation
must use SQLite's backup/checkpoint facilities and never copy only the main file
while a WAL transaction may be pending. Profile mismatch, corruption, redirect,
hardlink, or wrong project identity fails closed and preserves the source for
backup-first repair.

The first profile does not claim encryption at rest. The approved W1 protection
slice must add SQLCipher or an approved equivalent, OS-vault key acquisition,
permissions qualification, and protected backups before sensitive projects are
production-qualified.
