---
id: ADR-0049
title: Bind citation contexts to existing canonical and protected document authority
status: Proposed
date: 2026-10-10
deciders: []
linked_tasks:
  - CAP-05.S05.T02
decision_scope: Documentary implementation mapping of approved CAP-05.S05.T02 to accepted ADR-0013/0024/0027/0029; no new architecture, security, migration guarantee, experience or release authority.
affected_paths:
  - services/core-api/src/research_observatory_core/document_citations.py
  - services/core-api/src/research_observatory_core/document_citation_repository.py
  - services/core-api/src/research_observatory_core/citation_reader.py
  - services/core-api/src/research_observatory_core/document_reference_repository.py
  - services/core-api/src/research_observatory_core/document_revision*.py
  - services/core-api/src/research_observatory_core/object_store.py
  - packages/contracts/documents/**
  - apps/desktop/src/app/documentCitations*
  - apps/desktop/src/app/ViewerCitationsPane.tsx
  - apps/desktop/src/app/DocumentViewerWorkspace.tsx
  - apps/desktop/src-tauri/src/document_reader.rs
  - apps/desktop/src-tauri/src/supervisor.rs
  - apps/desktop/src-tauri/src/lib.rs
  - tests/documents/**
  - tests/desktop/**
supersedes: []
superseded_by: null
---

# ADR-0049: Bind citation contexts to existing canonical and protected document authority

## Context

The approved task requires source-preserving citation markers, sentence and
paragraph context, locations and explicit multi-target resolution. Accepted
document v1 and its immutable human approval remain authoritative. Accepted
ADR-0029 already requires separate canonical encrypted enrichment, exact current
reference inputs and bounded protected Reader inspection. This Proposed record
maps those decisions to the implementation; it does not approve new authority.

## Candidates

Rewriting accepted structure would simplify lookup but change historical human
approval. A separate canonical citation collection preserves the accepted
revision and allows explicit refresh and exact retry. Flattened text inference
alone could misclassify footnote callouts and lose exact locations; authenticated
native roles and spans preserve reported markers, while conservative text
patterns remain explicitly inferred.

## Decision

Implement the separate protected citation collection under the existing
canonical writer and reserved enrichment kind. Bind the accepted document and
exact current reference collection, including its protected payload digest.
Preserve raw and NFC spans, source order, canonical marker identity when reported,
and each target member. Missing and ambiguous targets remain explicit. Reference
subtrees and nonbibliographic callouts do not become inferred citations.

Native source roles and attributes are authenticated retained parser data, never
instructions or permission. Derivation and each Reader delivery require current
source and target authority, human actor, Intent and privacy epoch. Publication
retains existing compare-and-swap, provenance, material dependencies, atomic
outbox, retry and cancellation semantics. Every extraction, association and
confidence observation remains unverified; no Work is created or adjudicated.

The approved Reader 1.9 contract supplies bounded one-context inspection,
explicit refresh, exact node-relative source jumps, target inspection and safe
clearing on lock, substitution or late response. Fixed Native commands carry
opaque IDs only. Core controls protected reads and bounded delivery.

## Consequences

The literal schema-28 migration, storage profile and accepted document v1 schemas
remain byte-for-byte unchanged. Existing canonical IDs and indexes are reused;
no second identity store or accepted-document mutation is introduced. Context
truncation, unavailable offsets and unsupported source relationships are explicit.
There is no model run, new hardware minimum, external destination, clipboard
action, automation-framework change, governed experience change or release claim.

## Verification

Focused tests cover reported and inferred citation styles, multi-target missing
and ambiguity, exact Unicode/raw anchors, native roles and nonbibliographic
callouts. Actual protected repository and Core checks cover current reference
and rights substitution, encrypted publication, exact retry, refresh, restart,
cancellation and rollback. Strict client and mounted Reader checks cover bounded
inert text, source navigation, pagination, admission and late-response clearing.
Fresh shipping Windows Native/Reader proof supplements explicitly synthetic
parser fixtures. Commit-bound evidence and independent disposition decide task
completion; this documentary mapping does not replace them.

## Task links

- `CAP-05.S05.T02`
