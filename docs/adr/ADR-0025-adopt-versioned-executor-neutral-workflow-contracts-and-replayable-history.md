---
id: ADR-0025
title: Adopt versioned executor-neutral workflow contracts and replayable history
status: Accepted
date: 2026-09-01
deciders:
  - W1 repository-owner pre-Wave approval at c5bbd97c0cdc665eecb973f5862478ef7be97752
linked_tasks:
  - CAP-03.S04.T01
decision_scope: Portable workflow definitions, exact run authority, separate execution identities and state machines, append-only transition replay, idempotency and checkpoint semantics, human-task audit authority, security-lock interruption, and the legacy operation projection bridge.
affected_paths:
  - packages/contracts/workflow/**
  - packages/contracts/README.md
  - packages/contracts/package.json
  - packages/contracts/tsconfig.json
  - packaging/build-inputs.json
  - services/core-api/src/research_observatory_core/workflow_contracts.py
  - services/core-api/packaging/sidecar-build.json
  - tools/core_sidecar_build.py
  - tests/contracts/README.md
  - tests/contracts/test_workflow_contracts.py
  - tests/foundation/test_adr_check.py
  - tests/packaging/test_core_sidecar_package.py
  - quality-scope.json
  - docs/architecture/workflow-contracts.md
  - docs/architecture/README.md
supersedes: []
superseded_by: null
---

# ADR-0025: Adopt versioned executor-neutral workflow contracts and replayable history

## Context

Research Observatory must run long scholarly work locally through application
and worker restarts while preserving the same workflow meaning for a later
server executor. The current bounded `OperationRegistry` is intentionally an
in-memory transport/status seam. It cannot become durable workflow authority,
and its legacy `op-*` identity and five-state projection cannot be silently
reinterpreted as the richer canonical workflow history.

The approved W1 CAP-03-D03 decision and CAP-03.S04 plan require versioned plan
data, at-least-once activities, stable idempotency, checkpoints, cooperative
cancellation, immutable artifacts, explicit progress, separate workflow/step/
job/attempt/human-task identities, and future server conformance. ADR-0013 fixes
portable UUIDv7 identities, ADR-0024 fixes scholarly provenance, ADR-0011 fixes
the current operation projection, and ADR-0018 requires application lock to stop
protected work unless a future explicit checkpointed allowlist is approved.

## Candidates

1. Promote the current in-memory operation projection into the durable model.
   This minimizes types but loses definition versioning, retries, checkpoints,
   human tasks, exact history, and executor portability.
2. Store executor-native definitions and histories: Python callables/SQLite
   implementation records locally and Temporal-native histories later. This
   makes each deployment authoritative in a different language and prevents
   deterministic project portability.
3. Define one strict, versioned, deployment-neutral workflow contract with
   separate definition and execution documents, typed activity-port names,
   append-only transition history, deterministic replay, exact authority
   references, and generated TypeScript/Python decoders. Keep local/server
   executor metadata in the run snapshot and preserve the operation API through
   an explicit projection bridge.

## Decision

Adopt candidate 3. A `WorkflowDefinition` is immutable declarative data. It
contains exact input/output schema references, an acyclic step graph, registered
activity or human-task kinds, bounded permission/resource declarations, retry,
idempotency, checkpoint, cancellation, and progress policy. It contains no
executor profile, SQLite/Temporal type, filesystem path, URL, closure, shell
command, raw research payload, secret, or provider SDK object.

A `WorkflowSnapshot` binds the exact definition ID, revision, semantic version,
and canonical content hash, plus exact Research Intent, policy, configuration,
project, and executor-contract references. The executor profile is runtime
metadata (`local` or `server`) and never changes the definition bytes. Unknown
major contract/history versions fail explicitly; running history is never
silently upgraded or mutated in place.

Workflow run, step run, logical job, physical attempt, checkpoint, artifact,
human task, human decision, and transition event have distinct identities.
Each stateful entity uses its own transition table. Append-only events have one
global contiguous sequence, exact from/to state, trusted actor, reason, and
optional progress/checkpoint/decision binding. A newly instantiated reducer
must reconstruct every current projection and its last revision exactly from
the serialized history. Terminal entities do not transition; resumed or
continued terminal work receives a new run/continuation identity.

Activity execution is at-least-once. A logical job keeps one idempotency key and
one canonical command fingerprint across physical attempts. Exact replay may
return the already committed outcome; reuse with changed command authority is a
conflict. Attempts are contiguous, at most one attempt succeeds, and a
succeeded job binds that exact attempt and only committed immutable outputs.
This is not an exactly-once side-effect claim.

Checkpoints bind one attempt, a contiguous per-attempt checkpoint sequence, the
exact global history position, an immutable state hash, and a content-addressed
payload artifact reference. Progress is quantified, unknown, or not applicable;
quantified attempt progress is monotonic. Cancellation is cooperative and
records the disposition of partial artifacts. If cancellation races an output
commit, only the revision/precondition-authorized terminal transition can
accept the committed result; other artifacts remain explicitly incomplete,
quarantined, or discarded.

A `HumanTask` binds its exact run, definition revision, step run, required role,
requester, assignee, evidence, decision schema, and allowed consequences. A
completed task has one immutable decision from the trusted assigned human actor,
and the completion event binds the exact decision ID and timestamp. Missing,
late, cross-run, wrong-role, or substituted decisions fail closed. Workflow
history records execution authority; ADR-0024 provenance records consequential
scholarly transformations; telemetry remains operational and retention-bounded.
Failed or cancelled attempts cannot claim accepted provenance outputs.

The legacy operation bridge binds one exact `op-*` operation projection to one
UUIDv7 workflow run and snapshot revision while retaining the existing five
states, cancellation flag, sequence, ETag, and bounded replay semantics. It is a
compatibility projection only. Application-lock interruption is distinct from
ordinary crash/restart: a security-lock event cannot auto-resume the same run.

## Consequences

Local and later server executors can validate the same exact definition bytes
and produce histories with the same semantic invariants. TypeScript and Python
consumers receive immutable generated snapshots and deterministic canonical
records. The stricter identity graph makes retry, cancellation, human review,
and restart behavior inspectable without exposing executor internals or
research content.

The contract is intentionally more detailed than the operation transport
projection. T02 must implement SQLite tables, migrations, atomic queue/
provenance transactions, leases, heartbeat, process recovery, resource pools,
and cancellation-versus-commit preconditions without weakening these semantics.
T03 must project them through the existing Core API and approved Task Center
experience. Server workflow infrastructure remains release-gated to W10/W11.

No released durable workflow rows exist, so T01 adds no database migration and
does not mutate the existing aggregate `workflows` subtype table. Rollback
before T02 persistence removes the unused v1 contract and bridge. After durable
v1 histories exist, rollback requires retaining their exact bytes or a tested
reader/upcaster; histories and accepted human decisions are never rewritten.

## Verification

- Draft 2020-12 schema and deterministic schema-hash/generator checks;
- shared local/server definition conformance fixtures;
- TypeScript/Python strict decoding and immutable-snapshot parity;
- deterministic serialize/reload/replay in a new reducer;
- separate transition, terminal, progress, retry/idempotency, checkpoint,
  artifact, cancellation, security-lock, reference, and human-decision tests;
- legacy operation identity/state/sequence/cancellation/ETag projection tests;
- service contract, architecture/ADR, quality, packaging-inventory, and
  generated-artifact checks;
- T02 real SQLite/process restart and T03 Core/UI integration evidence.

## Task links

- `CAP-03.S04.T01`
