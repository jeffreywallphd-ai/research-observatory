---
id: ADR-0055
title: Recognize independently reviewed approved corrective metadata
status: Proposed
date: 2026-10-11
deciders: []
linked_tasks:
  - CAP-05.S06.T02
decision_scope: Read-only recognition of exact immutable owner-approved and independently reviewed metadata in existing corrective scope verification. No task state, product authority, or UI criterion change.
affected_paths:
  - tools/ui_change_gate.py
supersedes: []
superseded_by: null
---

# ADR-0055: Recognize independently reviewed approved corrective metadata

## Context

Normal W2.C18.T01 submission rejects metadata explicitly granted by
ECR-0014/W2.A06 because its installed scope exception recognizes independently
reviewed control maintenance, not approved amendment metadata. The original
rejection and frozen approvals remain unchanged. The owner approved the exact
bounded consumer, tests, and associated ADR/index exception in
`artifacts/evidence/W2.C18.T01.closeout-compatibility-decision-01.json`.
ADR-0054 remains reserved for the separately approved A06 product restoration.

## Candidates

1. Preserve the demonstrated submission block.
2. Add a generic read-only recognizer using existing immutable authority
   consumers, exact independent disposition, and complete Git bindings.
3. Widen filenames or manually replace normal task state. Rejected.

## Decision

This is a Proposed implementation record under the exact approved exception,
not an Accepted or superseding architecture decision. Retain existing task,
corrective scope, source, reference, and submission predicates. Recognize only
metadata commits individually bound by an immutable independent task-owned
disposition to an owner-approved same-Wave v4.1 packet. Reuse existing approval
and independent packet-review consumers; approved patterns alone grant nothing.

Pin every extra commit, path, Git object, and raw digest in the reviewed range.
Unknown or altered authority, incomplete or merged history, self-review,
unsupported source/schema/reference paths, redirected objects, and stale or
unauthenticated generated-output inputs deny. Bind retained generated integrity
evidence and unchanged generator/checker source. Later data needs a new complete
independent round. No new controller, schema file, generator, or product scope.

## Consequences

Explicitly approved metadata can pass the existing normal submission boundary
without granting reusable source permission. The normal maintenance chain still
authenticates this protected source, tests, ADR/index, and its separate evidence
and review deliveries. All changes and adverse records remain append-only.
This change does not implement the separately approved direct UI selectors or
lineage method, replace capture predicates, approve a task, close recovery
findings, or authorize release. Failed controls block use; rollback preserves
history and evidence.

## Verification

- Real disposable Git tests exercise schema-valid v4.1 authority, independent
  packet review, exact metadata inventory, unknown later data, forged authority,
  self-review, malformed records, source/reference/schema additions, merges,
  executable objects, and intermediate add/revert changes.
- Normal isolated taskctl exact-evidence validation retains candidate, branch,
  worktree, full diff, criterion, and passing-check requirements.
- Existing affected corrective and associated-ADR maintenance tests, source
  style/type checks, and ADR/protected-path association checks remain required.
- Results belong to actual retained receipts and independent review; this
  Proposed record asserts no successful execution or task approval.

## Task links

- `CAP-05.S06.T02` is the existing ordinary origin of active correction
  `W2.C18.T01`. The associated-ADR consumer requires the ordinary origin in
  `linked_tasks`; the correction is implementation context.
