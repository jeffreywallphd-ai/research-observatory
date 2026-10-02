---
id: ADR-0035
title: Admit exact intentional amendment UI lineage
status: Proposed
date: 2026-10-02
deciders: []
linked_tasks:
  - W2.A01.T01
decision_scope: Documentary association of the owner-approved ECR-0009 intentional UI amendment with a narrow, Git-authenticated design-first gate lane for W2.A01.T02; accepted ADR-0003 remains in force.
affected_paths:
  - design/ui-change.schema.json
  - tools/ui_change_gate.py
supersedes: []
superseded_by: null
---

# ADR-0035: Admit exact intentional amendment UI lineage

## Context

Accepted ADR-0003 requires an intentional renderer change to follow a human-approved
new reference, with that approval strictly before implementation and independent
review of the task. Its ordinary-task encoding requires `experience_change` and
`human-and-agent-review`. The approved ECR-0009 packet materializes
`W2.A01.T02` through the amendment v4.1 task schema, which forbids both fields.
The existing UI gate consequently cannot admit the specifically approved
Academic Minimal 1.8 selected-version attachment interaction without a bounded
control extension. It must not mistake an amendment task's missing fields for
permission to bypass ADR-0003's human approval or review purpose.

The repository owner approved the exact ECR-0009 packet and proposed reference
in `planning/wave-amendment-approvals/W2.A01.json`. That approval authorizes
`W2.A01.T01` to install this gate extension and requires its independent
control/security review before `W2.A01.T02` starts. It does not activate the
reference, prove native/Core attachment, or approve W2 release. This Proposed
companion supplies ADR-0001's task-linked protected-path association; its status
does not itself grant new product, security, or architectural authority.

## Candidates

1. Add the ordinary `experience_change` and `review_gate` fields to the
   amendment task or infer them from a contract label. The approved amendment
   schema rejects those fields, while self-asserted labels cannot authenticate
   human authority. Reject.
2. Exempt amendment tasks from the intentional UI gate or accept a newer
   reference without full history. That would admit unrelated amendments,
   forged approvals, same-commit approval, and hidden add/revert edits. Reject.
3. Add a versioned, exact-task lane that derives its authority from immutable
   packet, approval, task, reference, lease, and independent-review history.
   Keep ordinary and restoration lanes unchanged. Select.

## Decision

Add `schemaVersion: "1.2"` solely for `W2.A01.T02` with
`changeKind: "intentional-design-change"`, reference ID
`RO-UI-ACADEMIC-MINIMAL-1.8`, version `1.8`, and predecessor
`RO-UI-ACADEMIC-MINIMAL-1.7`. Its closed `intentionalAmendmentAuthority`
object names `W2.A01`, `ECR-0009`, `W2.A01.T01`, and the exact new reference
approval-record path. Those names select the lane; they are never proof by
themselves. The gate authenticates the immutable ECR packet and its hash-bound
proposal, the human approval record and introduction, the exact materialized
task inventory, the committed independent `W2.A01.T01` disposition, the current
`W2.A01.T02` owner/lease/branch/base, and the 1.8 approval and published package
against committed Git objects. Every governed UI and reference path and every
intermediate commit in the task-base range is checked, including reverted edits
and redirected objects. Human reference approval must strictly precede each
renderer implementation commit. Control edits cannot be mixed into that
renderer delivery or self-authorize it. Taskctl may record backlog transitions
in separate commits, but no commit may change `planning/backlog.yaml` together
with governed reference or renderer files. Admitted `.d.ts` typed product-source
files obey the same publication order and backlog separation; their per-commit
history is recorded separately from governed `uiFiles` and cannot hide an
add-then-revert edit.

The owner-approved ECR authority plus the independent `W2.A01.T01` and
`W2.A01.T02` reviews provide the exact amendment-specific substitute for the
two ordinary-task fields that the amendment schema cannot carry. This is an
additive implementation of ADR-0003's design-first and review purpose for one
named task, not a generic amendment exception or a silent supersession of its
accepted ordinary-task decision. Existing `1.0` ordinary and linked-restoration
contracts and `1.1` resumed-restoration contracts retain their validation and
denials. No policy root, threshold, reference-history rule, or CI base is widened.

## Consequences

The reference publication must reproduce the approved proposal, with only
enumerated approval metadata and derived hash changes, in a distinct commit
before renderer work. The renderer may carry only opaque native intents and
typed outcomes; production choose/drop/attach stays unavailable until the
original `CAP-05.S01.T01` adds and qualifies the trusted native/Core boundary.
This ADR neither authorizes renderer file paths/bytes or stock Tauri path-drop
events nor counts mock UI behavior as real acquisition proof. Document Reader
opening remains `CAP-05.S04` work under ADR-0029.

The extension adds a narrow review burden and no persistence migration or
remote service. A failed, incomplete, stale, or substituted chain denies UI
qualification; preserve adverse evidence and repair in a reviewed descendant.
Rollback of the protected control change requires a separately reviewed
change and ADR association. Do not remove the historical approval, rewrite
Academic Minimal 1.7, or relax the ordinary gate to make rollback pass.

## Verification

- Schema and real-Git gate fixtures accept only the exact `1.2` task/packet/
  reference chain and reject substituted labels, proposal bytes, approvals,
  claim owner/lease/branch/base, extra contracts and out-of-envelope files,
  redirected objects,
  hidden add/revert history, and approval in or after renderer code.
- Existing `1.0` and `1.1` positive and denial fixtures retain their assertions.
  The complete exact-base `ui_change_gate` run remains required for T02.
- Run `tools/adr_check.py` over the exact T01 base-to-candidate range. Expanded
  independent control/security review checks the gate, schema, this Proposed
  companion, and the one appended index entry before T02 starts.
- T02's exact reference-publication reproduction, renderer contract, mounted
  behavior, and independent task/slice reviews remain separate evidence. The
  original task must later prove real native/Core acquisition before W2 exit.

## Task links

- `W2.A01.T01` introduces and independently reviews this bounded gate lane.
- `W2.A01.T02` is its sole admitted intentional UI consumer.
