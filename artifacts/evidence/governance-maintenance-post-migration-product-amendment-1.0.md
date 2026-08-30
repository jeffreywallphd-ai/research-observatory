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

- Focused v4 schema/authority tests, including reservation substitution,
  migration/effective-state substitution, repository-global ECR identity,
  truthful empty histories, exact review-ledger binding, and itemized refactor
  budget denial.
- Existing ECR approval/history tests to prove v1 compatibility.
- Governed Python quality, backlog validation, planning-review validation, and
  Git diff hygiene.
- Independent control/security review of the exact maintenance commit before an
  ECR-0004 packet is treated as reviewable.

## R01 findings and strict-descendant remediation

R01 at `624c3745aa5559b11b7c6fe6727ec382ae11328f` returned
`CHANGES_REQUESTED`. Its immutable ledger is
`artifacts/evidence/governance-maintenance-post-migration-product-amendment-1.0.review-R01.md`.
This successor closes the four findings without changing product or Wave
authority:

1. Reserved approvals must name their unique Git introduction commit; migration
   authority must name the exact last commit of its adopted file and approved
   review; adopted amendments must name the transition commit whose parent was
   not yet ADOPTED.
2. A v4 human approval must bind a separately committed independent-review
   ledger by exact path, hash, introduction/reviewed-state commit, candidate,
   packet hash, reviewer, disposition, findings, closures, and strict one-file
   candidate-to-review delta. A free-form review assertion is denied.
3. The refactor denominator is the exact itemized task inventory read from the
   approved Wave-base backlog blob with fixed S=1, M=3, L=5 points. Refactor
   allocations must match amendment task estimates exactly; omitted, duplicate,
   inflated, inconsistent, or non-finite values are denied.
4. Empty adopted or reserved histories are permitted when truthful, and the
   next ECR identity is derived from the repository-global packet and approval
   namespace rather than from one Wave.

The repository owner subsequently directed that this authentication refactor
must not be constrained by the 15% rule. The generic schema therefore retains
the 15% default but permits a packet-scoped `owner-directed-wave-exception`
that names the exact refactor tasks, authorization, and rationale. The exception
does not hide or alter the itemized denominator, allocation, or computed share,
and it cannot apply to tasks outside the declared scope.
