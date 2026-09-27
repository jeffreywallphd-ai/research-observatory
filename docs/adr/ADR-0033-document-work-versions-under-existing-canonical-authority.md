---
id: ADR-0033
title: Document work versions under existing canonical authority
status: Proposed
date: 2026-09-27
deciders: []
linked_tasks:
  - CAP-04.S03.T03
decision_scope: Documentary implementation record for approved W2 WorkVersion contracts, additive schema v16, and existing reconciliation port extensions; no new architecture or product authority.
affected_paths:
  - packages/contracts/**
  - services/core-api/src/research_observatory_core/ports/reconciliation.py
  - services/core-api/src/research_observatory_core/reconciliation*
  - services/core-api/src/research_observatory_core/storage/**
  - services/core-api/src/research_observatory_core/storage.py
  - services/core-api/src/research_observatory_core/migrations/runner.py
  - quality-scope.json
  - packaging/build-inputs.json
supersedes: []
superseded_by: null
---

# ADR-0033: Document work versions under existing canonical authority

## Context

CAP-04.S03.T03 implements the frozen W2 packet at
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`. Accepted ADR-0013/0014/0024
govern canonical identity, repository transactions, provenance and encrypted
storage; ADR-0025 governs durable work; ADR-0027 separates scholarly Work,
WorkVersion and source assertions, retains human decisions and requires current
rights. This Proposed record accompanies protected-interface changes under
ADR-0001. It neither supersedes those decisions nor confers additional approval.

The predecessor at `0738c2543db85af8189bd0948393698b04662de6` implements
schema v15 with canonical Work membership and merge/split history. Literal v15
DDL and populated synthetic rows were captured before implementation, including
partial dependency impacts, and remain immutable compatibility fixtures.

## Candidates

1. Store version/status fields in a renderer or source-record projection. This
   is simple to display, but cannot own immutable decisions or reliably preserve
   competing assertions, source rights and exact predecessor identity.
2. Extend canonical aggregates and the existing reconciliation port with typed
   version, directed relationship and explicit preference revisions. This needs
   additive subtype tables and bounded contracts, but preserves the accepted
   identity, transaction, policy and recovery boundaries.

## Decision

The approved implementation follows candidate 2. WorkVersion is a canonical
object with exact source assertion revisions, manifestation kind and explicit
date precision. Directed update relationships bind exact version revisions and
retained source selectors/value digests. Preferences are explicit human decisions;
changed membership, version or warning evidence requires renewed review. A
preference never suppresses a warning or grants rights.

Core authorizes current project/Intent/source rights for reads, previews, writes
and identical retries. Atomic publication retains provenance/outbox facts,
owned dependency impacts and canonical history. A preference materially depends
on its newly published Work head; old preference decisions cannot reactivate
after a merge/split round trip. Version-owned recovery authenticates the decision,
published endpoints, checkpoint and impact semantics.

The existing port and generated client expose bounded work inventory, context,
history, preview and commit operations. Native admission validates request shape
without claiming policy authority. A definitive pre-publication stale refusal
uses `RO-CORE-RECONCILIATION-VERSION-NOT-APPLIED`; generic conflicts and lost
replies retain the exact command because publication may already have occurred.
The approved Ingestion Review region preserves drafts, requires fresh evidence
after definitive refusal, and clears protected state on denial/close.

The governed Python inventory includes the new domain and tests. Packaging binds
the new portable schema files. Neither changes module direction or relaxes checks.

## Consequences

Schema v16 adds seven normalized tables and canonical subtype constraints. The
backed migration preserves literal v15 rows and fingerprints, publishes no
invented versions, and restores the predecessor after interruption. Rollback uses
the verified encrypted backup through existing migration recovery; older software
must not open an unsupported newer schema. Portable fixtures distinguish synthetic
illustrative record keys from byte-exact predecessor evidence.

History and unresolved membership increase storage and review complexity, but
prevent silent scholarly reclassification. Contexts and requests have explicit
size limits; source content stays encrypted and local. Denied/unknown rights
remain restrictive and all output is inert text. W2 qualifies Windows x64 LOC/LAB;
this adds no hosted deployment, new provider, credential or cross-platform claim.

## Verification

`tests/reconciliation/test_versions.py`, `test_version_repository.py`,
`test_version_api.py`, `test_version_client.py`, `test_version_migration.py`,
`test_renderer.py` and `test_native_renderer.py` exercise identities, source
substitution, dates, current rights, concurrent decisions, exact retry, history,
atomic faults, partial/cancelled/restarted impacts and the Windows principal path.
The task evidence records the exact executed case inventory and qualifications.
Literal v15 plaintext and SQLCipher migrations cover interruption and backup
restoration. Generated-contract, shared storage/API, dependency-impact, native
admission, affected quality, architecture, ADR, UI-reference and build-manifest
checks accompany independent commit-bound disposition. Full slice performance
and fresh Wave qualification remain separate obligations.

## Task links

- `CAP-04.S03.T03`
