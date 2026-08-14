---
id: ADR-0012
title: Use relocatable versioned local project packages with classified storage
status: Accepted
date: 2026-08-13
deciders:
  - W1 repository-owner pre-Wave approval at 594e63be501711d67d17a4aef176bb9b6a8748be
linked_tasks:
  - CAP-02.S01.T01
decision_scope: Local project-root manifest, relative storage layout, authority classification, retention, backup, deletion, and portable-export membership.
affected_paths:
  - packages/contracts/project/**
  - packages/contracts/README.md
  - packages/contracts/package.json
  - packages/contracts/tsconfig.json
  - packaging/build-inputs.json
  - docs/architecture/project-package.md
  - docs/architecture/README.md
supersedes: []
superseded_by: null
---

# ADR-0012: Use relocatable versioned local project packages with classified storage

## Context

W1 needs a durable local project authority before database, encryption,
provenance, and workflow slices can persist their own state. Absolute paths make
backup and relocation fragile. A single opaque database hides which data is
canonical, rebuildable, transient, or safe to omit. A broad plaintext manifest
could also disclose sensitive research context or credentials.

The approved W1 packet selects a small non-sensitive root manifest, clearly
separated protected storage classes, atomic staged creation, and portable
project-relative paths. CAP-03 canonical identity is not yet available, so this
contract establishes a strict RFC 4122 UUIDv4 bridge for project identity.

## Candidates

1. Store all state in an application-global directory and keep project paths in
   preferences. This is simple but makes individual projects hard to inspect,
   relocate, restore, or delete safely.
2. Use a versioned directory package with a strict plaintext identity/format
   manifest, classified project-relative storage entries, and an explicit
   portable-export inventory.
3. Use a single archive or database file for everything. This offers a compact
   artifact but conflates canonical, cache, lock, log, and temporary state and
   makes crash-safe incremental work and recovery harder.

## Decision

Adopt candidate 2. A project root contains `project.ro.json` and the exact
layout in `packages/contracts/project/project-layout.v1.json`. The manifest
contains only identity, revision, package/layout versions, lifecycle state,
compatibility, storage-format identities, and timestamps. It contains no title,
research content, path, secret, key, endpoint, or provider field.

Every governed location is project-relative and classified as authoritative,
derived, cache, operational, or transient. Backup, deletion, retention, and
portable-export semantics are explicit for all ten storage classes. Portable
export includes only the manifest, database, encrypted objects, configuration,
and researcher exports. Shared model binaries remain outside the package.

## Consequences

Projects can move between roots without rewriting identity or manifest bytes.
Backup and deletion have an exact inventory, and transient or rebuildable state
cannot silently become portable authority. The fixed layout is intentionally
strict: adding a class, changing a path, or changing export membership requires
a new layout version and compatibility evidence.

The plaintext manifest cannot provide confidentiality and therefore carries no
sensitive display metadata. Database/object protection is identified here but
implemented by later CAP-02 slices. Creation, locking, quarantine, migration,
and safe-open behavior remain later tasks and must honor this contract.

Rollback removes the new project contract before any released project uses it.
After release, rollback requires a reader/bridge that preserves existing
packages; silently rewriting or ignoring the version is prohibited.

## Verification

- strict TypeScript manifest decoder success and hostile unknown/path/secret
  field denial;
- exact JSON-to-TypeScript layout binding;
- Windows and POSIX relative-path tests under two different roots;
- portable-inventory test proving every transient, rebuildable, cache, log, and
  lock class is excluded;
- JSON Schema Draft 2020-12 schema validation and architecture/ADR checks.
- schema/TypeScript parity attacks for UTC syntax and safe integers, plus the
  bound language-neutral semantic rules for compatibility and timestamp order;
- cross-language compatibility-version operands share the exact inclusive
  `0..9007199254740991` component domain before ordering.

## Task links

- `CAP-02.S01.T01`
