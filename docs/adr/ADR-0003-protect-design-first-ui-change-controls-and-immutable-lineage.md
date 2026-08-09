---
id: ADR-0003
title: Protect design-first UI change controls and immutable lineage
status: Accepted
date: 2026-08-08
deciders:
  - CAP-00 approved experience policy and CAP-00.S06.T03 independent review
linked_tasks:
  - CAP-00.S06.T03
decision_scope: Design-first UI classification, exact task and reference lineage, human approval separation, reference-before-implementation ordering, pull-request enforcement, and protection of the enforcement controls.
affected_paths:
  - architecture-protected-paths.json
  - ci-policy.json
  - ui-change-policy.json
  - design/ui-change.schema.json
  - tools/ui_change_gate.py
  - tools/ci_check.py
  - planning/backlog.schema.json
  - verification-profiles.json
  - quality-scope.json
  - .github/workflows/ci.yml
  - .github/pull_request_template.md
supersedes: []
superseded_by: null
---

# ADR-0003: Protect design-first UI change controls and immutable lineage

## Context

Architecture Baseline 1.3 and the authoritative backlog already require
intentional researcher-facing changes to update and obtain human approval for
the governed UI reference before application implementation. A defect
restoration may instead cite the existing approved reference. Policy text alone
cannot distinguish those paths in automation, bind an implementation to the
exact approved package, prove approval-before-code ordering, or prevent a change
from weakening the checker that reviews it.

CAP-00.S06.T03 must provide a local and pull-request gate without depending on a
network service, mutable working-tree claims, a trusted implementation agent, or
unstructured checkboxes. It must also allow the first implementation of an
already approved page/workflow without incorrectly requiring a new design.

## Candidates

1. Rely on pull-request prose and reviewer memory. This is simple but cannot
   prove exact files, reference hashes, task ownership, or commit ordering.
2. Compare application screenshots only. Visual checks help with conformance but
   cannot establish human approval lineage or distinguish design change from
   restoration.
3. Add a schema-governed per-task change contract and validate immutable Git
   base/head blobs, reference package hashes, task metadata, identities, and
commit ancestry. Protect the checker, policy, schema, CI wiring, and task
schema as architecture-governed controls.

## Decision

Adopt candidate 3. Govern three explicit change kinds:
`intentional-design-change`, `approved-reference-implementation`, and
`defect-restoration`. Every changed researcher-facing implementation range has
one canonical task contract with exact changed-file coverage and focused
evidence. Intentional change requires a different reference than the base,
`approval_kind: human`, a `human:<identity>` approver distinct from the claimed
implementation owner, a task `human-and-agent-review` gate, and an approval
commit that is a strict ancestor of every implementation commit. Conformance and
restoration use the unchanged approved package; restoration also states the
defect and expected approved behavior.

CI supplies the pull-request/push base and checks full Git history. Local runs
may provide the task base explicitly; manual CI requires one, and ambiguous
active-task base selection fails closed. The contract task must be active and
bound to that exact base. Governed UI paths must remain regular Git blobs rather
than symlinks or other redirected object types. Defect restoration retains the
human-and-agent classification gate until the governed conformance verifier is
installed. Gate-control paths become protected
architecture paths, and canonical path inventories are also embedded in the
checker so a policy-only edit cannot silently remove coverage.

## Consequences

UI work gains deterministic, offline, auditable reference lineage and fails
closed for absent, stale, forged, self-approved, same-commit, or incompletely
scoped evidence. Initial approved-reference implementation remains possible, and
restoring a defect does not manufacture a new design decision. Pull requests
must retain full history for ordering checks and carry one small JSON contract;
tasks that intentionally revise experience require both human and independent
agent review.

The gate does not authenticate a human by itself; repository review controls and
the task human gate authenticate the declared human identity. The machine gate
prevents the implementation identity from being reused as approver and verifies
that the exact approval record/package precedes code. Changing the protected
path inventory or enforcement model requires a changed Proposed/Accepted ADR and
review. Rollback requires a superseding ADR because removing the gate would
weaken an established architecture safeguard.

## Verification

- `python tools/ui_change_gate.py --repo . --base <task-base> --head HEAD`
- `python tools/adr_check.py --repo . --base <task-base> --head HEAD`
- `python tools/ci_check.py --repo .`
- `python tools/taskctl.py validate`
- Foundation tests for approved implementation, restoration, missing/stale
contracts, newer human approval, self approval, same-commit ordering, exact
task/range lineage, regular-blob enforcement, ambiguous base selection, human
restoration classification, and gate-control weakening.

## Task links

- `CAP-00.S06.T03`
