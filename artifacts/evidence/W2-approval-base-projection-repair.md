# W2 historical approval-base projection repair

Status: bounded control maintenance, pending independent exact-commit review. This record does not approve ECR-0009, Academic Minimal 1.8, an ordinary task, or W2 release.

## Predecessor and exact delta

The quiescent predecessor is commit `b7b7928ae75bed890e28fd36c78491f981fdcf45`, with physical `planning/backlog.yaml` SHA-256 `2c4cc75dc1c7a1532df2742bcdaec1f937a778537754a058c1be74bc95f2475b`. W2 was `PAUSED`, `CAP-05.S01.T01` was `BLOCKED` with no lease, and no W2 ordinary task was `IN_PROGRESS` or `REVIEW`; no amendment campaign was active. `wave_approval_bases` contained only W1.

The repair appends one W2 object after the unchanged W1 base. Its packet commit is `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`; its historical approval-record commit is `3bc1c1828efab50efc730bf3907c3036eff58a2f`. Both are ancestral to the predecessor. The current W2 approval equals the approval in that historical record and hashes canonically to `3f15c0da1fdaaf41b5ce69cc3cc3cda337ff549178101e0a358e0fb40503c97a`. The repair copies that exact object into the missing projection. The physical successor backlog SHA-256 is `cdf8466285dfaf30bd6fc2cdf21a48c2fb841ce4f72b95875a821586121340cc` before any further taskctl transition.

The edit preserved the file's CRLF working-copy form. Removing the new W2 object from the parsed successor exactly reproduces the parsed predecessor; byte removal of the inserted block reproduces the physical predecessor. W1's base, effective W2 approval, task/lease state, amendment chain, frozen packet, release criteria and control revision are unchanged. This adds no new approval or execution authority; it makes the existing historical approval addressable by the v4.1 ECR validator.

## Risk-selected proof and limits

Risk is high for evidence/control authority and low for product runtime. `taskctl validate` passed: 20 capabilities, 117 slices, 385 tasks and 12 release gates. Regenerated backlog views pass `--check`; `plan_review_check` passes the 492-page static review site. The in-memory authority validator accepted the valid projection and rejected wrong W2 canonical hash, a forged W2 approval note, a nonexistent record commit, and a changed W1 packet commit. The first diagnostic assertion used an incomplete expected error string; the validator did reject the forged record commit, and the failed harness log is retained at `artifacts/tmp/W2-approval-base-projection-adversarial.log` (SHA-256 `530ee65a546b79e17638f9adc1e38e1417086c223dc8ebcdfbe1d542c313d876`). The corrected full run passed; ignored log `artifacts/tmp/W2-approval-base-projection-adversarial-corrected.log` SHA-256 `0c30094bddc77b20fd37210d97ccec4a1d3b87099d59a25c609b22a72e6d17de`.

No product, schema, validator, migration or verification code changed. Full product profiles are deferred to the normal W2 qualification. `planctl ecr validate ECR-0009` remains a separate consumer check once the inert proposal packet returns from the ignored hold and is committed. Independent control-authority review of the exact repair commit is required before local-main integration.
