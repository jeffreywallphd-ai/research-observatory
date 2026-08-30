# Independent control/security review R02: post-migration product amendment packets

- **Candidate commit:** `24a25766c2672a26442571fa2f98415c6849bdbc`
- **Predecessor commit:** `a0bce3fea0795c7c2351227790af3a60b64eee6c`
- **Original R01 candidate:** `624c3745aa5559b11b7c6fe6727ec382ae11328f`
- **Disposition:** `APPROVED`
- **Scope:** Commit-bound remediation review of PMPA-R01-F01 through PMPA-R01-F04 and the candidate's incremental control surface. The review covered exact authority chronology, independent packet-review evidence, refactor accounting and the owner-directed exception, generic identity/history behavior, activation boundaries, legacy schema compatibility, and witness-safe approval handling. No product, backlog, task, Wave, approval, or witness state was changed. The protected untracked `artifacts/evidence/W1.A04.B00.json` witness was not read, staged, edited, or deleted.

## R01 closure replay

### PMPA-R01-F01 — CLOSED

The remediation now rejects each prior authority-substitution class:

- reserved approval authority must equal the file's single Git introduction commit and the current bytes must equal that introduction blob (`tools/planctl.py:888-897`, `1527-1531`);
- `migrationAuthority.commit` must equal the last commit of the adopted migration file, contain the exact current blob, and contain the exact hash-bound `APPROVED` migration review in the same commit (`tools/planctl.py:745-785`); and
- an adopted amendment's `effectiveStateCommit` must be the transition whose backlog has `ADOPTED` while its immediate parent did not (`tools/planctl.py:912-941`, `1482-1489`).

The focused fixture denies substituted reserved-introduction, migration, and effective-state commits. The existing commit-existence, ancestry, and ordered-chain checks remain in force. No chronology-bypass regression was found.

### PMPA-R01-F02 — CLOSED

V4 approval no longer accepts an invented review projection. It requires a review ledger at the exact amendment-local RNN path, exact SHA-256, unique Git introduction commit, immutable Git blob, and exact reviewer/candidate/packet/attempt/disposition/finding-closure identity. The ledger commit must descend from the packet candidate, the candidate-to-reviewed-state diff must contain only that ledger, approval HEAD must equal the reviewed-state commit, and the eventual approval introduction must descend from it (`tools/planctl.py:789-858`, `1092-1093`, `1124-1138`, `1771-1800`).

The approval schema retains the legacy v1-v3 review shape but the v4-specific validator rejects that shape when it lacks the ledger binding. The focused denial test for an invented review without a ledger passes. The append-only review control is preserved: findings must be empty for an approved ledger, closures must be unique and closed, and the approval's closure projection must exactly match the ledger.

### PMPA-R01-F03 — CLOSED

The denominator is now derived from the exact approved Wave-base commit's `planning/backlog.yaml`, with every Wave task itemized using the fixed `S=1`, `M=3`, `L=5` scale. The packet must reproduce the source commit/path, item order, estimates, points, and total exactly. Refactor allocations are separately derived from the amendment's exact refactor-task partition and required task estimates; finite points and the one-decimal share are recomputed (`tools/planctl.py:1570-1632`).

The focused suite denies inflated totals, omitted allocation, non-finite values, inconsistent points/share, and overbroad exception scope. The explicit `owner-directed-wave-exception` is packet-scoped to the exact refactor task IDs and requires non-empty authorization and rationale; it does not suppress the baseline, estimates, allocations, points, or calculated share. Human approval therefore remains an exact-packet authority decision rather than a hidden arithmetic bypass.

### PMPA-R01-F04 — CLOSED

The v4 schema now permits truthful empty adopted and reserved histories. The validator still requires both collections to equal repository authority exactly, preserves consecutive amendment numbering across adopted plus reserved IDs, and derives the next ECR identity from repository-global packet and approval records rather than the target Wave alone (`tools/planctl.py:944-960`, `1414-1536`). The empty-history schema fixture and cross-namespace collision denial pass.

Existing v1-v3 packet schemas and their validator dispatch remain unchanged. All exact immutable Wave-amendment approval records `W1.A01` through `W1.A04` validate against the revised shared approval schema. The current-state `ECR-0001` and `ECR-0002` approval/history smoke checks pass. `ECR-0003` continues to report its post-migration released-hold/current-state incompatibility in the unchanged v2/v3 validator; this is not introduced by the candidate delta and no historical bytes or legacy controller branches were changed.

## Incremental boundary assessment

- W1 must remain campaign `PAUSED` at Wave scope; any ordinary `IN_PROGRESS` or `REVIEW` task, active recovery hold, or overlapping active/review amendment denies v4 activation (`tools/planctl.py:1634-1661`).
- Slice/task authority still forms an exact ordered partition, task identities remain amendment-local, refactor classifications cannot escape their contribution, and every task depends on the amendment bootstrap.
- Governed-experience files remain safe-path/hash bound during packet validation and exact packet-commit blob bound during approval.
- Approval still rejects tracked dirt and permits untracked content only through `taskctl.wave_resume_allowed_untracked`; no candidate change broadened this boundary. This review inspected that control path without opening the retained W1 witness.
- The remediation adds generic helper checks and one schema branch; it does not add a task state, approval class, controller identity, recovery hold, or incident-specific workflow.

## Findings

No blocking or non-blocking findings in the reviewed remediation scope.

## Checks performed

- Exact lineage: `24a25766c2672a26442571fa2f98415c6849bdbc` has sole predecessor `a0bce3fea0795c7c2351227790af3a60b64eee6c`; both `a0bce3f` and original candidate `624c374` are strict ancestors.
- `git diff --check a0bce3fea0795c7c2351227790af3a60b64eee6c..24a25766c2672a26442571fa2f98415c6849bdbc` — pass.
- `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_planctl_amendments` — pass, 8 tests in 105.601 seconds.
- `.venv\Scripts\python.exe tools/quality_check.py --repo .` — pass: 168 governed Python files.
- Revised shared approval-schema replay against exact immutable records `W1.A01.json` through `W1.A04.json` — pass.
- Legacy current-state smoke: `ECR-0001` and `ECR-0002` approved/history-bound — pass; `ECR-0003` retains its pre-existing post-migration hold-state diagnostic in unchanged legacy code, as noted above.
- Static and adversarial review covered the four R01 substitutions/forgeries, candidate-to-review diff confinement, approval lineage, migration review binding, finite itemized budget reconstruction, owner-exception scope, global ECR collision, empty histories, pause/quiescence/hold/overlap denial, governed-experience binding, and witness-safe clean-tree handling.

## Conclusion

Candidate `24a25766c2672a26442571fa2f98415c6849bdbc` closes PMPA-R01-F01 through PMPA-R01-F04 without weakening the existing activation, experience, legacy-history, or witness boundaries. The remediation is approved for integration within the bounded governance-maintenance increment. This review does not itself approve an ECR packet, materialize an amendment, resume W1, or authorize product work.
