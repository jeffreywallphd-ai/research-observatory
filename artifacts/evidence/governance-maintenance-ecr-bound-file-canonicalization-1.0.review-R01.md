# Independent control review R01: Git-canonical ECR bound-file hashing

- Candidate commit: `7ac7f5d999da871716b30640ec1c8f2115398c6c`
- Predecessor commit: `5423e4c918ad6aa71653e04a36545674e78c7423`
- Authority: `artifacts/evidence/governance-maintenance-ecr-bound-file-canonicalization-1.0.md`
- Originating finding: `ECR-0007-R01-F01`
- Disposition: **APPROVED**
- Approval available: **yes**, for this bounded governance-maintenance increment only

## Scope authentication

The candidate has the stated predecessor as its sole parent and changes exactly three paths:

- `artifacts/evidence/governance-maintenance-ecr-bound-file-canonicalization-1.0.md`
- `tests/foundation/test_planctl_amendments.py`
- `tools/planctl.py`

The delta is 181 insertions and 2 deletions. It does not change ECR-0007, the backlog, product code, governed UI-reference bytes, Wave state, or release authority. The maintenance record, implementation, and regression test are mutually consistent with the Tier-2 boundary authorized by GOV-MIG-0001.

## Control assessment

The implementation preserves the existing safe repository-path, duplicate-path, missing-file, unreadable-file, hash-format, and hash-mismatch denials. For each safe bound path it now:

1. obtains the Git blob at the packet commit (or `HEAD` for a pending packet);
2. uses `git diff --quiet --no-ext-diff <comparison-commit> -- <path>` to distinguish a clean tracked worktree path from a pending material change;
3. hashes Git-normalized blob bytes only when the path is clean and present in the comparison commit;
4. hashes local bytes for dirty tracked and pending-untracked files; and
5. in exact-commit validation, separately requires the path to exist in the packet commit and the local/canonical payload to equal the committed blob.

This closes the CRLF/clean-filter false mismatch without allowing local checkout representation to replace the immutable Git identity. Dirty tracked content remains bound to its local pending bytes, pending-untracked content remains reviewable by local-byte hash, and exact-commit validation denies both unavailable blobs and semantic divergence. A Git comparison return code greater than one produces an explicit validation error rather than falling back to a permissive local-byte path. `--no-ext-diff` also prevents repository-configured external diff execution from determining the clean/dirty decision.

## Findings

No blocking or non-blocking findings.

## Independent checks

- Commit identity and ancestry: candidate and predecessor resolved exactly; sole-parent relationship confirmed.
- Scope: `git diff --name-status`, `--stat`, and `--check` confirmed the exact three-path delta and no whitespace errors.
- Focused clean-filter regression: `PlanctlAmendmentTests.test_bound_repository_files_use_git_normalized_bytes_for_clean_worktrees` passed (1 test). The fixture covers CRLF materialization of an LF Git blob, clean pending and exact-commit acceptance, pending-untracked local-byte acceptance, semantic-edit denial, exact-commit divergence denial, and fail-closed invalid-commit behavior.
- Full affected controller suites: `tests.foundation.test_planctl_amendments` and `tests.foundation.test_plan_review_amendments` passed (27 tests in 216.367 seconds), including existing traversal, duplicate, missing, hash-tamper, commit-binding, budget, authority, approval, lifecycle, and projection cases.
- Direct helper replay: the prior worktree-byte digest was denied in both pending and exact-commit modes; the corrected Git-blob digest was accepted in both modes for the clean governed file.
- Formatting/lint: Ruff format check and Ruff check passed for `tools/planctl.py` and `tests/foundation/test_planctl_amendments.py`.
- Generated backlog views: deterministic check passed with no changes.
- Approved UI reference: integrity/reproducibility check passed for `RO-UI-ACADEMIC-MINIMAL-1.5` (55 governed files, 14 workflow profiles).

## Baseline quality debt

- The affected mypy command still reports the disclosed `sorted` key callback type error at candidate line `tools/planctl.py:1470`. Blame and predecessor comparison locate that expression outside this candidate delta; the candidate merely shifts its line number.
- The repository quality check still reports the disclosed unlisted tracked file `tests/e2e/test_workflow_profile_matrix.py`. That file and the quality-scope configuration are unchanged by this candidate.

Neither failure was introduced, masked, or weakened by this maintenance increment. They remain truthful predecessor debt and are not grounds to broaden this bounded control repair.

## Conclusion

`7ac7f5d999da871716b30640ec1c8f2115398c6c` is approved for integration as the smallest generic correction to ECR bound-file canonicalization. It preserves fail-closed Git and repository-scope controls and has deterministic regression coverage across clean-filter, pending-untracked, exact-commit, substitution, and Git-error paths. This disposition approves only the maintenance increment; it does not close or approve ECR-0007, mutate the immutable R01 history, or authorize product work.
