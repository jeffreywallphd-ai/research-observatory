---
id: ADR-0039
title: Bind approved desktop reference activation
status: Proposed
date: 2026-10-03
deciders: []
linked_tasks:
  - W2.A03.T01
decision_scope: Documentary association of the owner-approved ECR-0011 exact Academic Minimal 1.8 presentation witness and bounded original-task UI continuation control; accepted ADR-0003/0004 and Proposed ADR-0037 remain in force.
affected_paths:
  - packages/contracts/workflow-profile/presentation-compatibility-1.8.json
  - tools/ui_conformance.py
  - design/ui-change.schema.json
  - tools/ui_change_gate.py
supersedes: []
superseded_by: null
---

# ADR-0039: Bind approved desktop reference activation

## Context

Academic Minimal 1.8 was human-approved and published at
`acdc67b616f5ecdec448f57a7efe46e4f359aa9f`, with package SHA-256
`cd8995fdcea2fe44452eaa1fdd258b6f9fab5714cbd443a81a8e5b4251220b94`.
The desktop consumers still select 1.7. The existing presentation verifier
allows the 1.7 identity and appended-region delta, but cannot express the
approved 1.8 date, purpose, page membership, capability, and ordered inserted
regions. The v1.3 UI gate authenticates the previously adopted W2.A01/A02
continuation; it cannot attribute a later independently reviewed 1.8 desktop
activation to the original `CAP-05.S01.T01` claim base
`6506c68461144747b0ee9be10853211717aa381d`.

The repository owner approved the exact ECR-0011/W2.A03 packet for two ordered
tasks. `W2.A03.T01` owns only the witness and protected control extension;
`W2.A03.T02` may later activate desktop consumers and the visual baseline after
T01's independent review. This Proposed companion supplies ADR-0001's
task-linked protected-path association. It is neither a new design approval
nor authority to complete the original task, resume W2, or release the Wave.

## Candidates

1. Relabel the 1.7 witness or baseline, shorten the original task range, or
   accept a later activation by filename. These lose approved semantic or Git
   lineage and can conceal adverse history. Reject.
2. Create a 1.9 reference for the already approved 1.8 behavior or broaden the
   gate for arbitrary later amendments. Neither is justified by the observed
   mismatch. Reject.
3. Authenticate one closed 1.5-to-1.8 presentation transform and one exact
   v1.4 continuation segment, deriving authority from committed Git objects,
   approvals and independent dispositions while retaining prior denials.
   Select under the owner-approved ECR-0011 packet.

## Decision

Add `presentation-compatibility-1.8.json` as a committed, closed witness. The
verifier compares immutable approved 1.5 semantic-source bytes and the actual
approved 1.8 publication/package, with clean regular Git blobs and exact
approval ancestry. `WORKFLOW_CATALOG.json` may change only root reference
identity and version. `CAPABILITY_COVERAGE.json` may additionally change the
date, insert `ingestion-reconciliation.html` immediately after
`document-reader.html` in CAP-05, append CAP-05 to that page's capabilities,
append the specified Source Manager region, set the exact approved Ingestion
Reconciliation and Document Reader purposes, insert four named ingestion
regions immediately before `reversible merge decisions` in approved order,
and append the selected work/version return region to Document Reader. The
verifier compares that closed ordered transform with published bytes; omissions,
extras, changed values, reordering, redirected objects, stale approvals,
dirty inputs and forged package digests deny. The 1.6/1.7 witnesses and their
denials remain valid. This witness proves presentation compatibility, not a
new reference approval or a desktop product.

Add `schemaVersion: "1.4"` solely for future ordinary
`CAP-05.S01.T01` `defect-restoration` against the approved 1.8 package. It
retains the exact v1.3 `adoptedContinuationAuthority`, restoration,
independent current-product classification, full original-base `changedFiles`,
and sole historical `W2.A01.T02` v1.2 contract. It requires one closed
`referenceActivationAuthority` with exact W2.A03/ECR-0011/control/consumer
selectors, approved reference-approval and witness paths, canonical
publication/witness/adoption/reactivation commits, and exact activation UI
file/commit arrays. These are assertions, not self-issued authority: the gate
rederives them from the owner-approved packet, Git history, taskctl state and
independent task, slice, exit and control/security reviews. It authenticates
the inherited W2.A01/A02 chain, frozen independently reviewed CAP-04.S05.T03,
reviewed GOV-MAINT-0025/0026 and W2.C10.T01 ancestry, W2.A03 bootstrap and
control-to-consumer order, original 6506 base,
current owner/lease/branch, and independent 1.8 product/reference capture with
complete producer and dependent-input bindings. Every changed path and
intermediate commit, including additions later reverted, is attributed to an
exact independently reviewed segment. The new witness under `packages/` and
later T02 activation files are admitted only within their respective reviewed
task ranges, never by a generic product or maintenance allowlist. A third
contract, foreign task, forged review, changed byte or Git mode, missing
predecessor, shorter base, stale capture or mixed control/product delivery
denies. Existing v1.0-v1.3 lanes keep their rules and denials.

This is an additive implementation of ADR-0003's approved-reference and
independent-review purpose, with ADR-0004's exact package and baseline lineage
intact. Proposed ADR-0037's narrower adopted-continuation decision remains
unchanged. No accepted decision is superseded, and this record does not grant
new renderer, native, Core, filesystem, network, rights or release authority.

## Consequences

The control must verify more immutable history and independently captured
inputs, so focused real-Git tests and expanded security/control review are
required. Missing or adverse proof remains a denial. `W2.A03.T01` cannot edit
the approved 1.8 reference, assembly scripts, desktop activation or visual
baseline. A reviewed T01 does not prove T02's committed Windows capture, the
original task's real native/Core acquisition, the unresolved intermittent D3D
startup denial, joined CAP-04.S05 evidence, or W2 qualification.

Rollback keeps the approved reference and historical approvals/reviews
immutable. A failure leaves W2 paused and the original task blocked; a
corrected protected control needs a reviewed descendant with ADR association,
not a rewritten witness, erased adverse result or weakened gate.

## Verification

- Focused witness tests compare the actual approved 1.8 publication with the
  frozen 1.5 source, then deny missing, extra, changed and reordered deltas;
  stale package/approval, dirty and redirected inputs also deny. Retain 1.6/1.7
  positive and adverse cases.
- Closed-schema and disposable real-Git v1.4 tests accept only the exact
  original-base two-contract chain and reviewed W2.A01/A02/A03,
  CAP-04.S05.T03, GOV-MAINT-0025/0026 and W2.C10.T01 history. Deny forged
  reviews, wrong predecessor or lease, mutated modes/bytes, missing producer inputs, extra
  contracts and hidden add/revert edits. Replay v1.0-v1.3 cases.
- Run `tools/adr_check.py` across the exact T01 base-to-candidate range and
  obtain independent control/security/ADR disposition on the committed
  candidate. T02 desktop activation/capture, later ordinary-task full-base UI
  gate and native/Core proof, slice/Wave qualification and human release are
  separate gates.

## Task links

- `W2.A03.T01` introduces and independently reviews this exact witness and
  bounded control route.
- `W2.A03.T02` is the ordered activation consumer after T01 approval.
- `CAP-05.S01.T01` is the later original-base restoration consumer only after
  W2.A03 adoption and explicit ordinary Wave resume.
