---
id: ADR-0052
title: Bind manual corrections to existing immutable document authority
status: Proposed
date: 2026-10-10
deciders: []
linked_tasks:
  - CAP-05.S06.T02
decision_scope: Documentary mapping of approved CAP-05.S06.T02 to accepted ADR-0029; no new architecture, security, migration, experience or release authority.
affected_paths:
  - packages/contracts/documents/**
  - services/core-api/src/research_observatory_core/ports/document_corrections.py
  - quality-scope.json
supersedes: []
superseded_by: null
---

# ADR-0052: Bind manual corrections to existing immutable document authority

## Context

Accepted ADR-0029 and the approved CAP-05.S06 plan require controlled human
corrections over an exact immutable base, preserving original parser output,
actor, rationale and history. Only explicit acceptance advances the accepted
revision and emits scoped downstream dependency facts. This Proposed mapping
records that implementation; the existing accepted decision remains authority.

## Candidates

An in-place edit would lose immutable parser evidence and exact revision links.
A separate unprotected correction store would duplicate canonical authority.
Typed, encrypted proposal records in the existing aggregate/object-store
boundary preserve both reviewable drafts and the existing transaction fences.

## Decision

Use the existing protected document revision adapter behind the additive
correction port and closed v1 contracts. Typed relabel/reorder/split/merge,
reference rematch, original-page anchor and exclusion operations carry exact
base and expected-old-value digests. Save, undo and discard remain proposals.
Explicit exact-draft acceptance atomically appends fresh canonical identities,
the human decision, provenance/outbox and scoped dependency impact.

Authenticate original Native/Docling receipts literally before translating
relationships through replayed protected source lineage. Excluded intervals
cannot be rediscovered by surviving ancestor scans or new quote/context
selectors. Preserve original observations; human labels and matches remain
separate from machine assertions and scholarly verification.

Native owns project/session/principal and current window/lock authority.
The renderer uses fixed closed actions, bounded projections and the inherited
Academic Minimal 1.9 Parsing Quality reference. Dirty, busy and unknown command
ownership blocks every ordinary exit, including guided stages and Return.
Lock clears private state. Recovery retries the exact command after fresh
authority; an ambiguous transport result is never a rollback or acceptance claim.

## Consequences

Original source/IR, accepted history, parser assets, migrations and existing
storage guarantees remain unchanged. Drafts and rationale stay encrypted;
diagnostics contain bounded codes. Current source inspect/derive, human/Intent/
privacy, exact-base CAS and final delivery fences apply to every command.
Readers reopen immutable historical revisions and expose accepted human
metadata without upgrading machine assertions to verified evidence.

The quality-scope change only inventories new product/task test Python files;
no governed root, threshold, checker, hook or shared automation changes. No
model or 8/16 GiB run is introduced. T03 retains parser-upgrade batch comparison.
Failed publication rolls back uncommitted changes and retains the accepted head.
Published decisions and older immutable revisions remain readable; recovery
never erases an accepted decision or relabels new content as an old revision.

## Verification

Authored domain/source-lineage tests cover all typed operations, Unicode,
exclusion and retained relationships. Real encrypted repository tests cover
proposal preservation, exact acceptance, actor/rationale, restart, retries,
CAS, rollback, dependency events and preview-only pagination. Actual Native/
Core and a declared Wry production-component host test bounded current authority
and save/accept/Reader/reopen behavior. Mounted production ApplicationRuntime
navigation tests use explicit child/transport doubles to exercise dirty, busy
and unknown ownership through guided stages and Return. They do not qualify
real OS focus, a shipping installation, parser models or full Wave performance.
Commit-bound selected checks and independent disposition determine completion.

## Task links

- `CAP-05.S06.T02`
