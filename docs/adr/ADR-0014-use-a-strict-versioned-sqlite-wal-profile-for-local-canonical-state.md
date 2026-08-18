---
id: ADR-0014
title: Use a strict versioned SQLite WAL profile for local canonical state
status: Accepted
date: 2026-08-14
deciders:
  - W1 repository-owner pre-Wave approval at 594e63be501711d67d17a4aef176bb9b6a8748be
linked_tasks:
  - CAP-02.S02.T01
  - CAP-02.S02.T02
  - CAP-02.S02.T03
decision_scope: Local SQLite identity and timestamp representation, initial normalized schema, canonical connection controls, checkpoint and integrity authority, and the later migration and repository boundaries.
affected_paths:
  - packages/contracts/storage/**
  - packages/contracts/README.md
  - services/core-api/src/research_observatory_core/storage.py
  - services/core-api/src/research_observatory_core/ports/**
  - services/core-api/src/research_observatory_core/repositories.py
  - services/core-api/src/research_observatory_core/projects.py
  - services/core-api/packaging/sidecar-build.json
  - tests/data/**
  - tests/packaging/test_core_sidecar_package.py
  - tests/service/test_project_lifecycle.py
  - tools/architecture_check.py
  - tools/core_sidecar_build.py
  - packaging/build-inputs.json
  - quality-scope.json
  - docs/architecture/local-sqlite-storage.md
  - docs/architecture/README.md
supersedes: []
superseded_by: null
---

# ADR-0014: Use a strict versioned SQLite WAL profile for local canonical state

## Context

The local project package now has a strict relocatable layout and a UUIDv4
project bridge, while shared scholarly aggregates use UUIDv7. W1 needs an
initial canonical database before migrations and typed repositories can be
implemented. That database must tolerate a desktop reader while a bounded
writer commits, survive Core restart, fail closed on incompatible files, and
avoid turning opaque derived binaries into arbitrary relational values.

SQLite defaults are not sufficient authority. Foreign-key enforcement and
trusted-schema behavior can differ by connection or build, WAL activation must
be verified from its returned result, and NORMAL synchronization can lose a
recent acknowledged transaction after power loss. STRICT is also a per-table
choice rather than a database-wide switch. The official SQLite WAL, pragma,
STRICT-table, and security guidance was rechecked for this task.

## Candidates

1. Use SQLite defaults and hand-open connections in each module. This is small,
   but foreign keys, durability, timeout, extension loading, and integrity
   behavior can drift silently between callers.
2. Define one versioned `sqlite-wal-v1` profile, use STRICT normalized scalar
   tables, apply and verify the complete connection profile centrally, retain
   content and derived binaries by digest reference, and introduce Alembic and
   SQLAlchemy only in their approved migration and repository tasks.
3. Add SQLAlchemy and Alembic in this first task and let ORM metadata create the
   database. This brings later boundaries forward, makes the initial schema
   depend on unimplemented repository models, and obscures the exact bootstrap
   DDL that every prior-version migration must reproduce.

## Decision

Adopt candidate 2. `packages/contracts/storage/sqlite-profile.v1.json` fixes
application ID `0x524f4253` (`ROBS`), schema version 1, the fourteen canonical
tables, allowed scalar column types, identifier/timestamp representation, and
connection/integrity policy. Its strict companion schema rejects overrides.
Core embeds the same semantic profile, and focused tests prove exact equality.

Every canonical table is SQLite STRICT. Aggregate, revision, event, outbox, and
setting identities are lowercase RFC 9562 UUIDv7 text. The project table is an
immutable identity anchor: it accepts the explicit ADR-0012 UUIDv4 bridge or a
future UUIDv7 identity with a matching stored scheme. It deliberately does not
copy mutable project-manifest lifecycle fields before the repository/UoW task
can update those states atomically. Persisted UTC instants use fixed
millisecond `YYYY-MM-DDTHH:MM:SS.mmmZ` text so ordering is lexical and precision
is unambiguous.

Each canonical connection explicitly enables and verifies foreign keys, WAL,
FULL synchronization, a 5-second busy timeout, untrusted schema, recursive
triggers, normal locking, and a 1000-page passive auto-checkpoint. It disables
loadable extensions, double-quoted string literals, and enables SQLite's
defensive connection configuration. Ordinary application code receives only a
restricted connection/cursor capability: it cannot replace the authorizer,
change connection configuration, enable extensions, reach a raw-cursor back-reference,
or issue write-form identity, security, or durability PRAGMAs. Only the backed-up migration connection introduced by T02
may replace governed DDL and its fingerprint. Database and parent identities are held
against Windows rename/delete while the connection is live. Project creation
initializes and verifies the schema inside the unpublished staging root; a
compatible project open verifies the immutable application/profile/schema
fingerprint and project identity before publishing a session lock or audit
record. Full `quick_check` and `foreign_key_check` probes remain explicit rather
than adding a database-size scan to every interactive open; the next tasks own
routine startup/maintenance scheduling and user-visible recovery.

Schema version 1 separates stable aggregate identities from normalized common
aggregate revisions, with exact
kind extension tables for scholarly records, documents, workflows, evidence,
ontologies, and decisions. Project/schema identities, aggregate identities,
aggregate revisions and their kind-extension rows are insert-only through
fingerprinted update/delete denial triggers. Typed settings cannot store
arbitrary JSON or binaries, and each versioned setting row is likewise
append-only. Provenance rows remain append-only. Object availability metadata
and outbox delivery metadata are the only intentionally mutable version-1 row
classes. The repository task will supply atomic domain-event behavior rather
than smuggling payload blobs into this schema.

Alembic forward migrations, backup-before-migrate, recovery manifests, and
checkpointed snapshots belong to `CAP-02.S02.T02`. Its dedicated migration
connection must replace denial triggers only inside the reviewed, backed-up
schema transition and publish the successor fingerprint before ordinary access.
SQLAlchemy 2 typed
repositories and explicit units of work belong to `CAP-02.S02.T03`; business
and renderer code never receive a SQLite connection. Dependency-neutral domain
values, bounded outcomes, and repository/unit-of-work protocols live under the
Core `ports` package; importing those ports does not load SQLite, SQLAlchemy, or
the local adapter. The private SQLAlchemy 2 Core adapter compiles parameterized
statements against the sealed canonical connection and is constructed only at
the composition boundary. The bootstrap adapter may
issue only its governed schema/profile SQL. Manual FULL/RESTART/TRUNCATE
checkpoints are reserved for migration, backup, snapshot, or maintenance code.

## Consequences

Readers retain a stable WAL snapshot while a writer commits, and another writer
waits for the bounded busy timeout rather than failing immediately. FULL
synchronization adds an fsync to each WAL commit, favoring acknowledged-command
durability over maximum write throughput. The 1000-page passive threshold is a
starting workstation policy; representative slice benchmarks may recommend a
new reviewed profile but cannot silently rewrite version 1.

No canonical table declares `BLOB` or `ANY`. The object metadata table binds a
project to SHA-256 identity, byte length, media type, rights, protection,
retention, storage state, and verification time without carrying bytes or a
filesystem path. Object/document bytes, indexes, models, and other derived
files remain in their classified project storage; database rows hold only
stable digests and metadata. This first task does not
claim database confidentiality: SQLCipher or an approved equivalent, key
acquisition, permissions qualification, and protected backup belong to the
later W1 protection/recovery slices. Until then the profile is suitable for
development and the approved staged local implementation, not a claim that
sensitive projects are encrypted at rest.

An application/profile/schema mismatch, redirect, hardlink, failed integrity
check, or wrong project identity is rejected without replacing the file. WAL
and SHM files are part of the live database state and must never be copied
independently. Rollback before release removes schema version 1. After a project
has canonical rows, rollback requires a validated reader or migration and may
not discard accepted revisions, provenance, or decisions.

## Verification

- exact Draft 2020-12 storage-profile validation and runtime semantic parity;
- version/application/profile/STRICT table and trigger inventory checks;
- fixed UUID, UTC millisecond, scalar type, typed-setting, FK, kind, and
  immutable identity/revision/extension/settings and append-only provenance
  constraint attacks;
- concurrent WAL reader/writer snapshot plus bounded second-writer wait;
- close/reopen integrity and exact project-identity verification;
- dependency-neutral port import plus dynamic/indirect SQL denial outside data adapters;
- optimistic conflict, exact command/precondition idempotency replay, changed-command conflict,
  bounded busy/incompatible authority, and atomic revision/provenance/outbox rollback;
- existing-file, hardlink, wrong-application-ID, and project-open denial with
  no lock, audit, or outside-file mutation;
- focused Core lifecycle, quality, architecture/ADR, task, and generated-view
  checks, followed by the complete data profile at slice review.

## Task links

- `CAP-02.S02.T01`
- `CAP-02.S02.T02`
- `CAP-02.S02.T03`
