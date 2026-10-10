---
id: ADR-0053
title: Bind document reprocessing to existing per-document acceptance authority
status: Proposed
date: 2026-10-10
deciders: []
linked_tasks:
  - CAP-05.S06.T03
decision_scope: Documentary mapping of approved CAP-05.S06.T03 to accepted ADR-0029 and ADR-0025; no new architecture, security, migration, experience or release authority.
affected_paths:
  - packages/contracts/documents/**
  - services/core-api/src/research_observatory_core/ports/document_reprocessing.py
  - services/core-api/src/research_observatory_core/document_reprocessing_api.py
  - services/core-api/src/research_observatory_core/document_revision_repository.py
  - services/core-api/src/research_observatory_core/object_store.py
  - quality-scope.json
supersedes: []
superseded_by: null
---

# ADR-0053: Bind document reprocessing to existing per-document acceptance authority

## Context

Accepted ADR-0029 requires immutable original parses and accepted revisions,
explicit human correction reconciliation, advisory anchor migration and separate
per-document reprocessing transactions. Accepted ADR-0025 governs exact durable
jobs, physical attempts, interruption and explicit continuation. The approved
CAP-05.S06 plan and Academic Minimal 1.9 Parsing Quality reference supply the
existing product scope. This Proposed mapping records implementation trace;
the accepted decisions remain authority.

## Candidates

Replacing normalized heads through ordinary acceptance would bypass comparison,
retained human decisions and impact. Chaining public acceptance and correction
writers would expose partial accepted state. Reusing the current document
adapter permits protected proposals followed by one compound publication.

## Decision

Store typed encrypted batch, comparison, reconciliation and acceptance records
inside the existing document aggregate/object-store boundary. The concrete
adapter remains in document_revision_repository.py behind revisions.reprocessing()
and an additive portable port and bounded Native-only API. No SQL migration,
new parser/provider, cryptographic profile or automation framework is introduced.

Every new replacement of an already normalized head requires explicit comparison
and per-document acceptance. Initial ordinary acceptance, historical reads and
exact historical command replay remain compatible. Comparison canonicalizes a
prospective structure without inventing a human acceptance. Each authenticated
correction generation is explicitly mapped to exact new nodes/references,
expected values, original operation digests and the retained new result.
Complete unresolved counts govern acceptance independently of pagination.

Stage protected values before publishing all machine/correction revisions,
human decisions, provenance/outbox and impact intents on one current-source-
fenced writer. Keep literal existing correction verification. The authenticated
outer reparse record binds the previous head, exact job/attempt/result/selection,
complete reconciliation plan and every nested command/revision. Source lineage
starts at the new authenticated machine receipt and advances mapped corrections.
Historical inputs remain non-material; actual new parse inputs remain material.

Recheck the external graph before any canonical append, then authenticate the
post-append impact run and checkpoint. Small propagation completes in the writer;
larger work remains pending for explicit checkpoint resume. Read-impact recovers
the original accepted binding from a later batch revision. An authenticated
already-advanced checkpoint returns current readback without consuming another
chunk. Cancellation stops future items and preserves committed decisions.
Unfinished old-session inputs need an explicit new immutable command/job under
current authority; completed historical outcomes remain readable.

Unique exact quote and context produce advisory unchanged/moved candidates.
Missing or ambiguous quotes remain unresolved and historical anchors never move.
The renderer keeps exact issued commands through unknown outcomes and ordinary,
guided-stage and Return guards, using the already approved 1.9 experience.

## Consequences

Current Native/session, human/Intent/privacy and exact source inspect/derive
authority apply through materialization, publication and delivery. Reference
rematches require current active Work and its authenticated sources. Responses
remain bounded and content-free on denial. Source/IR, authors/rationale, accepted
history, storage/migrations and scholarly verification stay unchanged.

The object reader adds only the protected reprocessing media type and an 8 MiB
read cap under the existing encryption/authentication profile. The quality-scope
declaration only registers the nine new product/test Python paths under unchanged
checks, thresholds and policies; root owns that additive inventory publication.
No hook, scanner, controller, CI or shared harness changes are authorized here.

## Verification

Authored domain fixtures cover retained text/structure/reference differences,
Unicode and quote ambiguity, exact mappings and resource bounds. Real encrypted
SQLCipher tests cover immutable history, compound acceptance, literal correction
readback, exact retry/CAS, substitution, every inner rollback boundary, selective
staleness, cancellation and restart. Actual Native/Core/vault composition proves
current rights, principal, session continuation and stopped delivery. Desktop
strict codecs and production-component journey tests cover the inherited
experience and unknown command ownership. These bounded checks do not qualify
shipping installation, real OS accessibility, model execution, minimum hardware
or full Wave performance. Commit-bound checks and independent disposition govern
completion; existing adverse results remain unwaived.

## Task links

- `CAP-05.S06.T03`
