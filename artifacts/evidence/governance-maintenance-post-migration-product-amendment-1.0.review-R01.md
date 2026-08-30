# Independent control/security review R01: post-migration product amendment packets

- **Candidate commit:** `624c3745aa5559b11b7c6fe6727ec382ae11328f`
- **Predecessor commit:** `c532570f4dab81b65453724215f6a74e37fd8c89`
- **Disposition:** `CHANGES_REQUESTED`
- **Scope:** Commit-bound review of the v4 ECR packet schema, authority/history validator, activation boundaries, task/slice/refactor and governed-experience controls, witness-safe approval worktree handling, and exact independent-review authority. No product, backlog, task, Wave, approval, or witness state was changed. The protected untracked `artifacts/evidence/W1.A04.B00.json` witness was not read, staged, edited, or deleted.

## Findings

### P1 / blocking — PMPA-R01-F01 — Authority commits can be substituted while retaining the same files/status

`_authority_chain_v4_errors` verifies that referenced files exist at the supplied commits and that historical amendment state is `ADOPTED`, but it does not require the unique authoritative commits. Three mutations of the otherwise-valid repository-derived fixture each returned an empty error list:

1. replacing reserved `W1.A04.approvalReference.introductionCommit` with the later `GOV-MIG-0001` commit;
2. replacing `migrationAuthority.commit` and `reservedAmendments[0].supersededByMigration.commit` with candidate HEAD `624c3745aa5559b11b7c6fe6727ec382ae11328f`; and
3. replacing adopted `W1.A01.effectiveStateCommit` with candidate HEAD.

The first passes because reserved approval validation checks only that the unchanged approval bytes exist at the claimed commit (`tools/planctl.py:1340-1378`), not `_approval_introduction_commit`. The second passes because `_migration_reference_errors` accepts any ancestral commit containing the unchanged adopted migration file (`tools/planctl.py:744-765`), not the migration's exact adoption/introduction authority. The third passes because an arbitrary later backlog containing the amendment as `ADOPTED` satisfies the historical-state test (`tools/planctl.py:1316-1340`).

**Impact:** A packet can rewrite the meaning and chronology of reserved W1.A04, `GOV-MIG-0001`, and adopted predecessor authority while remaining “valid.” This contradicts the claimed exact frozen authority chain and permits unrelated later state to be laundered as an amendment's effective-state commit.

**Required closure:** Bind the reserved approval to its unique Git introduction commit; bind the migration to the exact adopted `GOV-MIG-0001` authority commit/review rather than any commit containing identical bytes; and bind every adopted amendment's effective-state commit to an immutable canonical source (for W1, the already-approved W1.A04 effective base or another exact append-only authority record). Add all three substitutions as denial tests.

### P1 / blocking — PMPA-R01-F02 — Human approval can assert a fictitious independent packet review

The shared approval schema defines `independentPacketReview` as an unconstrained object. `_approval_record_errors` checks only that its `result` is `APPROVED`, its `candidateCommit` equals the packet commit, and its free-form `reviewer` string differs from `approvedBy` (`tools/planctl.py:878`, `932-935`). It does not require an independent review ledger path, hash, Git introduction, reviewed-state commit, or finding closure.

A temporary v4 approval record with reviewer `invented-independent-reviewer`, result `APPROVED`, and the matching packet commit produced `invented_review_errors []` when all unrelated packet/Git boundaries were held valid. No review artifact existed.

**Impact:** Exact-commit human approval can expand product/security/experience authority without any independently authored packet review, directly defeating the mandatory control the candidate claims to preserve.

**Required closure:** Require and validate an immutable independent-review ledger with exact candidate commit, disposition, reviewer identity, findings/closures, content hash, and Git lineage. Separate the packet candidate from the reviewed-state/ledger commit where necessary; a self-declared object inside the human approval draft is not evidence of independent review. Add an approval-denial test for the current invented-review record.

### P1 / blocking — PMPA-R01-F03 — The 15% refactor limit can be laundered through an unbound denominator

The schema accepts a scalar `plannedWorkPoints` and a free-form `method` (`enabler-change-request.v4.schema.json:132-143`). The validator only recomputes `refactorPoints / plannedWorkPoints` from those packet-supplied values (`tools/planctl.py:1427-1433`). It neither derives nor itemizes the pre-assessment approved-work denominator and does not allocate points to the declared refactor tasks.

Changing the valid fixture to `plannedWorkPoints = 1000000000000`, `refactorPoints = 100`, and `refactorSharePercent = 0.0` returned no authority error, although the fixture's claimed W1 denominator is 194 points and the refactor allocation increased twentyfold.

**Impact:** Any amount of refactoring can be made to appear below 15% by inflating one self-asserted number. The packet therefore does not enforce the planning rule's exact itemized pre-assessment denominator or auditable refactor allocation.

**Required closure:** Freeze an itemized, source-bound pre-assessment planned-work denominator and itemized per-task refactor allocations in one common finite estimation unit; recompute and deduplicate the Wave/CAP roll-up from those items; reject non-finite values and disagreement with the authoritative approved plan. Add denominator inflation, allocation omission, duplicate allocation, and non-finite-number denial tests.

### P2 / blocking — PMPA-R01-F04 — The supposedly generic v4 lane is coupled to W1's current history and can reuse global ECR identities

The schema requires at least one adopted amendment and at least one reserved amendment (`enabler-change-request.v4.schema.json:36-45`). A post-migration first amendment, or any Wave with no approved-but-unmaterialized reservation, cannot use v4 even though the validator's sequencing algorithm otherwise supports zero-length arrays. In addition, the next ECR number is calculated only from the target Wave's frozen/reserved amendments (`tools/planctl.py:1384-1391`), while ECR identities are repository-global. A later Wave can therefore propose an already-used `ECR-0001`.

**Impact:** The new lane works only for the present W1.A01-W1.A04 shape and is not a stable generic post-migration amendment format. Future use either becomes impossible or risks global change-request identity collision.

**Required closure:** Permit empty adopted/reserved collections when repository authority truthfully has none, while still requiring exact complete inventories; calculate the next ECR identity from the repository-global immutable ECR namespace. Add a no-reservation/first-amendment fixture and a cross-Wave ECR-collision denial.

## Controls that passed review

- Existing v1-v3 schemas were not modified; the focused suite's historical ECR-0001 exact approval/history test passes.
- The v4 happy-path fixture validates, and existing tests deny a changed reserved-approval hash and an arithmetically over-limit declared percentage.
- Current W1 activation checks require Wave campaign `PAUSED` at `wave` scope, deny ordinary `IN_PROGRESS`/`REVIEW` tasks, deny any active recovery hold, and deny overlapping `ACTIVE`/`REVIEW` amendment campaigns (`tools/planctl.py:1435-1462`).
- Authorized tasks must be exact ordered amendment-local identities; slice contributions must use known capabilities, exact ordered slice identities, partition authorized tasks once, and keep refactor tasks within their contribution.
- Governed-experience files are safe-path/hash checked during packet validation and are additionally compared to exact packet-commit Git blobs during approval (`tools/planctl.py:957-965`). This prevents the permitted untracked historical witness from being used as a governed-experience authority file.
- Approval requires HEAD to equal the packet commit, denies tracked dirt, and delegates the only untracked exception to `taskctl.wave_resume_allowed_untracked`, which authenticates the fixed W1 witness path, SHA-256, document type, task identity, and evidence commit. Any other untracked path remains denied. The witness itself was not opened during this review.
- Packet proposal/schema/review file roles are unique, current hashes are checked, and approval rechecks each file against its packet-commit Git blob.

## Checks performed

- Exact lineage: candidate `624c3745aa5559b11b7c6fe6727ec382ae11328f`; sole predecessor `c532570f4dab81b65453724215f6a74e37fd8c89`; four-path bounded delta.
- `git diff --check c532570f4dab81b65453724215f6a74e37fd8c89 624c3745aa5559b11b7c6fe6727ec382ae11328f` — pass.
- `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_planctl_amendments` — pass, 5 tests in 18.888 seconds.
- `.venv\Scripts\python.exe tools/quality_check.py --repo .` — pass: 168 governed Python files.
- Repository-derived v4 fixture — schema and authority validation pass.
- Authority adversarial replay — reserved-introduction substitution, migration-commit substitution, adopted-effective-state substitution, and inflated-denominator laundering each returned `[]` (findings F01/F03).
- Approval adversarial replay in an isolated temporary fixture — an invented independent-review object returned `[]` from `_approval_record_errors` (finding F02).
- Static boundary review covered schema strictness, safe-path/symlink handling, packet and governed-experience Git-blob binding, exact task/slice partition, pause/quiescence/hold/overlap checks, exclusive approval creation, and witness-safe clean-tree handling.

## Conclusion

Candidate `624c3745aa5559b11b7c6fe6727ec382ae11328f` preserves legacy validation and implements several sound boundaries, but it is not safe to integrate. It can substitute authority chronology, approve expanded authority without a real independent review, and launder the 15% refactor limit; its identity model is also not generic across post-migration Waves. Remediate these four findings in one bounded successor and replay them append-only. No ECR packet approval or W1 resume is authorized by this review.
