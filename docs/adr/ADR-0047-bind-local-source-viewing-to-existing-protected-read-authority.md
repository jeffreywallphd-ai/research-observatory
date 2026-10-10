---
id: ADR-0047
title: Bind local source viewing to existing protected read authority
status: Proposed
date: 2026-10-08
deciders: []
linked_tasks:
  - CAP-05.S04.T01
  - CAP-05.S04.T02
  - CAP-05.S04.T03
decision_scope: Documentary implementation mapping of the approved local viewer and cooperative protected-read cancellation to accepted ADR-0016/0017/0029; no new product, security, migration, hardware or release authority.
affected_paths:
  - services/core-api/src/research_observatory_core/object_store.py
  - services/core-api/src/research_observatory_core/ports/object_store.py
  - services/core-api/src/research_observatory_core/projects.py
  - services/core-api/src/research_observatory_core/project_action_mutex.py
  - services/core-api/src/research_observatory_core/app.py
  - services/core-api/src/research_observatory_core/main.py
  - services/core-api/src/research_observatory_core/document_viewer*.py
  - services/core-api/src/research_observatory_core/ports/document_viewer.py
  - services/core-api/src/research_observatory_core/ports/viewer_actions.py
  - services/core-api/src/research_observatory_core/viewer_action_repository.py
  - packages/contracts/documents/**
  - packages/contracts/storage/README.md
  - apps/desktop/src/app/documentViewer*.*
  - apps/desktop/src/app/pdfDocumentViewer.ts
  - apps/desktop/src/app/viewerWorker*.*
  - apps/desktop/src/app/viewerAssets*.*
  - apps/desktop/src/app/DocumentViewer*.*
  - apps/desktop/src/app/ViewerActionsPane.tsx
  - apps/desktop/src/app/viewerActions*.*
  - apps/desktop/src/app/ViewerAnchorContexts.tsx
  - apps/desktop/src/app/SourceAnchorReader.tsx
  - apps/desktop/src/app/ApplicationRuntime*.*
  - apps/desktop/src/app/DocumentAttachmentPane.tsx
  - apps/desktop/src/app/ReconciliationPane.tsx
  - apps/desktop/src/app/ReconciliationVersionsPane.tsx
  - apps/desktop/src/app/ImportWorkspace.tsx
  - apps/desktop/src/app/workflowNavigationModel.ts
  - apps/desktop/src/app.css
  - apps/desktop/src-tauri/src/document_reader.rs
  - apps/desktop/src-tauri/src/document_viewer.rs
  - apps/desktop/src-tauri/src/viewer_actions.rs
  - apps/desktop/src-tauri/src/viewer_actions/**
  - apps/desktop/src-tauri/src/viewer_export.rs
  - apps/desktop/src-tauri/src/viewer_print.rs
  - apps/desktop/src-tauri/src/supervisor.rs
  - apps/desktop/src-tauri/src/lib.rs
  - apps/desktop/src-tauri/tauri.conf.json
  - apps/desktop/package.json
  - apps/desktop/vite.product.config.ts
  - apps/desktop/pdfjsWorkerBuild.ts
  - pnpm-lock.yaml
supersedes: []
superseded_by: null
---

# ADR-0047: Bind local source viewing to existing protected read authority

## Context

CAP-05.S04.T01 implements the source viewer selected by accepted ADR-0029.
Original encrypted sequential reads authenticate the whole source before
exposing any byte and retain a metadata writer until close. The accepted design
explicitly includes a backward-compatible cancellation hook for that read loop
and bounded prefix discard. This Proposed record maps that existing authority;
it cannot replace the accepted architecture or frozen Wave packet.

## Candidates

1. Drop a renderer promise while leaving the Core reader/writer alive. This
   cannot satisfy cancellation or lease-release requirements.
2. Stop a database thread or expose a decrypted path/cache. This violates the
   accepted source, cryptographic and migration boundary.
3. Use a trusted cooperative stop signal between bounded authentication/read
   chunks, close and roll back the owned reader, then deliver only authorized
   bounded ranges through the fixed native viewer transport. This is the
   implementation of the accepted decision.

## Decision

The existing object port receives an optional trusted `cancellation_requested`
callback for exact attached-original reads. Existing callers keep their
behavior. The callback performs no I/O or nested database/project action.
Unavailable or cancelled signals deny access with `ObjectReadCancelled`,
distinct from corruption/key loss. Authentication still completes before the
first byte. A cancelled open closes/rolls back in its owner; a cancelled live
read releases its registry lease and rolls back the transaction. Healthy
ciphertext remains available for an explicitly fresh authorized retry.

The viewer implementation must preserve the original/normalized revision
distinction, current per-copy inspect permission, separately governed derive
permission for structured text, bounded range admission, native delivery fences
and inert rendering. A successful object-loop test does not establish those
later integration boundaries or complete this task.

The bounded original-read pool owns one cooperative worker, permits one active
read per project and at most eight waiting requests, and coalesces only exact
source/range/session/authority keys. Every member retains its own cancellation
signal; cancelling one cannot cancel another authorized member. Responses are
bounded and only retained until their waiters leave, never as a source cache.
Delivery authorization is freshly checked by the calling service.

The project action guard retains reentrancy and admits waiting owners in FIFO
order. Releasing it between ranges therefore gives already waiting metadata
commands precedence over the next viewer operation. This implements ADR-0029's
writer-interleaving requirement without changing project or database authority.

The typed private native/source/range/text/cancel protocol and exact source-field
inventory are documented in
[the document contract](../../packages/contracts/documents/source-viewing.md).
Original inspection and accepted derivative inspection have different rights
checks; successful earlier authority cannot authorize delivery after revocation.
Native validates closed shapes and exact correlation, then delivers bounded raw
byte IPC without renderer paths, root, session or credential exposure.

The product uses the exact locally bundled PDF.js 6.4.299 worker. Its build-time
source digest and unique range-group/scheduling transforms fail closed on
dependency drift. SDK missing-chunk demands acquire actual range readers one at
a time, and cancelled documents never admit deferred demands. No source-byte
queue or original cache is added and Core's admission limit remains unchanged.
The inert integration uses guarded worker backing stores, decoded-message clone
admission, tracked surfaces and a shared bundled-asset allowance. Late thumbnails
are fenced by the navigation generation and clean up on cancellation/failure.
Current reservations do not themselves prove the complete or peak footprint;
actual decoder/native measurements remain qualification requirements.

## Consequences

### Rights-aware Reader actions

CAP-05.S04.T03 implements the action-specific mediation already required by
accepted ADR-0029. Closed source/anchor selectors cross Native to Core; source
text, paths, programs, actors and grants are not renderer request authority.
Existing retained-copy rights, trusted human, accepted Intent and privacy
fingerprint govern every fixed inspect/derive/quote/local-export use. A separate
explicit review records only otherwise missing or unknown permissions for that
copy and action; it cannot override denial, expiry, disputes or pending
propagation. Its receipt is not execution authority.

Core materializes only the exact identified quotation or anchor annotation,
with current per-copy policy and unverified extraction. Native separately
selects local destinations, rechecks current Core and window/lock authority,
and publishes held create-new outputs. An original handoff additionally verifies
the complete retained original and holds the explicitly selected local
application. Delivered plaintext is outside project protection.

The initial Windows print adapter uses the local Microsoft PDF driver through a
bounded held stream; other queues remain unavailable. Incomplete owned outputs
are delete-pending before plaintext is written. Cancellation denies delivery
but ownership remains until actual callbacks, Core frames and Native work
close. Clipboard history/cloud suppression markers precede identified quotation
publication. Tests use only authored fixtures and a private clipboard station.
This documentary mapping adds no product/security authority, migration format,
remote route, hardware tier or automation framework work.

The change is additive and retains existing envelopes, keys, immutable source
identities, schema/migration history and corruption quarantine behavior. No
plaintext disk cache, new encryption construction, hosted service or automation
framework development is introduced. Retained sources support retry; there is
no resumption of a partially authenticated stream. Rollback discards only the
uncommitted reader's verification timestamp, not the original or its history.

Owner-directed smaller resource/model options and deferred larger tiers remain
a separate successor-packet requirement. This record does not waive viewer
memory, latency, cancellation, hardware qualification or later release gates.

## Verification

Focused real encrypted-attachment cancellation tests cover pre-open stop,
mid-authentication stop before stream return, post-authentication stop before
buffer delivery, failed stop signal, unchanged source and verification metadata,
writer release and exact fresh retry. Existing inspect-rights characterization
remains selected. Complete viewer transport/rendering, hostile input, memory,
performance, native principal and experience checks remain task obligations.

## Task links

- `CAP-05.S04.T01` owns this implementation and qualification.
- `CAP-05.S04.T02` extends the same approved source boundary with portable opaque
  anchor selections, bounded retained context and fresh delivery authority.
  It reuses accepted ADR-0029 and canonical anchors, changes no encryption or
  migration format, and introduces no automation framework work or new authority.
- `CAP-05.S04.T03` adds the approved rights-aware local action contracts and
  distinct permission review, with Core/Native publication and physical-closure
  checks. This Proposed record does not replace accepted ADR-0029 or task gates.
