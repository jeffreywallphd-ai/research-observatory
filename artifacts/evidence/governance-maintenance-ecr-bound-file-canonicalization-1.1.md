# Governance maintenance supplement: review-site canonical governed-file binding

- **Predecessor commit:** `4eaa413b23d72c52d2229574d9fbb76ef6ea7338`
- **Authority:** `GOV-MIG-0001`, the bounded increment recorded in
  `governance-maintenance-ecr-bound-file-canonicalization-1.0.md`, its
  independent approved R01 review, and the deterministic integration failure
  produced while applying `ECR-0007-R01-F01` remediation.
- **Risk tier:** 2. This completes the same generic approval/review projection
  correction and grants no product, experience-reference, ECR execution, Wave,
  task, release, gate, or remote authority.
- **Quiescent boundary:** W1 remains `PAUSED`; `CAP-07.S01.T02` remains
  `BLOCKED`; ECR-0007 is pending and non-executable. Uncommitted R02 proposal
  edits exist locally but are excluded from this supplement candidate.

## Newly exposed integration defect

The exact 1.0 candidate correctly canonicalized v4 governed-file validation in
`planctl`, and its independent review was truthful for that three-file scope.
When the ECR-0007 token digest was then replaced with the approved immutable
Git-blob hash, `planctl ecr validate ECR-0007` passed, but
`plan_review_site.py` independently re-hashed raw checkout bytes and failed with
`ECR-0007 governed experience hash mismatch`. The generated review projection
therefore retained a second checkout-specific implementation of the same
boundary.

This is consequential evidence discovered after the 1.0 review, not a reason to
rewrite its candidate or approval. The 1.0 implementation and review remain
immutable historical inputs; this strict-descendant supplement closes the
omitted generator consumer.

## Intended projection delta

1. Reuse `planctl._bound_repository_file_errors` from the review-site loader so
   the validator and generator share one safe-path, duplicate, existence, Git
   canonicalization, pending-local, hash, and failure semantic.
2. After shared validation succeeds, project the already authenticated declared
   digest into the generated manifest instead of re-hashing workstation bytes.
3. Add a review-site integration fixture with an LF Git blob, forced CRLF
   worktree materialization, successful pending projection, and semantic-change
   denial.

## Invariants and exclusions

- Declared ECR source files retain their existing exact-byte checks; only the
  v4 governed-experience file path uses Git clean-filter semantics.
- The generator cannot accept a value the shared validator rejects, and a dirty
  semantic change still fails before any generated page is written.
- No ECR-0007 source or generated page, approved UI-reference byte, backlog,
  task/Wave state, approval, product code, or release authority is part of this
  candidate.
- The 1.0 maintenance record and approved review remain unchanged. This
  supplement requires its own exact-commit independent review before the ECR
  R02 proposal is frozen.
- The protected untracked `artifacts/evidence/W1.A04.B00.json` witness is not
  read, edited, moved, deleted, hashed, or staged.

## Selected checks before candidate freeze

- Focused review-loader CRLF/Git-blob projection and semantic-tamper denial:
  **PASS**.
- Live ECR-0007 validation with the corrected repository-stable token digest:
  **PASS**.
- Full planning review-site regeneration and deterministic checker: **PASS**,
  491 HTML pages.
- Complete affected amendment-control and amendment-review suites, Ruff
  formatting/lint for the two changed Python files, backlog validation,
  generated-view freshness, UI-reference integrity, and Git diff hygiene are
  required before or immediately after candidate freeze.
- The already disclosed predecessor quality inventory and mypy diagnostics are
  outside this supplement and must remain visible for later W1-exit closure.

## Pre-freeze results

- Combined amendment-control and review-projection suites: **PASS**, 28 tests
  in 218.468 seconds, including both canonicalization regressions.
- Ruff formatting and lint over `tools/plan_review_site.py` and
  `tests/foundation/test_plan_review_amendments.py`: **PASS**.
- ECR-0007 structural/history validation with the Git-blob token digest:
  **PASS**. Full review-site regeneration and deterministic validation:
  **PASS**, 491 HTML pages.
- Backlog validation: **PASS**, 20 capabilities, 117 slices, 365 tasks, 12
  release gates. Generated backlog views: **PASS**, no changes. Approved
  UI-reference integrity: **PASS**, all 55 governed files unchanged.
- Git diff hygiene: **PASS**. Candidate staging is restricted to this evidence
  record, the shared review-site consumer, and its focused integration test;
  the pending ECR R02 files and generated projections are deliberately
  excluded.
