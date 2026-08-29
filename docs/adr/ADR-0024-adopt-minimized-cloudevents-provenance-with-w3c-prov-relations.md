---
id: ADR-0024
title: Adopt minimized CloudEvents provenance with W3C PROV relations
status: Accepted
date: 2026-08-29
deciders:
  - W1 repository-owner pre-Wave approval at c5bbd97c0cdc665eecb973f5862478ef7be97752
linked_tasks:
  - CAP-03.S03.T01
  - CAP-03.S03.T02
decision_scope: Portable scholarly-provenance event envelope, W3C PROV entity/activity/agent relations, schema evolution, content minimization and retention declarations, and RFC 8785 canonical record/hash-checkpoint boundaries.
affected_paths:
  - packages/contracts/provenance/**
  - packages/contracts/README.md
  - packages/contracts/package.json
  - packages/contracts/tsconfig.json
  - services/core-api/src/research_observatory_core/provenance_contracts.py
  - services/core-api/packaging/sidecar-build.json
  - tools/core_sidecar_build.py
  - tests/contracts/test_provenance_contracts.py
  - tests/packaging/test_core_sidecar_package.py
  - packaging/build-inputs.json
  - quality-scope.json
  - docs/architecture/provenance-contracts.md
  - docs/architecture/README.md
supersedes: []
superseded_by: null
---

# ADR-0024: Adopt minimized CloudEvents provenance with W3C PROV relations

## Context

Research Observatory must reconstruct how material sources, transformations,
evidence, decisions, syntheses, exports, and invalidations were produced without
event-sourcing all application state. Existing SQLite provenance rows are a
content-free transaction/audit seam, but they do not yet define a portable
cross-capability Entity/Activity/Agent model or a versioned event envelope.

The contract has to work unchanged across the local SQLite and later server
adapters, correlate with operational traces without retaining telemetry, and
carry enough exact identity for deterministic lineage. At the same time,
research content, prompts, paths, personal names, email addresses, credentials,
and provider secrets must not become routine ledger metadata. W3C PROV-O,
CloudEvents 1.0, RFC 8785, W3C Trace Context, and the approved CAP-03 decision
packet constrain the boundary.

## Candidates

1. Add mutable audit columns to every domain table. This is initially small,
   but cannot represent many-to-many derivations, responsible agents, retained
   alternatives, or superseding history.
2. Fully event-source canonical application state. This yields one history, but
   unnecessarily couples aggregate reconstruction, migration, privacy, and
   availability to every historical event and conflicts with the accepted
   relational-current-state architecture.
3. Keep relational current state and immutable revisions authoritative, while
   emitting a strict append-only W3C PROV-aligned event through the same
   transaction/outbox boundary. Use a CloudEvents-compatible envelope, protected
   payload references, and deterministic canonical hashes/checkpoints.

## Decision

Adopt candidate 3. The portable `research-observatory` provenance contract uses
CloudEvents 1.0 required attributes (`specversion`, `id`, `source`, `type`) plus
`subject`, occurrence `time`, versioned `dataschema`, JSON content type, and
lower-case extension attributes for project, actor, correlation, causation,
W3C `traceparent`, sensitivity, retention, and event schema version.

Each event contains exactly one bounded `ProvenanceActivity`, one opaque
`ProvenanceAgent`, immutable input/output `ProvenanceEntity` references, typed
PROV relations, and one versioned configuration reference. Stable project IDs
retain the existing UUIDv4 bridge or UUIDv7; event, entity/revision, activity,
agent, correlation, causation, and relation identities are UUIDv7. Known v1
types cover acquisition, parsing, extraction, verification, decisions,
synthesis, export, and invalidation. A structurally valid future type remains
storable but is explicitly not interpreted until a compatible reader catalogs
it.

The envelope contains references and bounded classifications, never raw
research or personal content. Optional large or sensitive event data is an
opaque protected-object reference; there is no inline payload escape hatch.
Every event and entity declares one closed sensitivity and retention class.
Retention may remove protected payloads under policy while retaining a
content-free tombstone where lawful; it never rewrites an event in place.

Canonical record bytes use the RFC 8785 ordering/serialization rules over this
schema's deliberately restricted I-JSON subset: strings, booleans, null,
arrays, and objects; no arbitrary floating-point or free-form values. The
Python runtime exposes the exact `sha256:` record identity. T02 will persist
those record hashes and create segment/checkpoint hashes. A canonicalization or
hash-algorithm change starts a declared new segment and never rehashes prior
events in place. Hashes detect accidental or unsupported mutation; they are not
a claim of nonrepudiation, trusted timestamping, or integrity against a fully
compromised host.

## Consequences

Cross-capability producers receive one deployment-neutral schema and matching
immutable TypeScript/Python decoders. Inputs, outputs, actors, configuration,
project identity, time, and trace become mandatory and relation completeness is
validated before persistence. Personal and scholarly content stays in protected
objects governed by its own rights and retention policy.

The first portable provenance schema is additive to the current SQLite audit
seam. T01 does not reinterpret or migrate existing narrow rows; T02 owns the
append-only ledger migration, atomic write, outbox projection, lineage queries,
and prior-row bridge. Unknown future event types can be retained safely, but no
query or UI may assign them meaning without a compatible catalog/upcaster.

More identities and relations increase row/index volume. T02 therefore owns
paged queries, project/time/type/subject/correlation indexes, bounded traversal,
and checkpoint cadence. Rollback before T02 persistence removes the unused
contract. After portable events exist, rollback must retain their exact bytes,
hashes, identities, sensitivity/retention declarations, and unknown types.

## Verification

- Draft 2020-12 schema and valid fixture validation;
- deterministic generator and exact schema-SHA binding;
- equivalent TypeScript and Python success, hostile-input, actor/time/project,
  relation-completeness, unknown-future-type, immutable-snapshot, and canonical
  restart/hash tests;
- package/type checks and frozen-sidecar module inventory;
- architecture/ADR, build schema inventory, quality, service, and data checks;
- T02 integration tests for atomic persistence, retry, restart, lineage,
  checkpoint mismatch, and prior-row compatibility.

## Task links

- `CAP-03.S03.T01`
- `CAP-03.S03.T02`
