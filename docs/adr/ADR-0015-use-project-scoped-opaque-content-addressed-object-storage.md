---
id: ADR-0015
title: Use project-scoped opaque content-addressed local object storage
status: Accepted
date: 2026-08-17
deciders:
  - W1 repository-owner pre-Wave approval at 594e63be501711d67d17a4aef176bb9b6a8748be
linked_tasks:
  - CAP-02.S03.T01
  - CAP-02.S03.T02
  - CAP-02.S03.T03
decision_scope: Plaintext content identity, project deduplication scope, opaque physical identity, durable versus rebuildable classification, atomic publication, reference authority, verified streaming, and the staged encryption handoff.
affected_paths:
  - packages/contracts/storage/**
  - packages/contracts/README.md
  - services/core-api/src/research_observatory_core/object_store.py
  - services/core-api/src/research_observatory_core/ports/**
  - services/core-api/packaging/sidecar-build.json
  - tests/contracts/test_object_store_contract.py
  - tests/data/test_local_object_store.py
  - tests/foundation/test_architecture_check.py
  - tests/packaging/test_core_sidecar_package.py
  - tools/architecture_check.py
  - tools/core_sidecar_build.py
  - packaging/build-inputs.json
  - quality-scope.json
  - docs/architecture/local-object-storage.md
  - docs/architecture/README.md
supersedes: []
superseded_by: null
---

# ADR-0015: Use project-scoped opaque content-addressed local object storage

## Context

W1 must store large documents and derived artifacts locally without relational
BLOBs, cross-project equality disclosure, partial-file visibility, unrestricted
decrypted paths, or counters that can drift from canonical references. The Wave
packet selected an encrypted content-addressed project store with atomic writes
and manifest verification. CAP-02.S03 separates the stable T01 identity/port from
T02 encryption and T03 quota/garbage-collection policy.

## Candidates

1. Store object bytes in SQLite BLOB columns. This simplifies transaction scope
   but expands WAL/backup cost and conflates large byte storage with relational
   authority.
2. Store files directly under plaintext SHA-256 names and maintain a mutable
   reference counter. This is simple but reveals equality in directory listings
   and permits counter drift.
3. Use project-scoped content identity with opaque deterministic physical names,
   atomic complete-file publication, SQLite metadata, and counts derived from
   canonical references. This preserves replacement and recovery boundaries.

## Decision

Adopt candidate 3. Plaintext SHA-256 is the immutable project-local content
identity. HMAC-SHA-256(project identity, content identity) derives the physical
name; it is opacity rather than a confidentiality claim. No bytes or paths enter
SQLite and no cross-project deduplication occurs. Complete files are fsynced and
verified before create-if-absent publication, and metadata is committed last.

Open verifies exact held bytes before returning a controlled stream. The first
reference authority is the immutable `documents` relation, so T01 derives counts
and denies referenced deletion. Durable `project-lifetime`/`export-retained`
objects remain distinct from `derived-rebuildable` objects. T03 broadens the
reference graph and owns mark/sweep, leases, quota, and cache eviction.

T01's `plaintext-fixture-v1` protection profile is an intermediate implementation
seam, never a release claim for sensitive data. T02 must replace it with reviewed
authenticated streaming encryption and versioned key wrapping while preserving
the content identity and port.

## Consequences

Duplicate bytes occupy one file within a project and never deduplicate across
projects. A crash can leave an invisible complete orphan or partial staging file,
both recoverable without a visible metadata row. Corruption is unavailable before
first-byte use and advances metadata to quarantine. HMAC with a public project
identity prevents direct hash display but does not resist an actor who already
knows both project identity and candidate content; encryption remains mandatory.

The port is deployment-neutral. A later hosted adapter may use different physical
keys while retaining the same project/content identity, rights, retention, and
verified-stream semantics. Rollback before T02 removes the adapter and its
unreferenced fixture data; after durable project use, rollback requires a reader
for the profile and cannot discard referenced bytes or metadata.

## Verification

- Draft 2020-12 validation of the exact object-store profile;
- dependency-neutral port and concrete-adapter architecture attacks;
- duplicate/project-scope/opaque-name/restart streaming integration;
- interruption, hash mismatch, rights denial, hardlink, corruption, and
  referenced-delete failure tests;
- packaging inventory and build-manifest binding before slice approval.

## Task links

- `CAP-02.S03.T01`
- `CAP-02.S03.T02`
- `CAP-02.S03.T03`
