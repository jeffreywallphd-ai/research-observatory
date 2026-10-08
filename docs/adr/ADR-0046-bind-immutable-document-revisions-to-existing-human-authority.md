---
id: ADR-0046
title: Bind immutable document revisions to existing human authority
status: Proposed
date: 2026-10-07
deciders: []
linked_tasks:
  - CAP-05.S03.T01
  - CAP-05.S03.T02
decision_scope: Documentary implementation mapping of immutable normalized structure, human acceptance and live parser admission to accepted ADR-0013/0024/0025/0029; no new security, product scope, framework or release authority.
affected_paths:
  - packages/contracts/documents/**
  - packages/contracts/storage/sqlite-migration-recovery.schema.json
  - packages/contracts/storage/sqlite-profile.v1.json
  - packages/contracts/storage/sqlite-profile.schema.json
  - docs/architecture/local-sqlite-storage.md
  - packages/contracts/storage/README.md
  - services/core-api/src/research_observatory_core/document_revision*.py
  - services/core-api/src/research_observatory_core/document_revisions.py
  - services/core-api/src/research_observatory_core/document_parse*.py
  - services/core-api/src/research_observatory_core/ports/document_revisions.py
  - services/core-api/src/research_observatory_core/storage.py
  - services/core-api/src/research_observatory_core/migrations/**
  - services/core-api/src/research_observatory_core/object_store.py
  - services/core-api/src/research_observatory_core/repositories.py
  - services/core-api/src/research_observatory_core/workflow_executor.py
  - services/core-api/src/research_observatory_core/main.py
  - services/core-api/src/research_observatory_core/app.py
  - services/core-api/src/research_observatory_core/import_preview_service.py
  - services/core-api/packaging/sidecar-build.json
  - packages/contracts/anchors/**
  - packages/contracts/README.md
  - services/core-api/src/research_observatory_core/anchors/**
  - services/core-api/src/research_observatory_core/source_anchor_repository.py
  - services/core-api/src/research_observatory_core/ports/source_anchors.py
  - apps/desktop/src/app/sourceAnchors*.*
  - apps/desktop/src/app/SourceAnchorReader*.*
  - apps/desktop/src-tauri/src/document_reader.rs
  - tools/architecture_check.py
  - tools/core_sidecar_build.py
  - tests/anchors/**
  - tests/service/test_source_anchor_api.py
  - tests/packaging/test_core_sidecar_package.py
  - quality-scope.json
  - verification-profiles.json
supersedes: []
superseded_by: null
---

# ADR-0046: Bind immutable document revisions to existing human authority

## Context

The approved CAP-05.S03.T01 outcome retains normalized structure across restart
and reparsing without silently changing a researcher's accepted document head.
S02 supplies protected originals, encrypted raw receipts and staged neutral IR;
S03 must compose a real durable parse operation and explicit human acceptance.
This Proposed record documents those already accepted decisions. It neither
changes their authority nor amends the frozen W2 packet.

## Candidates

1. Replace the current document head when the parser returns success. This
   violates ADR-0029's explicit human acceptance and immutable prior revisions.
2. Retain normalized output only in memory until acceptance. This loses the
   staged result after restart and cannot authenticate durable physical output.
3. Persist an encrypted exact-attempt result, then append the original document
   through a current-authorized explicit human acceptance. This is the approved
   outcome and the selected implementation mapping.

## Decision

The trusted native command submits a fixed `document-parse` activity bound to
current human actor, native session, accepted Intent, privacy policy, original
source/copy rights and recorded producer/configuration/assets. Its worker port
exposes parsing and retention without SQLite/path/key authority. The private
repository adapter owns borrowed canonical transactions and encrypted objects.
Raw artifacts and normalized output must match the authenticated successful
physical attempt; source, retained-result and accepted revision IDs remain
distinct. Parsing alone never changes the original document head.

Explicit acceptance binds the complete retained receipt, semantic command,
confirmation digest and expected current revision. Current authority and rights
apply to protected reads and replays as well as publication. Core mints UUIDv7
element IDs scoped to the new revision and remaps the complete neutral hierarchy,
text projections, source locators, reference/citation links and quality metadata.
It preserves uncertainty and scholarly `unverified` state. Original revision,
decision, element index, dependencies, provenance and scoped outbox publication
are atomic. Exact retries create no extra event; changed commands or concurrent
stale bases conflict. Earlier accepted revisions remain queryable.

Schema 26 adds immutable job, result, accepted revision and element-index tables
through the existing verified-backup forward-only migration. The literal
populated v25 fixture predates these source edits. Interruption must preserve its
authenticated rows, history and ciphertext, and valid retry must reopen exactly.
Recovery-manifest rules retain their prior target-v21 through v25 meanings and
add exact source/chain/hash/path binding for target-v26.

The existing product admission controller accounts for the selected activity's
maximum resources before claim and releases its reservation on every outcome.
One parser permit is shared across projects; metadata demand remains lighter.
All Core worker adapters use the same immutable policy. The selected parser
reservation is four CPU slots, 4 GiB memory and 1 GiB disk, plus existing
interactive headroom. Unknown/insufficient capacity leaves the job unclaimed.
Heartbeat and cancellation polling stay outside canonical writers, whose stop
check uses a latched native signal plus current durable lease/rights/session.

The four-slot host is safely denied by that conservative current policy. The
approved four-core parsing tier remains an unresolved W2 qualification
obligation; this record does not approve a different minimum, reduced
accounting or a parser performance exemption. The exact owner-accepted S02 warm
timing observation remains adverse and is not investigated or remeasured here.

## Consequences

Protected backend persistence becomes available to later S03 anchor and resolver
tasks. No governed desktop experience changes here. Structural acceptance never
creates a citation, participant, scholarly result or verification decision.
Accepted hierarchy indexing follows the contract's already validated
parent-before-child order in one pass so a large lawful graph does not monopolize
the canonical writer through quadratic traversal.

## Verification

Focused proof covers exact predecessor recovery, authenticated encrypted
retention, stable/disjoint identities and reopen, current authority denial,
semantic replay/concurrent-base conflict, corrupt/partial output, atomic
rollback, bounded hierarchy traversal, admission and native routes. One fresh
actual signed LPAC parse exceeding the lease interval must prove live renewal
and an intervening canonical write. It is not a benchmark rerun. Synthetic
fixtures and source-level Core composition do not qualify a newly frozen
desktop; slice integration, fresh W2 qualification, independent reviews and
the separate release decision remain required.

## Task links

- `CAP-05.S03.T01`

## CAP-05.S03.T02 implementation mapping

This append-only Proposed implementation note maps the already approved anchor
outcome to accepted ADR-0013/0024/0029. It adds no decision authority or frozen
Wave/reference change. T01's documented decisions and adverse minimum-tier
obligation remain unchanged.

Core derives protected selectors only from an exact accepted immutable revision.
Project/document/source/revision/node/projection IDs must agree. When text
selectors are available, NFC Unicode 16.0.0 code-point spans and
exact/prefix/suffix/context text must agree; absence is explicit. Quote/context
caps are 2048/8192 code points; the protected envelope is at most 32 KiB. Geometry retains
the unrotated top-left source frame, normalized rectangle, original dimensions,
explicit quarter-turn rotation and reported block granularity. Missing geometry
has an explicit structural/text fallback. There is no fuzzy reassignment to a
new accepted head or scholarly verification inference.

An anchor is a derived canonical Document aggregate using the existing encrypted
object, current human/native-session/Intent/privacy/exact-copy inspect+derive
authority, provenance, material source-revision dependency and scoped outbox.
Publication/replay is atomic and idempotent; changed semantic commands conflict.
The private named source_anchor_repository adapter composes through the existing
revision adapter and portable SourceAnchorRepository port. Business and port
modules gain no SQLite, root, key or connection authority. Exact adapter/module
registration and strict sorted sidecar inventories retain existing checks.

Common reads authenticate the small retained context and full canonical replay
under current source authorization, without loading full PDF or normalized IR.
Derivative authentication does not verify original bytes or update their
verification timestamp. Original source streaming retains its existing complete
authentication and current-copy rights. Corrupt derivative data cannot quarantine
the original. Late or detached session results deny or clear protected state.

Five fixed native commands accept opaque identities/ranges, retain current
window/project/session delivery fencing, and never accept renderer-supplied
root/actor/quotes/coordinates. The reusable Reader strictly decodes those contracts
and converts code points to UTF16 explicitly. Inert passage highlighting,
structural fallback, revision/confidence labels, keyboard return, scaling,
theme/reflow and late-lock clearing follow the inherited approved reference.
Attachment activation/workspace routing and original-byte PDF.js rendering remain
CAP-05.S04. Resolution/citation links, stale-dependent propagation and the 100 ms
S03 resolver budget remain CAP-05.S03.T03/slice obligations.

Focused evidence covers authored selector/geometry/Unicode cases, actual protected
SQLCipher persistence/reconstruction, canonical integrity/atomic interruption,
native-session/rights denial and actual Core API composition. The mounted actual
React component uses an explicit fixed Tauri response double populated from Core
synthetic outputs. These proofs do not claim a full Core/Tauri process restart,
new installed package, minimum-tier, benchmark or Wave release qualification.
Existing ADR change-set validation is required for the protected contract/port
and product check registrations; omission is preserved as R01's finding.

- `CAP-05.S03.T02`
