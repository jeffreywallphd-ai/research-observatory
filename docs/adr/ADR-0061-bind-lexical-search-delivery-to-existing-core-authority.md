---
id: ADR-0061
title: Bind lexical search delivery to existing Core authority
status: Proposed
date: 2026-10-17
deciders: []
linked_tasks:
  - CAP-06.S01.T03
decision_scope: Documentary implementation of approved lexical search under Accepted ADR-0001/0010/0025/0057; no new architecture authority.
affected_paths:
  - apps/desktop/**
  - packages/contracts/core-api/**
  - packages/contracts/storage/**
  - services/core-api/src/research_observatory_core/**
  - tools/architecture_check.py
  - tools/core_api_contract.py
  - tools/core_api_search.py
  - quality-scope.json
supersedes: []
superseded_by: null
---

# ADR-0061: Bind lexical search delivery to existing Core authority

## Context

Approved CAP-06.S01.T03 requires fielded search, filters, stable pages, exact
snippets and rank explanations. ADR-0057 selects the protected lawful mirror;
ADR-0010 owns generated public contracts; ADR-0025 owns durable admitted work.
The same Core API must remain usable independently of the desktop renderer.
This record documents implementation within those decisions. It does not change
the frozen Wave, security authority, experience reference or release criteria.

## Candidates

1. Run queries and retain authoritative result state in the renderer. This
   would duplicate rights, ranking and execution authority and impede headless
   callers; reject it.
2. Expose fixed Core commands over the existing authenticated transport, with
   protected canonical execution records and current-authorized delivery.
   Implement this within the approved architecture.

## Decision

Add six strict `/projects/search` operations and generated client methods.
Preserve every predecessor schema and operation identity. Core resolves current
Native/session/actor/Intent/privacy authority; bodies cannot claim a principal.
Public DTOs expose bounded hits and method scores, never a raw SQL/store/key
capability or relevance probability. Lexical-only execution explicitly reports
semantic unqualified and rerank not run.

The pure `ports/lexical_search` protocols separate HTTP commands and worker
orchestration from persistence. Compose the concrete search adapter in `main`.
The existing worker controls heartbeat, cancellation and normal drain through
the activity repository port; the data adapter owns query/store materialization
and atomic accepted output. Long search orchestration does not hold the project
lifecycle mutex. Individual authority checks and canonical transactions retain
their existing guarded lock order and final current-input fences.

Register only six new root data-adapter basenames: `lexical_input_repository`,
`lexical_query_repository`, `lexical_run_repository`, `lexical_run_lineage`,
`lexical_delivery` and `lexical_search_repository`. The SQL-bearing input-history
helper resides at that root, leaving the query domain storage independent.
Business, port, alias and nested-impostor denial remain unchanged. One pure
`IndexServiceProblem` identity is re-exported by the prior index module.

Canonical schema30 adds immutable SearchRun/input manifests, authenticated
observation classification and source epochs without modifying published29.
Run/provenance/outbox and queue success commit atomically through the existing
writer. Exact input/result digests bind opaque cursors. Complete current-lawful
capture precedes BM25 and final delivery; no persisted warm-read certificate is
introduced. Non-outbox import/object changes and trusted rights-time transitions
invalidate earlier observations. Historical runs and failed attempts remain.

After a successful protected TRUNCATE checkpoint, a temporary genuine read-only
SQLCipher companion establishes a reader under the same held identities/key.
Close the writer, then companion, before any key or file hold is released.
This avoids the installed binding's final Windows WAL-delete retry while the
existing authenticated cleanup retains deletion ownership. It changes neither
the persistent WAL mode nor dependency/profile. Failed companion setup still
attempts both actual closes, preserves authority denial and reports incomplete
close; it does not manufacture read or retirement eligibility.
SQLite documents the relevant [read-only WAL close behavior](https://sqlite.org/walformat.html).

The approved1.10 Search Studio consumes the same public commands. Bounded
memory-only context supports exact Reader return and focus restoration, with
current-page revalidation. Lock, project/Intent replacement, denied rights and
expiry clear protected results. Exact-command retry reconciles lost responses;
late source/anchor replies cannot override navigation or a locked context.

## Consequences

Core remains the authoritative headless-capable API; no AI mode, new launcher,
scheduler, database engine, worker key grant, deployment or egress is added.
Per-request complete capture has unqualified scale/latency costs. Small fixtures
and the empty-corpus Native principal check do not qualify100k performance.
Slice and Wave qualification retain their separate scale, resource, packaging
and release obligations. Backup-first30 migration preserves exact prior cells,
objects and history; recovery restores the verified predecessor through existing
authority rather than downgrading current state or rewriting approvals.

## Verification

Use exact predecessor OpenAPI comparison, generated client/Rust admission,
actual supervised Native/DPAPI/SQLCipher execution, protected current-input and
run tests, frozen synthetic held-out lookup comparison, exact v28/v29 migration
and interruption checks, close failure/lifetime regressions, and production
browser paging/source-return/keyboard/denial/late-reply tests. Mocks and synthetic
scientific records retain their stated limits. Add root-only adapter positive
checks and business/port/alias/nested negative checks without changing detection.
Development observations are not commit-bound task or Wave qualification.

## Task links

- `CAP-06.S01.T03`
