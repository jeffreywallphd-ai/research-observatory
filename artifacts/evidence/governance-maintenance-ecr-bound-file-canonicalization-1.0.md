# Governance maintenance increment: Git-canonical governed-file binding

- **Predecessor commit:** `5423e4c918ad6aa71653e04a36545674e78c7423`
- **Authority:** `GOV-MIG-0001`, the governance-automation simplification rule in
  `AGENTS.md`, and blocking finding `ECR-0007-R01-F01` in
  `planning/enabler-change-requests/ECR-0007.review-R01.json`.
- **Risk tier:** 2. This corrects approval validation at a Git persistence
  boundary but grants no product, experience-reference, amendment-execution,
  Wave-resume, task, release, gate, or remote authority.
- **Quiescent boundary:** W1 remains `PAUSED` at ordinary Wave scope;
  `CAP-07.S01.T02` remains `BLOCKED`; no product implementation for ECR-0007
  has started; no ordinary W1 task is `IN_PROGRESS` or `REVIEW`.

## Exact defect

The ECR v4 governed-experience validator hashed raw Windows checkout bytes and
compared those bytes directly with the immutable candidate blob. Git correctly
normalizes `design/ui-reference/assets/tokens.css` to LF in the repository while
the Windows checkout materializes CRLF. The file is clean and semantically
identical under Git's configured attributes, but the raw-byte comparison binds
the pending packet to workstation materialization and makes exact-commit
approval fail.

R01 therefore found that ECR-0007 carried the checkout SHA-256
`475da960ade048a4a0989dfd42cbcae974b82aedc7b13e18af77e6216bdff230`
instead of the immutable Git-blob SHA-256
`e6aa1ebf847e983f4f5c9d20ad0e753716737cdfbedf617df2292bf510bebfa5`.

## Intended projection delta

1. For a tracked governed file that is clean relative to the comparison commit,
   hash the exact Git blob so the declared digest is repository-stable.
2. For a new or materially modified pending file, continue to hash the local
   bytes so an uncommitted proposal remains reviewable before candidate freeze.
3. For approved validation, require the file to exist in the exact packet
   commit and use Git's clean-filter-aware comparison to prove that the current
   worktree has not materially diverged from that commit.
4. Fail closed when Git cannot perform a required comparison, and retain all
   safe-path, duplicate-path, missing-file, hash, and immutable-commit checks.

## Invariants and exclusions

- No approved UI-reference byte, manifest, reference ID, product style, or
  behavior changes in this maintenance increment.
- No ECR packet, review ledger, approval, backlog, task state, Wave state,
  recovery hold, or release gate is rewritten or advanced.
- A CRLF/LF materialization difference is accepted only when Git reports the
  path clean under repository attributes; a semantic edit still fails both
  pending hash binding and exact-commit validation.
- The adverse R01 ledger remains immutable. ECR-0007 remediation must be a
  separately committed strict descendant and must receive an independent R02
  disposition.
- The protected untracked `artifacts/evidence/W1.A04.B00.json` witness is not
  read, edited, moved, deleted, hashed, or staged.

## Selected checks before candidate freeze

- Focused CRLF fixture covering pending and exact-commit validation against an
  LF Git blob, plus semantic-change denial.
- Complete `tests.foundation.test_planctl_amendments` and
  `tests.foundation.test_plan_review_amendments` suites because the helper is a
  shared v4 proposal/approval boundary.
- Governed Python quality, task/backlog validation, planning-review validation,
  UI-reference integrity, generated-view freshness, and Git diff hygiene.
- Live ECR-0007 validation must reject the pre-remediation workstation hash;
  after R02 replaces it with the immutable blob hash, the same validator must
  pass.
- Independent control/security review of the exact maintenance candidate before
  ECR-0007 R02 is frozen.

## Pre-freeze results

- Focused Git-attributes regression: **PASS**, including clean CRLF/LF
  normalization, untracked pending-file hashing, semantic-change denial, and
  invalid-commit fail-closed behavior.
- Amendment-control suites: **PASS**, 27 tests in 216.332 seconds, including the
  new regression and the complete amendment review-rendering suite. The added
  pending-file and Git-error assertions also pass in the final focused rerun.
- Ruff formatting and lint over the two changed Python files: **PASS**.
- Full governed Python quality was attempted and exposed an unrelated
  predecessor defect: tracked `tests/e2e/test_workflow_profile_matrix.py`
  (introduced by `8c1afd658b8161b3ef4c81b61fcdf9ca4daa670a`) is absent from the explicit
  quality inventory. Direct mypy over the changed files also reaches two
  pre-existing `arg-type` diagnostics at `tools/planctl.py:1470`, last changed
  by `515fa32cb`. Neither path or line is changed by this increment; broadening
  the candidate to repair them would violate its bounded purpose. They remain
  due before W1 exit qualification.
- Backlog validation: **PASS**, 20 capabilities, 117 slices, 365 tasks, 12
  release gates.
- Planning review check: **PASS**, 491 HTML pages. Generated backlog views:
  **PASS**, no changes. Approved UI-reference integrity: **PASS**, 55 governed
  files and reference `RO-UI-ACADEMIC-MINIMAL-1.5` unchanged.
- Live ECR-0007 validation: expected pre-remediation **DENIAL** only for the old
  checkout-byte `tokens.css` hash, proving that R02 must bind the Git-blob hash.
- Git diff hygiene: **PASS**.
