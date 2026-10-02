---
id: ADR-0036
title: Verify exact amendment reference approval metadata
status: Proposed
date: 2026-10-02
deciders: []
linked_tasks:
  - W2.A01.T02
decision_scope: Bounded verifier repair for exact human actor spelling and proposal-bound optional deferred_surfaces in amendment reference approvals; existing amendment, design-first, and publication authority remain in force.
affected_paths:
  - tools/ui_conformance.py
supersedes: []
superseded_by: null
---

# ADR-0036: Verify exact amendment reference approval metadata

## Context

The owner-approved ECR-0009 packet binds the proposed Academic Minimal 1.8
reference. Its `APPROVAL.yaml` omits `deferred_surfaces`, and the immutable
W2.A01 approval record names `approvedBy: human:repository-owner`. The current
conformance verifier requires `deferred_surfaces` for amendment approvals and
prefixes every record actor with another `human:`. It would reject an exact 1.8
publication even when the approved proposal and human record match. Adding an
unreviewed `deferred_surfaces` field to the published approval would instead
change the proposal's governed bytes and fail the publication comparison.

The current verifier accepts the older full-field amendment approvals. One
accepted 1.4 approval predates packet-bound reference inventories, while the
accepted 1.6 packet binds one proposed approval file. Both are immutable
predecessor evidence and must remain valid without a broad missing-proposal
exception. ADR-0003's design-first human approval and reference-before-renderer
ordering remain unchanged. ADR-0035 governs the distinct W2.A01.T02 UI gate lane.

## Candidates

1. Add `deferred_surfaces: []` during publication or rewrite the approved
   proposal. This changes the owner-reviewed reference shape. Reject.
2. Treat the field as universally optional and accept any actor spelling. This
   could admit an unbound approval or mask a substituted approver. Reject.
3. Accept omission only for an exact authority-bound amendment shape whose
   packet's committed proposal also omits the field. Compare every non-metadata
   approval field with that proposal, and normalize an already-prefixed human
   actor without changing the required publication identity. Select.

## Decision

The conformance shape check admits the existing closed amendment authority
record with or without `deferred_surfaces`; all other keys and authority fields
remain exact. The authority check reads the one regular Git proposal blob named
and SHA-256-bound by the approved packet at its immutable commit. It compares
the proposal and publication after excluding only the enumerated approval
metadata: status, approval kind, approver, approval time, basis, and authority.
The omission or addition of `deferred_surfaces`, as well as any scope or contract
change, therefore denies. A missing, duplicated, redirected, unreadable, or
hash-mismatched proposal denies.

The approval record's actor is canonical when it already begins with `human:`;
otherwise the existing bare historical actor receives that prefix. The
published approval must still contain the exact single-prefix `human:<identity>`
required by the shape validator and match the authenticated record. The one
accepted 1.4 approval without a packet proposal inventory retains its
predecessor behavior only at its exact approval commit and blob digest; no new
approval can claim that exception. Full package reproduction against ECR-0009
remains independently enforced by the existing publication control.

## Consequences

The exact 1.8 approval can publish without inventing a field or changing the
reviewed proposal. Missing proposal authority, substituted scope, actor, or
approval bytes continue to deny. The added Git reads are confined to the
amendment reference approval boundary and do not add a network dependency,
renderer permission, native file path, Core operation, or release decision.
This Proposed companion documents a verifier repair; it does not accept the
reference, finish W2.A01.T02, or supersede ADR-0003.

## Verification

- Real-Git approval/package fixtures reproduce the prefixed actor and omitted
  field failure before the repair and pass only with the exact packet proposal.
- The same fixtures deny proposal omission, mismatched proposal digest, added
  `deferred_surfaces`, omitted declared `deferred_surfaces`, and changed scope.
- Historical 1.4 and 1.6 reference approvals retain exact package validation.
  Existing approval-shape and authority-lineage regressions remain required.
- Independent control/ADR review and an exact base-to-candidate `adr_check` run
  precede integration. Reference publication, renderer and native/Core proof
  remain separate W2.A01.T02 and CAP-05.S01.T01 obligations.

## Task links

- `W2.A01.T02` consumes the exact owner-approved 1.8 reference after this
  bounded verifier repair is independently reviewed.
