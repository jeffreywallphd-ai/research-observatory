---
id: ADR-0037
title: Authenticate adopted attachment UI continuation
status: Proposed
date: 2026-10-03
deciders: []
linked_tasks:
  - W2.A02.T01
decision_scope: Documentary association of the owner-approved ECR-0010 with one Git-authenticated adopted-amendment continuation and restoration UI gate lane for the original CAP-05.S01.T01; accepted ADR-0003 remains in force.
affected_paths:
  - design/ui-change.schema.json
  - tools/ui_change_gate.py
supersedes: []
superseded_by: null
---

# ADR-0037: Authenticate adopted attachment UI continuation

## Context

Accepted ADR-0003 requires full task-base UI lineage, approved reference
authority and independently checked restoration classification. The original
`CAP-05.S01.T01` claim retains base
`6506c68461144747b0ee9be10853211717aa381d`, `agent-review`, and no
`experience_change`. Its complete range now includes the separately approved,
independently reviewed and adopted `W2.A01.T02` 1.7-to-1.8 reference and
renderer delivery, plus later T01 restoration. The historical T02 v1.2
contract is valid at its frozen task review, not as a present-day live T02
lease. The existing gate rejects that inherited contract during ordinary T01
and may select `HEAD^` instead of T01's base when no explicit base is supplied.
A short-range pass cannot qualify the original task.

The repository owner approved the exact ECR-0010/W2.A02 packet for a bounded
continuation authority. Academic Minimal 1.8 remains byte-identical and
approved; ECR-0010 does not authorize a 1.9 reference or new interaction.
This Proposed companion provides ADR-0001's task-linked association for the
protected schema/gate change. Its status does not itself approve product work,
modify Accepted ADR-0003, unblock T01, resume W2 or authorize release.

## Candidates

1. Use `HEAD^`, a post-adoption base or T02's old contract as T01's entire
   authority. This would hide the original claim range or replay a historical
   contract outside its reviewed boundary. Reject.
2. Create a 1.9 reference or change the researcher interaction. The observed
   problem is authority attribution for already approved 1.8 behavior, not a
   demonstrated new experience decision. Reject.
3. Add one versioned, exact-task continuation route that authenticates the
   inherited and resumed segments from immutable approvals, Git history,
   review records and current independent conformance evidence. Preserve all
   other routes and denials. Select.

## Decision

Add `schemaVersion: "1.3"` only for ordinary `CAP-05.S01.T01`
`defect-restoration` against approved
`RO-UI-ACADEMIC-MINIMAL-1.8`/`1.8`, with predecessor
`RO-UI-ACADEMIC-MINIMAL-1.7`. A closed
`adoptedContinuationAuthority` names exact `W2.A02`/`ECR-0010`/
`W2.A02.T01` and inherited `W2.A01`/`W2.A01.T02` selectors, the unchanged
historical v1.2 contract path, adoption/reactivation commit anchors, separate
inherited and resumed UI path/commit inventories, and the task-namespaced
independent classification path, SHA-256 and introduction commit. The existing
`restoration` object states the approved interruption and restart behavior.
Contract fields are assertions: the gate derives and checks their values from
committed packets, approvals, taskctl state, reviews and Git objects. No other
version can carry this object, and v1.3 cannot combine it with legacy authority
objects.

Exactly two contracts may appear in T01's complete 6506-base history: the
authenticated historical `W2.A01.T02` v1.2 contract and T01's current v1.3
contract. The gate authenticates W2 and W2.A01 owner approvals, the exact
approved 1.8 publication, T02 claim and independently reviewed candidate,
W2.A01 adoption, W2.A02 approval and reviewed control delivery, T01's
original approved definition, current owner/unexpired lease/branch/base and
explicit reactivation. It attributes every governed reference, renderer,
typed-source, backlog and UI-gate-control commit to its independently reviewed
historical or resumed segment, including intermediate additions and reverts.
The W2.A01.T01 source rounds, separately reviewed reference-verifier/ADR-0036
repair, active UI-gate/fixture maintenance chain, GOV-MAINT-0025
quality-inventory review and W2.A02.T01 control chain are authenticated by
their exact candidate/evidence/review ancestry; filenames or hashes alone do
not grant a general exception. The original T01 task definition comes from
the immutable W2 packet Git blob, not a mutable current projection.

The independent classification must judge the **current committed product**
against the unchanged approved 1.8 package. It binds the exact candidate,
independent reviewer, criterion and report hashes, complete T01 UI history,
paired product/reference captures and producer-input Git blobs. The existing
capture reader covers Core, native Rust, renderer, contract, build and checker
inputs. The gate separately derives the T01-owned tests, fixtures, workers and
other product inputs outside that snapshot, and requires exact
`dependentInputFiles` and blob matches. An omission, redirection, stale
capture, later source or dependent-input touch, even if reverted before HEAD,
denies. T01 cannot edit the approved reference. The classification is not
task approval and cannot replace native/Core acquisition proof.

One exact historical mixed commit is admitted:
`9727f1b195e7dee300e7f3df3c289e7739fb0fdc`. Its immutable
sole-parent tree must show `quality-scope.json` strictly appending exactly
nine canonical regular Python paths newly introduced in that same commit,
with all earlier entries, order, metadata and roots unchanged, alongside
exactly two approved restoration renderer edits and no other gate control.
This check does not assert prior independent approval of 9727 or establish a
reusable mixed-control pattern. A later independent T01 full-candidate review
must examine it and the current product. All other mixed control/product
commits deny. The gate's automatic base selection uses T01's 6506 base only
for the sole authenticated active continuation; it never silently falls back
to `HEAD^` in that state. Other v1.0, v1.1, v1.2 and linked-correction routes
retain their existing requirements, roots, thresholds and denials.

This is an additive, exact implementation of ADR-0003's reference and review
purpose under the owner-approved ECR-0010. It does not supersede ADR-0003,
change the approved 1.8 package or create general ordinary-task authority.

## Consequences

The control must read immutable Git and independently reviewed records across
the complete original range, increasing focused test and review cost. Missing,
forged, stale or unattributed history denies rather than granting a shortcut.
Neither the control task nor this ADR edits a renderer, native boundary, Core
operation, approved reference, original task base, migration or release gate.
The separate intermittent D3D startup denial and exact-candidate native/Core
qualification remain unresolved T01 work after amendment adoption and explicit
W2 resume. Preserve adverse evidence. Rollback of the protected control change
requires a separately reviewed change and ADR association; historical approvals
and reviews remain immutable.

## Verification

- Focused schema and real-Git tests accept only the exact two-contract chain,
  approved 1.7-to-1.8 publication, current independently captured 1.8
  classification, complete dependent-input inventory and exact 6506 automatic
  base. Retain v1.0-1.2 positive and adversarial assertions.
- Reject forged/missing approvals or reviews, extra/mutated contracts, foreign
  task/lease/branch/base, stale captures or producer/dependent inputs, reference
  rewrite, redirected objects, hidden add/revert, changed 9727 tree or Python
  introductions, and any other mixed control/product commit.
- Run `tools/adr_check.py` over the exact W2.A02.T01 base-to-candidate range
  and obtain expanded independent control/security/ADR review before amendment
  exit. The resumed T01 must separately pass the full original-base UI gate,
  exact-candidate native/Core task proof and independent review; later slice,
  Wave and human release gates remain separate.

## Task links

- `W2.A02.T01` installs and independently reviews this bounded control route.
- `CAP-05.S01.T01` is its sole subsequent ordinary-task consumer after W2.A02
  adoption and explicit Wave resume.
