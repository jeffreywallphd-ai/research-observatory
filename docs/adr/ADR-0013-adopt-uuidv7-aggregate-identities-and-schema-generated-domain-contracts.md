---
id: ADR-0013
title: Adopt UUIDv7 aggregate identities and schema-generated domain contracts
status: Accepted
date: 2026-08-14
deciders:
  - W1 repository-owner pre-Wave approval at 594e63be501711d67d17a4aef176bb9b6a8748be
linked_tasks:
  - CAP-03.S01.T01
decision_scope: Portable aggregate and revision identity, UUID minting authority, common scholarly value objects, and deterministic Python/TypeScript generation from the core domain schema.
affected_paths:
  - packages/contracts/domain/**
  - packages/contracts/README.md
  - packages/contracts/package.json
  - packages/contracts/tsconfig.json
  - services/core-api/src/research_observatory_core/domain_contracts.py
  - tests/contracts/test_domain_contracts.py
  - packaging/build-inputs.json
  - quality-scope.json
  - docs/architecture/domain-contracts.md
  - docs/architecture/README.md
supersedes: []
superseded_by: null
---

# ADR-0013: Adopt UUIDv7 aggregate identities and schema-generated domain contracts

## Context

Research records, documents, evidence, decisions, workflows, ontologies,
graphs, opportunity candidates, and monitoring events need identities that
survive project relocation and later deployment-profile changes. Database row
numbers and file paths are not portable identities. A single mutable identifier
also cannot distinguish the stable scholarly object from an immutable revision.

Consumers in Python and TypeScript must agree on strict wire behavior without
making either language implementation authoritative. The contract must retain
exact observed wording and competing interpretations, distinguish unknown from
not reported or not applicable, and carry confidence and rights as typed
decisions. RFC 9562 and JSON Schema Draft 2020-12 are the governing external
standards rechecked for this implementation.

## Candidates

1. Expose database row identifiers and hand-maintain separate Python and
   TypeScript models. This is initially small, but it couples identity to one
   adapter and permits silent cross-language drift.
2. Use canonical UUIDv7 aggregate and revision identities, a separate safe
   integer revision counter, an authoritative Draft 2020-12 schema, and
   deterministically generated strict Python and TypeScript contracts.
3. Use content hashes as all identities. Hashes are appropriate for immutable
   bytes and derivations, but not for a stable scholarly aggregate whose
   interpretation advances through retained revisions.

## Decision

Adopt candidate 2. Newly minted durable aggregate and revision identities are
canonical lower-case RFC 9562 UUIDv7 values. The Core service is the only
current minting authority and uses operating-system cryptographic randomness;
clients validate identities but do not mint durable authority. Aggregate ID is
stable, revision ID is immutable and distinct, and the non-negative safe integer
revision provides optimistic-concurrency ordering.

`packages/contracts/domain/domain-core.schema.json` is the exact
language-neutral wire authority. It defines the principal aggregate envelope
and value objects for source anchors, exact observed text, disputed
alternatives, epistemic status, confidence, rights, and external identifiers.
Unknown fields fail closed. Cross-field rules that JSON Schema cannot express
portably are declared as data in the schema and executed identically by both
generated runtimes.

`packages/contracts/domain/generate.mjs` deterministically emits the
TypeScript contract and the dependency-neutral Python contract used by Core.
The generated files embed the raw schema SHA-256; `--check` rejects drift.

The version-1 local project manifest remains the explicit UUIDv4 bridge recorded
by ADR-0012. It is not silently reinterpreted as UUIDv7. CAP-03.S01.T03 must
publish the compatible bridge or migration before a persisted canonical
aggregate relies on that legacy project identity.

## Consequences

Portable identities no longer encode a machine path, user identity, provider,
or database adapter. Time ordering is available at millisecond granularity, but
UUID ordering is not accepted as scholarly chronology; recorded UTC instants
and revisions remain authoritative. UUIDv7 is not a secret or authorization
token and callers must not treat it as unguessable authority.

Observed wording and disputed alternatives coexist instead of destructive
normalization. Rights states fail closed: unknown rights grant no use, and an
allowed or denied decision requires a source reference. The common envelope is
deliberately small; aggregate-specific lifecycle and transition rules belong to
CAP-03.S01.T02, and compatibility/deprecation rules belong to T03.

Generated artifacts add a reviewable build step, but the generator, schema
hash, cross-language fixtures, and strict decoders make drift deterministic.
Rollback is safe before any canonical aggregate is persisted. After that point,
rollback requires a reader and migration that retain every aggregate/revision
identity and observed alternative.

## Verification

- Draft 2020-12 schema validation with valid, disputed, UUIDv4, path-bearing,
  rights, and malformed-dispute fixtures;
- deterministic generation and raw schema SHA-256 binding;
- TypeScript typecheck and strict decoder tests;
- Python typing, strict decoder parity, and the RFC 9562 UUIDv7 test vector;
- architecture/ADR checks and exact build schema inventory.

## Task links

- `CAP-03.S01.T01`
