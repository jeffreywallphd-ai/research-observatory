# Independent remediation review R02: exact-candidate evidence qualification

- Remediation candidate: `e8c27fcf12a8fdc2889c3385922a7f974e658333`
- Predecessor/adverse-ledger commit: `1942ab0ca231aaafd2c47aef92d11a1314b72af9`
- Original implementation candidate: `fe9e5345595e12fe63887b343034bcec5796ab80`
- Remediation evidence: `artifacts/evidence/governance-maintenance-ecr-bound-file-canonicalization-1.1.remediation-R02.md`
- Remediation evidence SHA-256: `1ccde498396e2e7a2d82ec8023e4c9cf79e4ec5df7e68dd7725ff0fdde8501c0`
- Remediation evidence Git blob: `b0c8d3f6cc110c4b03a014a97e6c187a981e55b5`
- Disposition: **APPROVED**
- Approval available: **yes**, for the bounded governance-maintenance supplement only

## Identity and scope authentication

`e8c27fcf12a8fdc2889c3385922a7f974e658333` has `1942ab0ca231aaafd2c47aef92d11a1314b72af9` as its sole parent and adds exactly one path, the 83-line remediation evidence record named above. The history is a strict descendant of the original implementation candidate and its adverse R01 review.

The following historical inputs are byte-identical between the adverse-ledger predecessor and this remediation candidate:

- original 1.1 maintenance record, Git blob `f6fdb2b8a2bbdaafd038d5aa2cf0c8628ef80fa5`;
- adverse R01 ledger, Git blob `3baa0d72fb809b4070c15d94c0b29d9b67267c31`;
- `tools/plan_review_site.py`, Git blob `ede2bde3d1c69cefb7672f8b03cb61ab47eb2d31`; and
- `tests/foundation/test_plan_review_amendments.py`, Git blob `8f3d84a87f12e4e376e0060edbef68214cb96f35`.

The remediation record's declared adverse-ledger SHA-256, `c1a112c72670c58662339f731784f226f23a7b4e2a930db6b47dc63cda806694`, matches the immutable R01 bytes. No pending ECR-0007 R02 source or generated projection is part of the candidate or this disposition.

## Prior finding closure

### `GOV-MAINT-ECR-CANON-1.1-R01-F01` — **CLOSED**

The strict-descendant record now makes the evidence boundary explicit:

- focused loader/helper, declared-source, import/cycle, Ruff, and affected-mypy results are classified as exact `fe9e5345595e12fe63887b343034bcec5796ab80` evidence;
- the exact supplement commit's repository-wide site outcome is correctly classified as an expected denial of the old ECR-0007 `tokens.css` digest;
- the 28-test, ECR validation, and 491-page site PASS results are explicitly classified as a provisional paired integration preview that used pending, unstaged R02 bytes; and
- no broad PASS may be claimed as commit-bound until the separate ECR R02 projection is frozen, independently reviewed, and replayed at that immutable commit.

This directly satisfies the R01 closure condition without rewriting the original maintenance record or adverse ledger, retroactively incorporating pending files, or weakening the deny-by-default behavior.

## Findings

No new blocking or non-blocking findings.

## Independent checks

- Resolved candidate, parent, and original-candidate identities; verified strict-descendant ancestry and sole-parent structure.
- Confirmed the exact one-file committed delta and unchanged original implementation, test, maintenance-record, and R01-ledger blobs.
- Recomputed the remediation-record and adverse-ledger SHA-256 values from immutable Git bytes.
- Replayed the focused review-loader clean-filter projection and semantic-tamper denial directly without live-repository class setup: pass.
- Replayed the separate declared-source byte-tamper denial directly: pass.
- Replayed the shared-helper regression covering clean pending/exact-commit identity, dirty semantic and exact-commit divergence denial, pending-untracked bytes, and invalid-commit fail-closed behavior: pass.
- Replayed shared import identity/cycle smoke, Ruff format/lint, and affected mypy over the unchanged implementation/test paths: pass.
- Materialized the exact remediation candidate with complete Git history and invoked the review-site ECR loader: it produced the required denial, `ECR-0007 governed experience: repository file hash mismatch: design/ui-reference/assets/tokens.css`.
- Confirmed the exact candidate backlog retains W1 `PAUSED` and `CAP-07.S01.T02` `BLOCKED` with no lease.
- Confirmed the original `4eaa413b23d72c52d2229574d9fbb76ef6ea7338..fe9e5345595e12fe63887b343034bcec5796ab80` implementation delta still passes `git diff --check`. The remediation Markdown itself has one extra blank line at EOF; that does not alter its evidence semantics or contradict the explicitly original-candidate diff-hygiene classification and is not acceptance-bound.

The full review site is not required to pass at the supplement-only commit because accepting the old digest would violate the remediation's governing invariant. The separately pending ECR-0007 R02 bytes were neither authenticated nor relied on in this review.

## Conclusion

`e8c27fcf12a8fdc2889c3385922a7f974e658333` closes `GOV-MAINT-ECR-CANON-1.1-R01-F01`. Its append-only record accurately separates exact-candidate proof from provisional paired integration evidence, preserves the original implementation and adverse history, and grants no product, ECR execution, Wave, task, release, or gate authority. The bounded governance-maintenance supplement is approved; ECR-0007 R02 remains a separate future commit-bound review.
