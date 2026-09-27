---
id: ADR-0031
title: Document exact scholarly reconciliation under existing canonical authority
status: Proposed
date: 2026-09-27
deciders: []
linked_tasks:
  - CAP-04.S03.T01
decision_scope: Documentary association of exact reconciliation with accepted ADR-0013, ADR-0024, ADR-0025 and ADR-0027; this Proposed record grants no new authority.
affected_paths:
  - packages/contracts/scholarly-records/**
  - packages/contracts/core-api/generated.ts
  - packages/contracts/core-api/openapi.json
  - packages/contracts/storage/**
  - services/core-api/src/research_observatory_core/reconciliation/**
  - services/core-api/src/research_observatory_core/reconciliation_api.py
  - services/core-api/src/research_observatory_core/reconciliation_repository.py
  - services/core-api/src/research_observatory_core/reconciliation_service.py
  - services/core-api/src/research_observatory_core/ports/reconciliation.py
  - services/core-api/src/research_observatory_core/ports/connector_runtime.py
  - services/core-api/src/research_observatory_core/storage.py
  - services/core-api/src/research_observatory_core/migrations/runner.py
  - services/core-api/src/research_observatory_core/migrations/versions/v0014_scholarly_reconciliation.py
  - tools/core_api_contract.py
  - tools/architecture_check.py
  - quality-scope.json
  - verification-profiles.json
supersedes: []
superseded_by: null
---

# ADR-0031: Document exact scholarly reconciliation under existing canonical authority

## Context

CAP-04.S03.T01 must reconcile retained scholarly observations while preserving
their source identity, uncertainty and current access restrictions. Accepted
ADR-0027 already permits unique valid exact identifiers to auto-link and reserves
conflicts for human review. ADR-0013/0024 own canonical UUIDv7 identity and atomic
repository publication; ADR-0014 owns strict typed storage; ADR-0025 owns durable acquisition jobs. The approved W2
packet remains immutable. This companion documents their application at the new
portable interface and additive schema boundary required by ADR-0001.

## Candidates

1. Trust normalized provider values or client-supplied source grants. This is
   simpler but can lose DOI case distinctions and bypass current authority.
2. Resolve exact retained source addresses inside Core, normalize raw observations,
   and atomically append canonical revisions and source links. This requires
   explicit source adapters and a backed-up migration but preserves the existing
   authority and audit boundaries.
3. Fetch registry verification during every match. This adds egress and availability
   requirements and conflates local syntax validation with external evidence.

## Decision

Implement candidate 2 under the accepted decisions. Normalization is versioned
and never upgrades an unverified observation to verified. DOI/PMID/arXiv/ISBN
and typed provider IDs can supply exact keys only in their proper entity scope.
Titles, locations and person IDs cannot merge Works. Unique compatible matches
append an inferred link; invalid, reassigned or conflicting keys append a disputed
assertion without changing a Work. Competing fields remain inspectable; accepted
source corrections take precedence without destroying raw observations.

Source addresses bind project, import manifest/member/key or accepted connector
page/ordinal. The authenticated API accepts addresses and command IDs, not grants
or provider payloads. Current project, accepted Intent, privacy and every source's
inspect/store/derive/index rights guard writes, replay and inspection. Local reads
do not renew old network consent or initiate remote lookup.

The project lifecycle fence spans resolution and publication. Protected source
reads may append access audit facts on a separate connection, so they precede the
writer transaction. Publication rechecks indexed candidates against the resolved
snapshot and fails closed if concurrency exposes an unresolved source. Existing
canonical transactions atomically publish revisions, provenance, outbox,
dependencies, exact-key links and idempotency. One bounded source is synchronous;
batch acquisition remains in existing durable jobs.

## Consequences

Schema 14 adds four append-only tables; it changes no existing source records or
accepted decisions. `assertion_json` contains only the versioned SourceAssertion
contract with database-enforced schema/project/source/address identity checks and
strict model validation on write/read; it is not an arbitrary payload extension.
The existing scalar-storage and no-generic-payload tests remain unchanged.
The frozen populated schema-13 predecessor is retained before
DDL edits. The existing migration runner validates its fingerprint, verifies a
protected backup, and advances schema/history in one transaction. Failure restores
the original transaction state; no automatic destructive downgrade is introduced.
An older binary explicitly rejects the newer schema. Retain the verified backup
for the established recovery procedure if reverting application code.

The JSON/OpenAPI/generated TypeScript contract exposes immutable IDs, bounded
dispositions, raw observations and normalization provenance only through authorized
inspection. Private values remain in protected storage and never become default
diagnostic labels. Conservative matching can produce additional human review,
especially for conflicting provider groupings or ISBNs whose subject scope is
unknown. Windows x64 is the qualification target. No governed UI, security grant,
new library, external service, fuzzy scoring or version-graph authority is added.

## Verification

`tests/reconciliation` challenges equivalence, source encodings, entity scope,
transitive bridges, conflicts, field precedence, concurrent writers, atomic
rollback, exact predecessor migration and encrypted backup/reopen. Its production
Core test exercises actual import and retained connector handoffs with Windows
DPAPI/SQLCipher, current-rights denial, offline local replay and application restart.
Only the external provider response is synthetic.

Generated-contract drift, schema validation, affected migration-chain regression,
architecture dependency checks, Python quality and independent commit-bound review
complete task qualification. Slice/checkpoint and fresh Wave qualification remain
separate obligations; this Proposed record is not an approval or completion claim.

## Task links

- `CAP-04.S03.T01`
