---
id: ADR-0050
title: Bind table and figure observations to existing protected document authority
status: Proposed
date: 2026-10-10
deciders: []
linked_tasks:
  - CAP-05.S05.T03
decision_scope: Documentary implementation mapping of approved CAP-05.S05.T03 to accepted ADR-0013/0024/0027/0029; no new architecture, security, migration guarantee, experience or release authority.
affected_paths:
  - services/core-api/src/research_observatory_core/document_table_figures.py
  - services/core-api/src/research_observatory_core/document_table_figure_repository.py
  - services/core-api/src/research_observatory_core/table_figure_reader.py
  - services/core-api/src/research_observatory_core/document_revision*.py
  - services/core-api/src/research_observatory_core/object_store.py
  - packages/contracts/documents/**
  - apps/desktop/src/app/documentTableFigures*
  - apps/desktop/src/app/ViewerTableFiguresPane.tsx
  - apps/desktop/src/app/DocumentViewerWorkspace.tsx
  - apps/desktop/src-tauri/src/document_reader.rs
  - apps/desktop/src-tauri/src/supervisor.rs
  - apps/desktop/src-tauri/src/lib.rs
  - tests/documents/**
  - tests/desktop/**
supersedes: []
superseded_by: null
---

# ADR-0050: Bind table and figure observations to existing protected document authority

## Context

The approved task requires tables, figures, captions, reliable cell observations,
page anchors and original previews. The approved S05 contract also requires
explicit human exclusion of corrupted extraction while preserving original parse
output. Accepted ADR-0029 already supplies separate canonical encrypted
enrichment and bounded inspection. This Proposed record maps implementation to
existing decisions; it grants no new authority.

## Candidates

Rewriting accepted structure would disturb immutable approval. A separate
collection preserves that source and all earlier observations. A dense rendered
grid could multiply source-controlled dimensions; bounded sparse cell pages
retain merged/split observations and quality. An external graphic URL or stage
ID cannot establish protected original-image permission or exact semantics.

## Decision

Use the existing canonical writer, schema-28 table-figures kind/index, complete
material registration, encrypted object store, human provenance and atomic
outbox. Bind original and accepted source identity and every canonical node.
Native namespace/container and Docling caption relationships require the exact
authenticated retained artifact. Preserve caption ambiguity and missing headers,
raw/NFC cell text, reported spans, geometry, confidence and unverified status.

Extraction and deliberate human exclusion append revisions with expected-head
CAS and exact retry. An exclusion records the exact object, actor, command and
rationale; it preserves the original parse, earlier collections and exclusions
on subsequent refresh of this same source. Current Native/project/session/human,
Intent/privacy and inspect/derive fences span preparation, publication and
delivery. Cancellation or precommit failure rolls back all publication effects.

Use conservative cumulative admission before copying repeated spans and
serializing entries. No dense expansion is permitted. The approved Reader 1.9
regions show one object and a bounded cell page beside the existing protected
original page. Original preview references bind source revision/digest and
reported page region; cell-based fallback is explicit. Closed opaque Native
commands, inert text, exact source jumps, reasoned exclusion and lock/late
clearing preserve existing authority and resource ownership.

## Consequences

Accepted document v1, source bytes, literal schema-28 migration and storage
profile remain unchanged. No new identity store, parser/model/OCR invocation,
image URL fetch, scholarly verification, hardware minimum, automation-framework
development, new experience reference or release decision is introduced.
Unavailable source relationships and previews remain explicit.

## Verification

Focused authored adapter fixtures challenge native namespace ownership,
ambiguous captions, retained Docling bindings, sparse merged cells and rotated
source geometry. Actual encrypted repository and Core authority checks challenge
source/actor/rights substitutions, material registration, exact retry, exclusion
history, refresh, restart, cancellation and rollback. Closed Native/client,
mounted Reader and fresh shipping Windows journeys cover source jumps, original
page inspection, exclusion, pagination, keyboard/themes, return, admission and
late-response clearing. Authored IR proves wiring, not model quality.
Commit-bound evidence and independent disposition determine task completion.

## Task links

- `CAP-05.S05.T03`
