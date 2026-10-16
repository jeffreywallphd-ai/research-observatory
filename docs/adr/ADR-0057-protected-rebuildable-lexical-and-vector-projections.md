---
id: ADR-0057
title: Protected rebuildable lexical and vector projections
status: Proposed
date: 2026-10-16
deciders: []
linked_tasks:
- CAP-06.S01.T01
- CAP-06.S01.T02
- CAP-06.S01.T03
- CAP-06.S02.T01
- CAP-06.S02.T02
- CAP-06.S02.T03
- CAP-06.S03.T01
- CAP-06.S03.T02
- CAP-06.S03.T03
decision_scope: Proposed Windows protected derivative lexical/vector storage, keys, generation and recovery semantics; canonical data stays authoritative.
affected_paths:
- services/core-api/src/research_observatory_core/ports/**
- services/core-api/src/research_observatory_core/**
- packages/contracts/**
supersedes: []
superseded_by: null
---

# ADR-0057: Protected rebuildable lexical and vector projections

Private, unnumbered and unaccepted. The broad architectural ownership patterns above are proposal scope, not a product edit allowlist. Implementation tasks must select exact affected files through the normal route; no schema/ADR number or reference identity is reserved.

## Context

Systems Design 2/6 makes canonical relational/object state authoritative and indexes replaceable. [ADR-0012](ADR-0012-use-relocatable-versioned-local-project-packages.md) governs relocatable project packages and file classes. ADR-0020 protects canonical databases; ADR-0029 governs immutable documents/anchors and protected viewing. Existing DatabaseKeyProvider grants project-database leases, not arbitrary index files. Current code and declared ports do not prove SQLCipher FTS5, protected derivative WAL/temp storage or a safe vector engine.

The unapproved historical Qdrant preference is a candidate, not a W3 mandate. The small local outcome needs lawful lexical search without an eligible encoder, bounded 100k-vector retrieval where actually qualified, exact query/run provenance and recovery without storing private text/vectors in an ordinary application cache.

## Candidates

1. Qdrant local/service with protected transport/storage and snapshot management. Mature filter/scale features are useful, but a new process/service, backup/encryption and installation surface precede demonstrated need. Keep an engine-neutral port so later adoption is possible.
2. Embedded exact cosine scoring over protected derivative vector rows/chunks plus a separate SQLCipher FTS5 database. It trades scale for bounded streaming, a smaller local deployment and explicit protection/rebuild ownership. Actual throughput and FTS/operator support still need proof.
3. Plain SQLite FTS/NumPy/mmap files under a cache directory. This is simple but cannot satisfy private text/vector at-rest protection; reject it for private project derivatives rather than silently weakening rights.

## Decision

Propose candidate 2 for W3. Use the existing governed derivative `indexes` class and approved key-protection mechanisms. The canonical project database and protected source objects remain the source of record. Derivative index bytes are excluded from portable backup/export under the existing file-class policy; source rights, immutable IDs, generation manifests and rebuild authority remain canonical. Do not export private vectors simply because they can be regenerated.

A separate protected SQLCipher index database contains its own revision-bound text mirror and an external-content FTS table in that same database. Do not claim unsupported cross-database external-content references. Reuse strict connection/foreign-key/integrity and protected-lifetime patterns where applicable; explicitly qualify FTS5, WAL, journal/temp, close and crash behavior. Unknown feature or confinement fails that index, not permission to write plaintext. Add a purpose-scoped derivative-index key lease at the Core storage port; never pass an existing project-DB lease to an arbitrary path, expose key material to workers or invent ad hoc cryptography. Path/volume/no-reparse and read/write handles remain bound for their consumed lifetime.

For vectors, use encrypted rows or bounded protected chunks plus an authenticated generation manifest and a deterministic exact cosine scorer. Filter canonical rights and metadata before streaming bounded scoring batches; stable-ID tie-breaks make equal scores reproducible. Public read-only model weights may use an app artifact cache. Private passages, vectors, tokens, prompts and KV caches may not become plaintext global cache/mmap/temp files. Large derivative chunks may use the existing protected object adapter with a reviewed purpose, manifest and authenticated retrieval; no separate evidence authority is created.

Canonical record changes commit revision/provenance/outbox together. An idempotent generation consumer updates derivative mirror/FTS/vector/checkpoint state with contiguous authority and expected inputs. No transaction spans the canonical and derivative stores, and no exactly-once distributed side-effect claim is made. Queries bind analyzer/chunk/model/dimensions/runtime/filter/rank/fusion parameters, canonical revision watermark and index generation. Report lag/staleness and any explicit recent-record overlay; overlays must reauthorize current canonical rights just like ordinary hits. Revocation filters returned IDs/snippets immediately, even if physical purge is pending.

A model, analyzer, chunking or dimensional change creates a new generation, never relabels existing vectors. Build a resumable shadow generation over exact lawful canonical inputs. Before pointer promotion, recheck completeness, hashes/watermark, current rights and integrity. Atomically switch the selected generation pointer only after validation; retain the old valid generation until readers drain. Cancel, crash, stale lease or changed inputs leave the shadow incomplete, not Ready. Restore, relocation and project-key rotation rebuild protected derivatives under fresh valid leases; stale keys/generations cannot leak data during purge. Source normalization and ADR-0029 anchor identity are unchanged by search tokenization.

Lexical retrieval remains useful when semantic/rerank roles are absent, resource-denied or unqualified. It must identify the unavailable component and executed plan rather than silently label a lexical-only run hybrid. Optional rerank uses a qualified profile over top20 by default, at most50 only with explicit qualification. A declared timeout fallback retains and labels the fused order; it cannot fabricate rerank success. Search expansion is an explicit bounded branch, never automatic corpus membership or human screening acceptance.

## Consequences

Exact scoring bounds memory but may be too slow at scale. W3 targets are proposed measurements, not assumed performance; retain actual failures and consider a later accepted engine decision if the bounded profile cannot satisfy the outcome. W5 larger-scale candidates and W9 optional optimization remain separate. Model/resource admission follows the first proposed architecture decision and selected policy03, including parser/inference serialization; index planning does not grant a concurrent model workload.

Migrate canonical generation/key metadata additively from the actual approved schema predecessor with verified backup/copy/row/object preservation. Do not reserve a schema number or destructively downgrade new canonical state. Derivative storage upgrades are discard-and-rebuild only after preserving authoritative manifests and lawful source state. Rollback selects a still-valid old generation only if its current rights/model/schema authority remains valid; otherwise show index unavailable and preserve manual/source inspection. It never restores revoked text or makes incomplete results authoritative.

## Verification

Future actual Windows proof must cover SQLCipher FTS5 capability; encrypted index/WAL/temp and key lifecycle; no plaintext private vector/text cache; denied cross-project/session/reparse/changed-volume access; and revoked rights in ordinary hits, snippets and overlays. Compare bounded exact-vector results and stable ties with deterministic small fixtures; report scientific gold recall on its real judged frame, not invented negatives. Freeze generation/analyzer/model/config and source IDs before comparisons.

Exercise updates, duplicate delivery, source deletion/change, shadow cancellation, crash/restart checkpoints, mixed-generation denial, corrupt manifest/chunk, rotation/relocation/restore, atomic pointer swap and backup/export exclusion. Measure separate 100k metadata/vector and permitted passage workloads within actual admission and original timing/cleanup rules; do not infer simultaneous model/large-layout capacity. Existing contract/architecture/migration/rights tests and actual packaging/principal checks remain necessary at their affected boundaries. No tool, benchmark or runtime check ran for this proposal.

## Task links

The nine CAP-06.S01-S03 tasks own query grammar/FTS, representation/vector generations and fusion/rerank/run replay. CAP-07.S02 supplies admitted encoder execution; CAP-06.S04-S06 consume result provenance/denominators, explicit branches and human screening. The existing task register/DAG owns their immutable identities and estimates; no new workstream or framework is introduced.
