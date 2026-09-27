---
id: ADR-0032
title: Document duplicate review under existing canonical authority
status: Proposed
date: 2026-09-27
deciders: []
linked_tasks:
  - CAP-04.S03.T02
decision_scope: Documentary association of approved duplicate review with accepted ADR-0013, ADR-0014, ADR-0024, ADR-0025 and ADR-0027; no new authority.
affected_paths:
  - packages/contracts/**
  - services/core-api/src/research_observatory_core/ports/reconciliation.py
  - services/core-api/src/research_observatory_core/ports/connector_runtime.py
  - services/core-api/src/research_observatory_core/ports/import_commits.py
  - services/core-api/src/research_observatory_core/ports/workflow_executor.py
  - services/core-api/src/research_observatory_core/reconciliation/**
  - services/core-api/src/research_observatory_core/reconciliation_repository.py
  - services/core-api/src/research_observatory_core/reconciliation_service.py
  - services/core-api/src/research_observatory_core/reconciliation_worker.py
  - services/core-api/src/research_observatory_core/repositories.py
  - services/core-api/src/research_observatory_core/storage.py
  - services/core-api/src/research_observatory_core/migrations/versions/v0015_reconciliation_review.py
  - quality-scope.json
  - packaging/build-inputs.json
supersedes: []
superseded_by: null
---

# ADR-0032: Document duplicate review under existing canonical authority

## Context

Approved CAP-04.S03.T02 requires explainable fuzzy candidates, human merge/split
review, preserved conflicting source fields and reversible identities. The
immutable W2 packet and reference 1.7 already authorize this outcome. ADR-0001
requires an indexed companion for its protected interfaces. This Proposed record
documents application of accepted decisions; it does not approve a new database,
algorithm authority, security grant, experience or Wave scope.

## Candidates

1. Collapse likely duplicates into mutable records. This loses source assertions,
   ambiguous alternatives and reversible researcher judgments.
2. Retain immutable source assertions and candidate evidence, then append explicit
   researcher-directed membership and alias revisions through existing canonical
   transactions, provenance, dependency impact and durable jobs.
3. Delegate identity authority to a remote provider. This introduces egress and
   availability requirements outside the approved local review task.

## Decision

Implement candidate 2 within the accepted architecture. Scores are versioned
ranking evidence, never probabilities or automatic fuzzy merge authority. Every
pair retains feature contributions and conflicting/missing states. The frozen
licensed DBLP-ACM fixture, source hashes, split, thresholds and scoring freeze
remain inspectable; later runs disclose that qualification labels are known.

The accepted-output inventory authenticates source-owner manifests and workflow
completion, including continuation branches. Its immutable snapshot bounds a
durable job. Current project, accepted Intent, policy, native session and source
rights remain authoritative at inspection, derivation, cancellation and retry.
Renderer input supplies neither actors nor rights. Native and generated-client
validation retain closed DTOs, bounded bodies and exact identity binding.

Human review previews a complete source partition, survivor and alias plan, then
appends Work revisions, preserved assertions, decision provenance, outbox and
dependency intent atomically. An ambiguous response retains the same command.
Historical receipts do not become current membership. Revision-qualified reads
retain history, while current resolution follows explicit sealed membership and
alias routes. The existing impact engine owns checkpoints and freshness denial;
resumable owner recovery must preserve its snapshot and authority validation.

Exact commands and review outcomes retain immutable root-impact ownership. If
later graph growth invalidates a pending preview, owner recovery verifies sealed
run fields, saved items and checkpoints, re-previews the same saved semantics,
and atomically appends a continuation link and predecessor cancellation. Previous
impact items and stale causes remain authoritative. Continuation depth is bounded
at 128; exhaustion denies further automatic recovery and retains pending/stale
state. This is a resource limit, not a guarantee of completion under continuing
graph changes. Existing impact validation and manually cancelled terminal states
remain intact.

## Consequences

Additive unreleased schema 15 extends typed canonical metadata; dedicated bounded
feature, candidate-set and explanation documents reject unknown fields and
invalid shape at storage and adapter boundaries. It does not introduce arbitrary
payload storage. Every new identity, ownership link and trigger belongs in the
exact inventory and fingerprint. Frozen populated schema-14 fixtures and the
published v14 migration remain unchanged. Existing verified backup, transactional
failure recovery and fingerprint checks continue to reject incompatible files.

The review UI implements existing ingestion regions and shared controls under
reference 1.7. Current denial clears protected evidence. It distinguishes pending
dependency propagation from completed recalculation and makes no invented source,
registry verification, scholarly validity or acceptance-probability claim.

## Verification

Criterion-linked proof covers frozen retrieval metrics, ambiguity and conflicting
fields, current authority, atomic publication, source-owner substitution, complete
partitions, aliases, retry, cancellation, migration and restart. Actual browser,
generated-client, native supervisor and encrypted Core tests establish the local
principal boundary. Focused conformance, schema inventory, types, architecture,
build and independent review remain mandatory; this record asserts no passing
qualification by itself.

## Task links

- CAP-04.S03.T02 implements the approved duplicate-candidate and reversible review
  contribution. Version/correction/retraction relationships remain T03 scope.
