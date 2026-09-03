---
id: ADR-0026
title: Adopt governed workflow profiles and history-preserving navigation state
status: Accepted
date: 2026-09-03
deciders:
  - W1 repository-owner pre-Wave approval at c5bbd97c0cdc665eecb973f5862478ef7be97752
  - ECR-0005/W1.A06 repository-owner approval at f48f11ed12c10d26acb1b80053e1a823c3ee5c16
linked_tasks:
  - CAP-03.S06.T01
decision_scope: Exact governed workflow-profile catalog projection, immutable project selection lineage, navigation-stage state separate from analytical execution, supporting-tool return context, and history-preserving profile migration.
affected_paths:
  - packages/contracts/workflow-profile/**
  - packages/contracts/README.md
  - packages/contracts/package.json
  - packages/contracts/tsconfig.json
  - packaging/build-inputs.json
  - services/core-api/src/research_observatory_core/workflow_profile_contracts.py
  - services/core-api/packaging/sidecar-build.json
  - tools/core_sidecar_build.py
  - tests/contracts/README.md
  - tests/contracts/test_workflow_profile_contracts.py
  - tests/packaging/test_core_sidecar_package.py
  - quality-scope.json
  - docs/architecture/workflow-profile-contracts.md
  - docs/architecture/README.md
supersedes: []
superseded_by: null
---

# ADR-0026: Adopt governed workflow profiles and history-preserving navigation state

## Context

Research Observatory must turn a selected scholarly objective into a clear,
versioned primary path while preserving researcher authority, prior work, and
access to the full workbench. The approved Academic Minimal 1.5 reference has
fourteen workflow profiles, but it is an experience catalog rather than durable
project authority. It cannot be copied into application code as an unversioned
switch statement or inferred from the last page visited.

ADR-0022 establishes immutable accepted Research Intent references. ADR-0025
establishes executor-neutral workflow definitions and execution history with
logical jobs and physical attempts. Navigation progress is related to both but
is not either one: completing a background job cannot by itself assert that a
researcher completed a consequential scholarly stage. ECR-0005/W1.A06 binds
CAP-03.S06 to the exact fourteen-profile Academic Minimal 1.5 catalog.

## Candidates

1. Derive navigation from current route and analytical job status. This is
   simple, but loses restart authority, conflates computation with scholarly
   completion, and silently rewrites meaning when route order changes.
2. Copy profile order into application services and migrate projects to the
   newest profile automatically. This makes the Core authoritative, but permits
   drift from the governed experience and rewrites prior researcher context.
3. Generate one strict portable profile catalog from the exact governed
   experience catalog; store immutable intent-bound selection revisions and
   separate navigation-stage revisions; require an impact preview and explicit
   history-preserving migration for a profile change. Keep persistence and UI
   adapters outside the contract.

## Decision

Adopt candidate 3. `WorkflowProfileCatalog` is a deterministic projection of
the exact `RO-UI-ACADEMIC-MINIMAL-1.5` `WORKFLOW_CATALOG.json` bytes and the
matching page contracts. Generation fails closed if the governed reference,
catalog hash, version, profile identities, or profile order changes. Each of
the fourteen profiles has exact identity and source hash, ordered primary
stages, optionality, an explicit linear/revisitable cycle policy, expected
outputs, and a supporting-tool policy. Because Academic Minimal 1.5 does not
declare stage-specific checkpoint authority, the projection records that state
as unknown instead of inventing completion gates.

`ProjectWorkflowSelection` is a project-owned immutable revision selected by a
human. It uses a stable selection aggregate ID plus a distinct UUIDv7 revision
ID, and binds one full accepted Research Intent reference and one exact profile
reference, including the governed reference, catalog, profile, revision, and
content hashes. Revision one has no predecessor or impact preview. A later
revision retains the aggregate ID, binds its immediate predecessor, and carries
a matching impact preview that enumerates affected prior stage-state revisions.
Historical selection and stage records remain immutable.

`WorkflowStageState` is navigation and scholarly-gate state only. It binds the
exact project, selection, and profile plus one primary or supporting route,
stable aggregate/revision identity, pass number, status, completion evidence,
attention/blocking reason, skip rationale, and staleness causes. A
supporting route must retain an exact return to the current primary stage. The
contract rejects analytical job/attempt/queue fields; ADR-0025 remains the sole
execution-history authority. A completed stage requires evidence identity,
attention requires an explicit reason, and stale requires explicit causes.

`WorkflowProfileMigration` binds exact source and target profiles, preserves
history, requires human acceptance, and supplies exactly one disposition for
every source stage. Additions or changes to a profile require a versioned,
reviewed workflow catalog and governed reference update. Unknown major versions
and unknown fields fail closed. Matching generated TypeScript and Python
decoders return owned immutable snapshots and deterministic canonical hashes.

## Consequences

Project navigation can survive process restart without treating background-job
success as researcher approval. UI and service consumers share one exact
portable vocabulary for ordered, optional, cyclical, supporting, current,
completed, attention, and stale states. Profile changes are previewable and
auditable, and prior work cannot be silently relabeled under a new profile.

The strict hash binding means even a benign profile copy edit requires the
governed reference/version workflow; this is intentional because it changes
the scholarly path shown to researchers. Supporting tools stay available and
cannot grant authority beyond the selected intent or project policy.

This task adds no database migration because no workflow-profile selection or
stage-state rows exist. CAP-03.S06.T02-T04 own commands, persistence,
provenance/outbox integration, restart behavior, and desktop projections. Until
then the new contract is unused by production state and can be rolled back by
removing the package. Once v1 records exist, rollback must retain an exact v1
reader or a reviewed migration; accepted history is never rewritten.

## Verification

- Draft 2020-12 validation and deterministic catalog/schema generator drift;
- exact fourteen-profile, governed-reference, order, optionality, cycle,
  supporting-tool, and output fixtures;
- TypeScript/Python parity, strict decoding, owned immutable snapshots, and
  stable canonical hashes;
- immediate selection lineage and impact-preview substitution denials;
- navigation-versus-job separation, status/evidence consistency, and explicit
  supporting-tool return denials;
- complete migration coverage, duplicate/missing mapping denials, and preserved
  history/human acceptance;
- contract-package typecheck, architecture/ADR/quality checks, and frozen
  sidecar/build-input inventory tests.

## Task links

- `CAP-03.S06.T01`
