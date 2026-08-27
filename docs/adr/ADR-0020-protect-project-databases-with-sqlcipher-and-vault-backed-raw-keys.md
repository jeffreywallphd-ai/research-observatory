---
id: ADR-0020
title: Protect project databases with SQLCipher and vault-backed raw keys
status: Accepted
date: 2026-08-27
deciders:
  - W1 repository-owner pre-Wave approval at c5bbd97c0cdc665eecb973f5862478ef7be97752
linked_tasks:
  - CAP-02.S04.T04
decision_scope: Windows W1 production project-database encryption, key authority, compatibility, migration, backup/restore, rekey, corruption/key-loss behavior, packaging, licensing, performance, and residual protection.
affected_paths:
  - packages/contracts/storage/**
  - packages/contracts/security/**
  - packages/contracts/README.md
  - packaging/build-inputs.json
  - pyproject.toml
  - uv.lock
  - services/core-api/**
  - tests/**
  - tools/protected_database_performance_check.py
  - quality-scope.json
  - docs/architecture/local-sqlite-storage.md
  - docs/architecture/local-credential-storage.md
  - docs/architecture/README.md
supersedes: []
superseded_by: null
---

# ADR-0020: Protect project databases with SQLCipher and vault-backed raw keys

## Context

ADR-0014 deliberately established the logical SQLite schema, WAL, integrity,
migration, and repository profile without claiming encryption at rest. The
approved W1 CAP-02.S04 packet selects SQLCipher as the leading production
profile and requires Windows credential-backed keys, no writable plaintext
fallback, migration, backup/restore, rekey, corruption and key-loss handling,
packaging and licensing evidence, and a measured performance result.

The release authority through W5 is Windows x64 and the packaged Core uses
CPython 3.14.6. The frozen dependency evaluation found `sqlcipher3==0.6.2` is
the available CPython 3.14 Windows x64 wheel and reports SQLCipher `4.12.0
community`. The binding implements the SQLite backup API and authorizer but
does not expose CPython's newer `setconfig`, `serialize`, or `blobopen` APIs.
Enabling `cipher_memory_security` in this wheel caused a reproducible Windows
stack overflow during evaluation, so that optional control cannot be claimed.

## Candidates

1. Retain ordinary SQLite and rely only on full-disk encryption. This does not
   protect a copied project package and violates the approved task.
2. Encrypt selected application fields. This leaves schema, indexes, metadata,
   and journaling exposed and creates a second application cryptosystem.
3. Use SQLCipher Community through the pinned `sqlcipher3` wheel with one random
   raw 256-bit key per project, retrieved from the user-scoped DPAPI profile
   vault through a replaceable key-provider port.
4. Introduce a different database engine or a commercial SQLCipher package.
   Neither has demonstrated compatibility or a W1 authorization advantage;
   a commercial package would also introduce unapproved procurement.

## Decision

Adopt candidate 3 for W1. Production composition installs a mandatory database-
key provider backed by the ADR-0017 Windows current-user DPAPI profile vault.
Database keys use a distinct vault namespace and purpose from object and later
export/recovery keys. Core passes a short-lived raw 32-byte lease directly to
SQLCipher, selects compatibility level 4, requires a zero-byte plaintext
header, 4096-byte pages, HMAC-SHA-512, and the SQLCipher 4 KDF profile, then
clears the lease at the boundary. Key material is never written to project
files, exports, logs, environment variables, or process arguments. The binding
necessarily receives one ephemeral hexadecimal PRAGMA value because it exposes
no raw `sqlite3_key` API; this value is neither retained nor projected.

The logical `sqlite-wal-v1` schema and repository contract remain unchanged.
Ordinary Core connections also require foreign keys, full synchronous WAL,
trusted schema off, extensions off, the existing authorizer, exact schema and
project identity, `cipher_integrity_check`, and bounded diagnostics. Because the
wrapper lacks `setconfig`, its authorizer plus verified PRAGMAs provide the
available equivalent boundary; the missing API is not hidden.

Production initialization fails closed when the key authority is absent and
rejects the plaintext SQLite header before opening an existing project. The
only plaintext mode is an explicitly scoped development/test fixture. A legacy
plaintext project requires the exact migration-consent token, is validated
read-only, exported into a separately keyed SQLCipher candidate, verified, and
published atomically. The plaintext rollback is read-only while retained and is
best-effort overwritten and unlinked only after protected open succeeds.

Backups use SQLite's online backup API into a keyed SQLCipher destination,
checkpoint and verify cipher, logical, foreign-key, schema, and project
identity, and reject a plaintext header. Restore requires a quiescent Core
database boundary and verifies a copy-on-write candidate before atomic
publication, restoring the displaced ciphertext on failure. Comprehensive
portable project snapshots remain CAP-02.S05 work.

Rekey creates an encrypted rollback copy, stages a new vault key, rekeys and
reopens the database with that staged key, then compare-and-swap activates it.
An append-only recovery manifest resolves interruption by proving the active
key, activating the staged key, or restoring the verified encrypted backup.
Missing keys and corruption retain ciphertext and never create a replacement.

The wheel and transitive SQLCipher community binary are frozen into the
PyInstaller artifact. `THIRD_PARTY_NOTICES.txt` is copied beside the executable
and reproduces the SQLCipher BSD-3-Clause and sqlcipher3 zlib notices. Supply-
chain qualification must continue to pin the lock, import the frozen extension,
inspect the artifact, scan dependencies, and re-evaluate any wheel or SQLCipher
version change.

## Threat assumptions and residual risk

This profile protects database bytes, WAL content, and verified backups against
offline file inspection, lost removable media, and accidental plaintext
disclosure. It detects page tamper through SQLCipher HMACs. It does not isolate
data from malware running as the same unlocked Windows user, a compromised Core
process, debugger or memory dump access, administrator/kernel compromise, or a
researcher who exports content through an authorized application path.

OS sign-in, BitLocker or equivalent full-disk encryption, endpoint protection,
application lock, patching, and physical security remain required layers. Loss
of both the DPAPI authority and every later explicit recovery artifact makes the
encrypted database honestly unrecoverable. `cipher_memory_security` is disabled
because it crashes this evaluated Windows wheel; process memory protection is a
documented residual until a replacement build passes the same qualification.

## Performance result

`tools/protected_database_performance_check.py` retained seven samples after one
filesystem warmup on Windows 11 build 26200, Intel Family 6 Model 183, 20 logical
CPUs, AMD64, CPython 3.14.6. The current empty-schema fixture and 100-read query
reported these p95 values: open 3.826 ms, representative query 3.850 ms,
integrity 5.248 ms, encrypted backup 35.952 ms, plaintext migration 133.709 ms,
and rekey 36.653 ms. All passed their explicit 100/50/750/750/1500/1500 ms p95
budgets. The full sample distribution, hardware, warm/cold description, and tool
hash are retained in the task evidence. Future qualification uses a 20 percent
regression threshold against the accepted baseline as well as the absolute
budget; representative/minimum-hardware and larger-data qualification remains
mandatory at W1 exit.

## Consequences and rollback

An installed runtime without SQLCipher or its vault provider is non-production
and fails closed; ordinary SQLite is not a fallback. Before migration, rollback
means leaving a validated plaintext legacy project untouched. During migration
or rekey, the operation-specific recovery state determines whether the verified
candidate, staged key, or rollback copy is authoritative. After a protected
project becomes canonical, uninstalling SQLCipher or losing its key does not
authorize conversion, deletion, or replacement.

macOS and Linux W6 work must provide qualified native credential adapters and a
compatible protected database build. It may not copy the DPAPI adapter or assume
the Windows wheel is portable. A future SQLCipher compatibility or page-profile
change requires a new migration and superseding ADR rather than an in-place
reinterpretation of existing bytes.

## Verification

- encrypted header, wrong/missing key, corruption, restart, and plaintext-denial tests;
- explicit plaintext migration plus interrupted publication recovery;
- prior encrypted schema migration with an encrypted verified backup;
- encrypted backup/restore, corrupt-backup denial, rekey, and interrupted rekey recovery;
- recursive key-material scans across project/backup bytes, diagnostics, environment, and arguments;
- strict portable profile, credential-purpose, packaging notice, and frozen-module tests;
- seven-sample Windows performance report and task-level supply-chain checks;
- independent high-risk security review before task approval.

## Task links

- `CAP-02.S04.T04`
