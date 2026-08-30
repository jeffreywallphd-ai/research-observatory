# Governance maintenance increment: post-migration product amendment packets

- **Predecessor commit:** `c532570`
- **Authority:** `GOV-MIG-0001`, the repository workflow in `AGENTS.md`, and the
  repository-owner request to add bounded CAP-02 authentication work to W1.
- **Risk tier:** 2. This changes planning/approval validation but grants no
  product, task, amendment-execution, Wave-resume, gate, or remote authority.
- **Quiescent boundary:** W1 is PAUSED at ordinary Wave scope;
  `CAP-03.S04.T01` is BLOCKED with no product implementation started; no task is
  IN_PROGRESS or REVIEW; no recovery hold or amendment campaign is active.

## Exact compatibility defect

The adopted W1 authority ledger contains W1.A01 through W1.A03. The immutable
approval for ECR-0003/W1.A04 exists, but its incident-specific bootstrap never
materialized and `GOV-MIG-0001` superseded that controller path while preserving
the approval as historical input. Reusing W1.A04 would overwrite immutable
authority; proposing W1.A05 through the legacy v2/v3 packet format would falsely
require the retired recovery hold and would omit the reserved identity.

## Intended projection delta

1. Add one v4 ECR packet schema for post-migration product/security/experience
   authority. It must freeze the approved Wave base, every adopted amendment,
   every approved-but-unmaterialized superseded reservation, and the exact
   adopted migration authority.
2. Allow amendment-local slice contributions to be assigned to an existing CAP
   while retaining flat amendment task identities for the current execution
   adapter.
3. Enforce the 15% refactor budget, exact slice-to-task partition, governed
   experience file hashes, PAUSED/quiescent Wave state, no active recovery hold,
   and no overlapping amendment campaign.
4. Let exact-commit human approval coexist only with the already-authenticated
   historical W1.A04 witness. Tracked changes and every other untracked path
   remain denied.

## Invariants and deferred work

- Existing v1/v2/v3 schemas and validators remain historical and unchanged.
- W1.A04 is never reused, adopted, rewritten, or silently omitted.
- This increment validates an inert packet only. It does not append W1.A04 or
  W1.A05 to the backlog and does not implement product behavior.
- The exact human-approved W1.A05 bootstrap, if later authorized, must add the
  generic taskctl materialization transition that records the historical
  reservation and appends W1.A05 without reviving a GRR/GCR controller.
- Product implementation remains impossible until independent packet review and
  exact-commit human approval.

## Selected checks

- Focused v4 schema/authority tests, including reservation substitution and
  over-budget denial.
- Existing ECR approval/history tests to prove v1 compatibility.
- Governed Python quality, backlog validation, planning-review validation, and
  Git diff hygiene.
- Independent control/security review of the exact maintenance commit before an
  ECR-0004 packet is treated as reviewable.
