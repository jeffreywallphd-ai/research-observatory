---
id: ADR-0051
title: Bind parsing quality triage to existing protected document authority
status: Proposed
date: 2026-10-10
deciders: []
linked_tasks:
  - CAP-05.S06.T01
decision_scope: Documentary implementation mapping of approved CAP-05.S06.T01 to accepted ADR-0029; no new architecture, security, migration guarantee, experience or release authority.
affected_paths:
  - quality-scope.json
  - services/core-api/src/research_observatory_core/parsing/quality.py
  - services/core-api/src/research_observatory_core/document_revision*.py
  - packages/contracts/documents/**
  - tests/documents/test_parsing_quality*.py
  - docs/architecture/document-parsing.md
supersedes: []
superseded_by: null
---

# ADR-0051: Bind parsing quality triage to existing protected document authority

## Context

Accepted ADR-0029 requires separate parsing dimensions, explicit missing and
ambiguous observations, review triage and immutable original/accepted history.
CAP-05.S06.T01 supplies the Core diagnostic path; CAP-05.S06.T02 owns the
desktop correction interaction. This Proposed mapping grants no new authority.

## Candidates

A combined correctness score would obscure missing confidence and overstate
machine output. Mutating the original parser quality record during rule changes
would obscure history. A separate versioned projection over exact retained
inputs preserves both and can diagnose failure before an accepted revision.

## Decision

Use a read-only Native Core query bound to the durable parse job, current
physical attempt, recorded selection/input digest, exact source and nullable
retained result. Expose named dimensions and versioned review reasons. Failed,
cancelled and pending jobs have unavailable observations, not invented IR or
measured zero. Native expected blocks require the exact authenticated retained
native artifact; absent scholarly expectations otherwise remain unknown.

Reuse current Native/project/human/Intent/privacy and exact-source inspect/derive
fences, cumulative protected-artifact admission and the lifecycle stop latch.
Cap diagnostic items before flattening, check the cooperative operation deadline
and cap the report. Warning details remain protected in the original output.
Confidence below 0.8 only routes a reported observation to review; it never
establishes correctness, blocks human inspection or changes scholarly state.

## Consequences

Original IR v1, source bytes, accepted revisions, IDs, provenance, schema-28
storage and accepted human decisions remain unchanged. Rule re-evaluation is
deterministic from durable inputs and definition/rule versions after reopen.
No database migration, model, OCR, network, hardware claim, new desktop pattern
or shared automation development is introduced. Coverage of retained normalized
projections does not establish recall of all original source text.

The existing quality-scope declaration registers exactly four new Python files:
the product quality module and its three focused document test modules. Its
governed roots, checker, rules, thresholds and shared harness remain unchanged.

## Verification

Frozen authored text/native/PDF/rich fixtures exercise separate dimensions,
missing-page/anchor/block failures, ambiguity, confidence states and the exact
0.8 threshold. Real encrypted repository tests cover partial output before
acceptance, queued/failed/cancelled jobs, immutable history, restart and resource
denial. Actual Native Core/Windows vault/SQLCipher tests cover current rights,
actor/Intent/privacy substitutions, stale sessions and stopped delivery.
Authored parser output proves diagnostic wiring, not model or scholarly quality.
Commit-bound checks and independent disposition determine task completion.

## Task links

- `CAP-05.S06.T01`
