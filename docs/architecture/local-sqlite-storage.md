# Local SQLite storage profile

The local Core service is the sole authority that opens
`state/project.sqlite3`. The desktop renderer, native shell, workers, and
business modules do not receive filesystem paths or SQLite connection objects.
ADR-0014 governs the first database profile; the portable machine record is
[`sqlite-profile.v1.json`](../../packages/contracts/storage/sqlite-profile.v1.json).

## Version-1 authority

| Concern | Version-1 rule |
|---|---|
| Database identity | application ID `0x524f4253`, `user_version=1`, profile `sqlite-wal-v1` |
| Durable identities | lowercase UUIDv7 text; project UUIDv4 bridge is explicitly tagged |
| Time | UTC RFC 3339 text at fixed millisecond precision |
| Types | STRICT `INTEGER`, `REAL`, and `TEXT`; no `ANY` or `BLOB` columns |
| Concurrency | WAL, normal locking, one writer, concurrent reader snapshots, 5-second busy timeout |
| Durability | `synchronous=FULL`; 1000-page passive auto-checkpoint |
| Trust | foreign keys on, trusted schema off, defensive mode on, DQS and extensions off |
| Integrity | exact table/trigger inventory, `quick_check`, and `foreign_key_check` |

Every connection is created by the canonical storage factory and re-verifies
these controls. WAL activation is accepted only when SQLite returns `wal`.
Project creation builds and checks the database before the staging directory is
published. Compatible project open validates database identity and integrity
before creating the session lock or appending the open audit record.

## Normalized table inventory

| Table | Authority |
|---|---|
| `schema_metadata` | singleton schema/profile/application identity |
| `projects` | immutable project identity anchor; mutable lifecycle remains manifest-owned until repository integration |
| `object_records` | content digest, size, media type, rights, protection, retention, and verification metadata; never object bytes or paths |
| `aggregate_identities` | stable project-scoped aggregate identity and kind |
| `aggregate_revisions` | immutable common scholarly aggregate revision envelope |
| `scholarly_records`, `documents`, `workflows`, `evidence`, `ontologies`, `decisions` | exact kind extension rows keyed to a common revision |
| `provenance_events` | append-only typed event metadata and record digest |
| `settings` | versioned, exactly-one-of typed scalar project settings |
| `outbox_events` | transaction-outbox metadata/digest seam for the later unit of work |

Object bytes, document content, indexes, models, caches, and other derived
binary artifacts remain in the classified project-package locations. The
database may retain a SHA-256 reference; it does not admit arbitrary payload or
derived blob columns.

## Evolution and recovery boundary

T01 owns only schema version 1 and its connection factory. T02 owns forward
migrations, backup-before-migrate, checkpointed snapshots, prior-schema
fixtures, and failure recovery. T03 owns SQLAlchemy repositories, optimistic
concurrency, transaction/outbox publication, and units of work. Central
bootstrap/migration code is the only allowed source of schema SQL; domain and UI
code must use the repository ports.

WAL and SHM files are live database state. A backup or relocation implementation
must use SQLite's backup/checkpoint facilities and never copy only the main file
while a WAL transaction may be pending. Profile mismatch, corruption, redirect,
hardlink, or wrong project identity fails closed and preserves the source for
backup-first repair.

The first profile does not claim encryption at rest. The approved W1 protection
slice must add SQLCipher or an approved equivalent, OS-vault key acquisition,
permissions qualification, and protected backups before sensitive projects are
production-qualified.
