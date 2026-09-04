# Independent control review R01: review-site canonical governed-file binding

- Candidate commit: `fe9e5345595e12fe63887b343034bcec5796ab80`
- Predecessor commit: `4eaa413b23d72c52d2229574d9fbb76ef6ea7338`
- Authority and evidence: `artifacts/evidence/governance-maintenance-ecr-bound-file-canonicalization-1.1.md`
- Related open finding: `ECR-0007-R01-F01`
- Disposition: **CHANGES_REQUESTED**
- Approval available: **no**, until the blocking evidence-truth finding below is closed by an independently reviewed strict descendant

## Scope authentication

The candidate has the stated predecessor as its sole parent and changes exactly three committed paths:

- `artifacts/evidence/governance-maintenance-ecr-bound-file-canonicalization-1.1.md`
- `tests/foundation/test_plan_review_amendments.py`
- `tools/plan_review_site.py`

The delta is 165 insertions and 5 deletions. It does not contain the pending ECR-0007 R02 proposal or generated-page edits and does not change the backlog, product code, governed UI-reference bytes, Wave/task state, approval, release, or gate authority. Those pending working-tree files were excluded from candidate authentication and were not treated as review evidence for this commit.

## Control assessment

The review-site loader now calls the same `planctl._bound_repository_file_errors` implementation already approved in the 1.0 maintenance increment. `plan_review_site` imports that helper, while `planctl` does not import `plan_review_site`; it invokes the site script only from a function through a subprocess. Import identity and CLI startup were replayed successfully, so the reuse introduces neither a Python import cycle nor recursive execution.

Before projecting any governed-experience entry, the loader requires the shared helper to accept the complete inventory. The shared boundary retains:

- rejection of missing/non-list inventories, duplicate or invalid entries, absolute/traversing/drive-qualified paths, symlink or junction traversal, repository escape, missing/unreadable files, and hash mismatch;
- Git-blob hashing for clean tracked files under repository clean filters;
- worktree-byte hashing for dirty tracked and pending-untracked files;
- exact packet-commit blob existence and worktree/blob equality when that mode is used by `planctl`; and
- fail-closed behavior for Git comparison errors.

The loader raises on the first shared validation error before completing a page build. After successful authentication it projects the packet's declared digest rather than re-hashing checkout bytes, so generated manifests retain the approved canonical identity. A dirty semantic substitution is rejected before output generation. Existing declared ECR source files continue to use their separate exact-worktree-byte validation and are not switched to Git clean-filter semantics.

## Findings

### `GOV-MAINT-ECR-CANON-1.1-R01-F01` — HIGH — blocking

The committed 1.1 maintenance record presents the combined 28-test amendment suite and full review-site regeneration as PASS results under “Pre-freeze results,” but those broad passes required the separately pending, unstaged ECR-0007 R02 digest correction. They therefore are not exact-candidate evidence for `fe9e5345595e12fe63887b343034bcec5796ab80`. Replaying the site setup from the candidate's committed bytes correctly fails with `ECR-0007 governed experience: repository file hash mismatch: design/ui-reference/assets/tokens.css`; the implementation's focused canonicalization fixtures pass independently. The record does disclose pending R02 edits elsewhere and labels the live corrected-digest check, but it does not qualify the 28-test/full-site PASS language as a paired provisional integration replay. That ambiguity is material at this evidence-control boundary because an exact-commit reviewer could incorrectly authenticate a green repository projection that the frozen candidate cannot produce by itself.

Reproduction:

1. Materialize the exact candidate tree while retaining or supplying the repository history required by existing amendment fixtures.
2. Exclude the pending ECR-0007 R02 source/generated edits.
3. Run the new focused helper/loader canonicalization tests; they pass.
4. Run review-site setup or regeneration against the exact candidate packet; it fails on the still-open ECR-0007 governed-file digest.
5. Reapply the pending R02 canonical digest correction and rerun; the broader integration projection can pass, demonstrating that the reported broad result is paired-worktree rather than exact-candidate evidence.

Required closure: add an immutable strict-descendant evidence correction that distinguishes (a) exact-candidate focused checks and their results from (b) the provisional paired integration replay performed with not-yet-frozen ECR-0007 R02 bytes. It must state that the candidate-alone review site remains expected to deny the old digest, must not rewrite the 1.1 record or incorporate the R02 files into this candidate retroactively, and must bind any later broad PASS to the exact frozen paired commit where it is reproducible. Obtain independent remediation review of that descendant. No product-code change is required by this finding.

## Independent checks

- Commit/ancestry authentication: candidate and predecessor resolved exactly; the predecessor is the candidate's sole parent.
- Scope and hygiene: `git diff --name-status`, `--stat`, and `--check` confirmed the exact three-file delta and no whitespace errors.
- Worktree exclusion: the reviewed implementation and test paths are byte-identical to the candidate commit; pending ECR-0007 R02 source/generated edits were not included.
- Shared-boundary identity and circularity: importing `planctl` and `plan_review_site` proved the loader references the exact shared helper object; `plan_review_site.py --help` completed successfully.
- Review-loader regression, invoked without live-repository class setup: clean CRLF worktree materialization over an LF Git blob was accepted and projected the Git digest; a dirty semantic change was denied with `repository file hash mismatch`.
- Declared-source regression, invoked without live-repository class setup: changing exact ECR source bytes remained denied with `declared source hash mismatch`.
- Shared-helper regression: the focused 1.0 test passed, including clean pending and exact-commit acceptance, dirty semantic and exact-commit divergence denial, pending-untracked local-byte acceptance, and invalid-commit fail-closed behavior.
- Additional helper denials: missing inventory, traversal, missing file, and duplicate path returned errors rather than permissive fallback.
- Ruff format and lint over `tools/plan_review_site.py` and `tests/foundation/test_plan_review_amendments.py`: pass.
- Affected mypy check over the same two files with skipped imports: pass, no issues.

## Check-boundary qualification

An isolated archive of the exact candidate was used to prevent pending R02 bytes from affecting the review. The new shared-helper test passed there. The archive's broader historical amendment tests were not usable as full-suite evidence because a one-commit snapshot intentionally lacks the older Git objects those fixtures query. Separately, the review-site class setup correctly rejected the exact candidate's still-unremediated ECR-0007 governed-file digest. That is the open `ECR-0007-R01-F01` state this supplement enables a later R02 packet to correct; it is not a permissive fallback or a defect in the new loader.

Accordingly, the maintenance record's reported 28-test and full-site passes are understood as integration-preview checks performed with the explicitly disclosed pending R02 digest correction present. They are truthful as pre-freeze combined-worktree results, but they are not represented here as exact-candidate-only passes. This review relies on the exact-candidate scope/implementation authentication and isolated deterministic boundary replays above. The repository-wide site can become green only after the separately reviewed ECR-0007 R02 source projection supplies the canonical digest.

## Conclusion

The code change in `fe9e5345595e12fe63887b343034bcec5796ab80` is otherwise technically clear: it removes the review generator's checkout-specific duplicate hashing logic, reuses the already reviewed fail-closed validator, projects only an authenticated declared digest, preserves separate exact source checks, and introduces adequate deterministic coverage for the newly exposed consumer. The candidate is nevertheless **CHANGES_REQUESTED** because its committed evidence does not unambiguously separate exact-candidate checks from the paired provisional R02 integration replay. This disposition does not review, close, or approve ECR-0007 R02, authorize product work, or make the pending proposal edits part of this candidate.
