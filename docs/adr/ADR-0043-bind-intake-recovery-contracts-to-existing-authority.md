---
id: ADR-0043
title: Bind intake recovery contracts to existing authority
status: Proposed
date: 2026-10-06
deciders: []
linked_tasks:
  - CAP-05.S01.T03
decision_scope: Documentary binding of T03 intake/recovery ports and additive v25 storage metadata to accepted workflow, rights, protection and migration decisions; no new security, scope, framework or release authority.
affected_paths:
  - packages/contracts/core-api/generated.ts
  - packages/contracts/core-api/openapi.json
  - packages/contracts/storage/sqlite-migration-recovery-v24.snapshot.json
  - packages/contracts/storage/sqlite-migration-recovery.schema.json
  - packages/contracts/storage/sqlite-profile.schema.json
  - packages/contracts/storage/sqlite-profile.v1.json
  - services/core-api/src/research_observatory_core/ports/acquisition.py
  - services/core-api/src/research_observatory_core/ports/document_attachments.py
  - services/core-api/src/research_observatory_core/ports/object_store.py
  - services/core-api/src/research_observatory_core/ports/workflow_executor.py
supersedes: []
superseded_by: null
---

# ADR-0043: Bind intake recovery contracts to existing authority

## Context

CAP-05.S01.T03 composes already approved local/remote acquisition, durable jobs,
fresh retained-candidate recovery and local access annotations. ADR-0025 governs
queue identity and atomic output/provenance; ADR-0027/0029 preserve copy rights,
original source observations and explicit researcher acceptance; ADR-0028 and
the accepted protection/migration decisions retain their exact boundaries.

The protected-path check found the implementation lacked a changed indexed
task-linked companion for ten portable/API/storage contracts. This Proposed record
documents their existing remit, as ADR-0042 does for T02. It creates no accepted
architecture decision and does not amend the frozen Wave packet.

## Candidates

1. Keep acquisition authority implicit in concrete adapter calls and replace
   original candidate/source records during recovery. This is smaller but
   violates the approved portability, immutable history and fresh-authority rules.
2. Compose typed ports and append-only relational projections under the existing
   document data adapter and canonical transactions. This requires explicit
   compatibility proof while preserving the accepted decisions. Use this detail.

## Decision

Single-attempt intake reuses the existing queue, admission/resources and exact
native-owned operation. Candidate, intake result, provenance, dependencies,
outbox and queue output publish atomically. Progress is factual; generic Retry
never restores transfer consent. Owned cleanup failure prevents unsafe dispatch.

Recovery appends an exact current actor/session/association/Intent/privacy/rights
basis without changing the original source, session or receipt. Attach separately
rechecks this basis. Local access notes grant neither permission nor availability.
Portable acquisition metadata and exact attached-revision protected reads supply
the downstream handoff; neither metadata nor a generic object hash grants access.

Schema v25 adds immutable intake/result/recovery/access-need projections. Current
profile/recovery metadata describe that additive version, and the v24 recovery
snapshot preserves the exact predecessor. No earlier migration, encrypted object
envelope, worker permission, parser choice or approved experience is replaced.

## Consequences

Windows x64 local/lab remains the target. The existing document adapter owns SQL;
portable/business modules receive no canonical connection or concrete repository.
New projections increase migration and recovery proof obligations. Verified
predecessor backup restoration remains the recovery route; old rows, history and
ciphertext survive all material interruption points. Security authority and the
three-attempt HTTP budget remain unchanged. EX01 separately governs exact 1.9
presentation admission; this record supplies no verification or release waiver.

## Verification

Fresh task checks cover queue admission, current authority, cleanup/cancellation,
restart/fresh confirmation, retained-copy distinctions and local notes without
egress. Literal v24 fixtures qualify additive v25 and interrupted recovery.
Owned HTTPS, SQLCipher, encrypted objects and signed LPAC exercise the real
principal handoff; protected reads reject substituted revisions and revoked
current inspect permission. Unchanged architecture/ADR checks and affected
quality/contracts/native/UI checks remain required. Preserve the initial missing
ADR and misplaced-adapter failures. Independent task and slice dispositions,
acquisition resource measurements, fresh W2 qualification and human release
remain separate obligations.

## Task links

- `CAP-05.S01.T03`
