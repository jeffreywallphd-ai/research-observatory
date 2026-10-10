---
id: ADR-0048
title: Bind reference enrichment to existing canonical matching and protected document authority
status: Proposed
date: 2026-10-10
deciders: []
linked_tasks:
  - CAP-05.S05.T01
decision_scope: Documentary implementation mapping of approved CAP-05.S05.T01 to accepted ADR-0013/0024/0027/0029; no new architecture, security, migration guarantee, experience or release authority.
affected_paths:
  - services/core-api/src/research_observatory_core/document_reference*.py
  - services/core-api/src/research_observatory_core/reference_*.py
  - services/core-api/src/research_observatory_core/reconciliation_repository.py
  - services/core-api/src/research_observatory_core/document_revision*.py
  - services/core-api/src/research_observatory_core/main.py
  - services/core-api/src/research_observatory_core/object_store.py
  - services/core-api/src/research_observatory_core/document_viewer_allocations.py
  - services/core-api/src/research_observatory_core/storage.py
  - services/core-api/src/research_observatory_core/migrations/**
  - packages/contracts/documents/**
  - packages/contracts/storage/**
  - apps/desktop/src/app/documentReferences*
  - apps/desktop/src/app/ViewerReferencesPane.tsx
  - apps/desktop/src/app/DocumentViewerWorkspace.tsx
  - apps/desktop/src-tauri/src/document_reader.rs
  - apps/desktop/src-tauri/src/supervisor.rs
  - apps/desktop/src-tauri/src/lib.rs
  - tests/documents/**
  - tests/service/test_reference_api.py
  - tests/desktop/**
  - tests/data/test_sqlite_migrations.py
  - tests/fixtures/documents/**
supersedes: []
superseded_by: null
---

# ADR-0048: Bind reference enrichment to existing canonical matching and protected document authority

## Context

The approved W2 task requires ordered raw-preserving references, extracted fields
and canonical Work links without inventing scholarship or identity. Accepted
document v1 retains immutable structure and omits native attributes. Existing
scholarly matching owns exact keys, sealed Work heads and ranking. The approved
Reader uses local protected inspection under reference 1.9. This Proposed record
maps those accepted decisions to implementation; it is not a new approval packet.

## Candidates

Enriching accepted document v1 in place would simplify lookup but would change
an immutable approval and historical schema. A separate canonical encrypted
enrichment preserves that approval and permits expected-head refresh and exact
retry. An index-only match would be cheap but could hide a competing Work when
its projection is absent; a complete current authorized catalog costs bounded
local processing and preserves actual unique-identifier semantics.

## Decision

Implement the separate canonical enrichment. Extract only source-supported
values; authenticated retained native attributes may establish an author role,
while conservative text-pattern observations remain inferred. Use existing
candidate-record author-list composition, exact-key assessment and component
ranking. Automatic association requires agreement of the index and complete
eligible catalog; the index may add uncertainty but cannot remove it. All target
heads, source assertions, decisions and accepted parse inputs remain fresh and
authorized. No Work is created or merged, and extraction/linking stays unverified.

An identifier assertion is active only when a complete native identifier element
or complete lexical segment supports it. Retained native identifier types bind the
scheme when present. Ground the raw source through the existing identifier
normalizer; text NFC, a strict substring, or guessed punctuation removal cannot
establish exact identity. Unanchored assertions remain visible and inactive.
DOI/ISBN internal spaces are preserved. A first word cannot prove the end of an
unstructured identifier; validated resolver URI syntax, complete semantic text,
reference end or a whitespace character forbidden inside the identifier supplies
the boundary. Ambiguous shorter observations cannot trigger automatic linking.

Publication uses the existing protected writer, canonical aggregate, event,
outbox and material-dependency contracts. The optional canonical manifest order
applies only to new reference publications; historical reconciliation manifests
retain their existing semantics. The later explicitly accepted document is a
direct semantic input; original lineage remains transitively immutable and its
earlier impact remains intact. Current exact-copy inspect/derive authority is
still mandatory at publication and delivery.

## Consequences

Schema 28 is additive, backed up and transactional from the exact frozen v27
predecessor. Interrupted migration restores the predecessor before retry.
Accepted structures, original ciphertext and older recovery manifests remain
unchanged. Refresh retains earlier collection history and publishes replacement
impact through existing contracts. A failure or cancellation leaves the base
document usable; corrupt, denied, stale or unavailable evidence delivers no
reference text. A current rights-fenced opaque notice supports explicit recovery.

Fixed Native/Core commands carry selectors only. The Reader uses one bounded
inert preview with disclosed truncation and human-review candidates inside its
existing inspector. Existing current rights, lock/close and cumulative admission
remain mandatory. Large catalogs/structures may produce a resource-limit denial;
there is no new minimum-hardware claim, model run, network destination, export,
clipboard action, automation-framework change or release qualification.

## Verification

Focused checks cover source spans and namespace attribution, complete catalog
matching, damaged index ambiguity, more than 64 actual material inputs, current
Work/decision freshness, encrypted retry/reopen/corruption/rights/cancellation,
the frozen v27 predecessor and all 27 migration interruption steps. Strict
Native/Core/client commands and mounted Reader tests cover inert text, source
substitution, opaque commands, source jump and late-response clearing. Actual
Windows vault/SQLCipher/current-source runtime composition supplements declared
synthetic parser fixtures. Commit-bound qualification and independent disposition
belong to the task evidence; exploratory tests do not approve the task or Wave.

## Task links

- `CAP-05.S05.T01`
