---
id: ADR-0016
title: Upgrade local object envelopes through a durable verified copy-on-write state machine
status: Accepted
date: 2026-08-18
deciders:
  - repository-owner
linked_tasks:
  - CAP-02.S03.T02
decision_scope: The release-compatible local object-envelope format, key-wrapping failure classification, and the durable coordination of prior plaintext object upgrades across SQLite and same-volume filesystem state.
affected_paths:
  - packages/contracts/storage/**
  - services/core-api/src/research_observatory_core/migrations/**
  - services/core-api/src/research_observatory_core/object_store.py
  - services/core-api/src/research_observatory_core/projects.py
  - services/core-api/src/research_observatory_core/storage.py
  - services/core-api/src/research_observatory_core/ports/object_store_keys.py
  - tests/contracts/test_object_store_contract.py
  - tests/data/test_encrypted_object_store.py
  - tests/data/test_sqlite_migrations.py
  - tests/data/test_sqlite_schema.py
  - tests/service/test_project_lifecycle.py
  - docs/architecture/local-object-storage.md
supersedes: []
superseded_by: null
---

# ADR-0016: Upgrade local object envelopes through a durable verified copy-on-write state machine

## Context

W1 selected authenticated encrypted project object storage while retaining the
plaintext SHA-256 content identity and opaque physical name established by
ADR-0015. CAP-02.S03.T01 deliberately introduced `plaintext-fixture-v1` as an
intermediate implementation seam. The first T02 implementation added relational
envelope columns but treated every existing v2 object as that test-only profile.
Independent security review demonstrated that a supported prior object then
remained plaintext, ordinary production open denied it, and an encrypted re-put
conflicted with the immutable content identity. The approved slice plan already
requires verified copy-on-write envelope upgrades with retained rollback, so the
current behavior cannot be release-qualified.

The repair crosses two durability domains. SQLite can atomically commit its own
rows, but it cannot roll back filesystem renames; conversely, a same-volume file
replacement cannot atomically commit SQLite metadata. Large-object encryption
also requires a project master key, bounded streaming I/O, and potentially long
work that must not run inside an Alembic DDL transaction. Windows replacement
APIs do not remove the need for an application journal: `ReplaceFileW` can retain
a backup but its write-through flag is unsupported, while `MoveFileExW` provides
write-through moves but not one transaction spanning two moves and SQLite.

The selected design must preserve researcher data, never expose unverified
plaintext to an ordinary production open, resume after interruption at every
material boundary, and remove the last plaintext rollback copy only after the
encrypted canonical object and metadata have both been verified.

## Candidates

1. Encrypt existing files inside the Alembic schema migration and one SQLite
   write transaction. This looks procedurally atomic but couples DDL to key
   providers and unbounded file I/O, holds the sole WAL writer, and still cannot
   roll back filesystem replacement with the database transaction.
2. Mark legacy rows and rewrite lazily on first open or duplicate put. This
   shortens startup work but intentionally leaves protected bytes plaintext for
   an unbounded period, makes first use a mutating operation, and reproduces the
   denial/conflict state found by security review.
3. Preserve committed migration history, advance through a successor relational
   profile that adds a durable object-upgrade journal, and run a key-dependent
   project-upgrade state machine before ordinary project open. Each object is
   streamed to an encrypted same-volume replacement, authenticated, swapped
   with retained rollback, committed in SQLite, verified through the production
   reader, and cleaned up. Restart reconciles the journal and observed file
   identities.
4. Reject prior projects and require destructive re-import. This is simpler but
   violates local project durability, provenance continuity, and the explicit
   compatibility duty.

## Decision

Adopt candidate 3. Do not rewrite the already committed v3 migration record.
Introduce a forward successor schema/profile that distinguishes legacy plaintext
objects from explicit test fixtures and records one operation row per object.
The relational migration may establish this state, but it may not claim that a
legacy object is encrypted or release-compatible merely by applying defaults.

Before an upgraded project becomes ordinarily open, Core obtains the required
project master-key version and holds the project upgrade lock. For each legacy
object it performs these recoverable phases:

1. `legacy-detected`: resolve the canonical object by opaque identity and verify
   exclusive file identity, recorded plaintext length, and SHA-256. A missing,
   redirected, hardlinked, or corrupt source stops with explicit recovery state.
2. `replacement-writing`: stream plaintext directly into an operation-scoped
   encrypted file on the same volume. No second plaintext staging file is made.
3. `replacement-verified`: fsync the replacement, authenticate its final tag,
   decrypt through the verifier, and match the recorded length and SHA-256. Store
   the intended envelope/key/wrap metadata in the journal without changing the
   canonical object row.
4. `swap-intent`: durably record the expected original, replacement, rollback,
   and canonical identities before any rename. Move the original to the guarded
   rollback location and the replacement to the canonical path using the
   platform adapter's write-through same-volume operations.
5. `metadata-committed`: reverify the canonical encrypted file, then atomically
   update the object row and journal in SQLite. Ordinary readers remain denied
   while any legacy or swap-recovery state exists.
6. `complete`: prove the production open path returns the recorded plaintext,
   close its held reader, remove the plaintext rollback file, reconcile staging,
   and mark the operation complete. Completed upgrade history remains auditable
   without retaining paths, hashes, key bytes, or research content in logs.

Restart uses the durable phase plus stable file identities to finish or restore
the last safe state. It never guesses from filenames alone. Missing key material
leaves the operation recoverable and the original preserved. Insufficient disk,
source corruption, authentication failure, rename failure, SQLite failure, or
cancellation leaves either the verified original or a journaled rollback copy;
none permits ordinary access until reconciliation succeeds.

Envelope/framing/magic/final-tag/trailing-content or structurally invalid stored
metadata is corruption and quarantines before first byte. A missing provider,
missing recorded key version, unusable key bytes, or AEAD unwrap failure for
otherwise well-formed wrapped-key metadata is classified as key unavailable and
preserved for recovery because wrong retained master-key bytes and a modified
wrapped key are not distinguishable at that boundary. Contracts, tests, and
evidence must state this conservative classification exactly.

## Consequences

LOC and LAB gain a deterministic upgrade path for v2/v3 projects and retain
plaintext only as bounded rollback state while an upgrade is incomplete. Normal
project use cannot proceed until every legacy protected object is encrypted and
verified. A large project may therefore take measurable startup/recovery time and
requires enough free space for one object's encrypted replacement plus rollback;
progress, cancellation, and low-disk behavior must be explicit and restartable.

The successor schema and portable profile add journal/state vocabulary, but
filesystem paths and key bytes remain adapter-private. Hosted adapters may use a
different physical swap primitive while preserving the phase and verification
contract. Rollback to an older application is not permitted after the successor
profile commits; recovery uses the verified pre-migration database backup plus
the per-object rollback authority, never deletion or re-import.

ADR-0015 remains authoritative for content identity, project deduplication,
opaque names, publication, and controlled streams. This record adds the
encryption envelope, upgrade, and recovery decision without superseding those
rules. CAP-02.S04 still owns the production OS credential-store adapter; T02 uses
its existing key-provider port and deterministic test provider.

## Verification

- v2 and rejected-v3 project fixtures upgrade to the successor profile and open
  through the production encrypted reader with no plaintext canonical, staging,
  or rollback file after completion;
- deterministic failpoints before and after every journal, fsync, rename,
  verification, metadata-commit, and cleanup boundary, followed by restart and
  exact finish-or-restore assertions;
- missing key, wrong key, corrupt source, insufficient disk, cancellation,
  SQLite busy/failure, and rename failure preserve bounded recoverability;
- magic/header, frame length/ciphertext, missing or duplicate final tag,
  trailing content, wrapped key, wrap nonce, and key-version mutation tests prove
  denial before first byte and the specified quarantine/key-unavailable state;
- strict schema/profile validation, migration-history and backup recovery tests,
  focused security/data/service suites, and frozen-sidecar inclusion;
- independent remediation review replays the original P1/P2 findings and the
  incremental migration/envelope risk boundary.

## Task links

- `CAP-02.S03.T02`
