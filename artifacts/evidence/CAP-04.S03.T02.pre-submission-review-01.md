# CAP-04.S03.T02 — independent adverse pre-submission review 01

Reviewer: `agent:/root/w2_t02_disposition`, independent of the task owner.
Reviewed candidate: `3998d9c68800d06b4e9400a99e785f3dd2005a01`.
Claim base: `691205f48cf8ee80b323a9971413f7da1d0608e1`.
Approved W2 packet: `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`.
Experience authority: `RO-UI-ACADEMIC-MINIMAL-1.7`.

**Disposition: adverse; both findings below remain OPEN and blocking.** This is
an exact-candidate pre-submission source review, not a formal task disposition,
task approval, integration approval or a review of subsequent remediation.

The review followed the repository's independent-review and verification-breadth
guidance, the [approved S03 task contract](../../planning/slice-plans/CAP-04/CAP-04.S03-canonical-work-version-and-identity-reconciliation.md#92-cap-04s03t02---implement-probabilistic-duplicate-candidate-generation-and-review)
and [task-start acceptance map](CAP-04.S03.T02.task-start.md). It examined changed
candidate, source-owner inventory, Work membership/alias, provenance/dependency,
durable worker, migration, API, generated client, native admission and review UI
boundaries. Progress notes 01–05 were navigation, not independent proof.
Owner-known qualification/control defects were excluded from this additional
finding ledger. No broad test profile was run and no other concrete additional
blocker was identified in this bounded review.

## Original probe evidence and portability

The original ignored probe ledger remains unchanged at
`artifacts/tmp/CAP-04.S03.T02-pre-submission-independent-findings-01.md`.
Its SHA256 is
`ba80e637bac75fe7a2c3493af1d3b5366bbdb410c4cf45d058136cd080f2c684`.
It contains the original commands, execution observations and adverse results.
The digest binds those bytes; it is not itself proof that a command executed.

The reproduction descriptions below intentionally use repository-relative
executable paths. This is a portability normalization: the original executed
commands, including their local executable spelling, remain in the bound ignored
ledger. No original command or output is rewritten by this review artifact.
All output blocks below reproduce the observed output verbatim.

The first probe used the candidate before owner remediation. After owner edits
began, the second finding's probes ran from the isolated frozen source export
created by these commands from the repository root:

```powershell
git archive --format=tar --output=artifacts/tmp/CAP-04.S03.T02-review-frozen-3998d9c.tar 3998d9c68800d06b4e9400a99e785f3dd2005a01 services/core-api/src tests packages tools
New-Item -ItemType Directory -Path artifacts/tmp/CAP-04.S03.T02-review-frozen-3998d9c -Force | Out-Null
tar -xf artifacts/tmp/CAP-04.S03.T02-review-frozen-3998d9c.tar -C artifacts/tmp/CAP-04.S03.T02-review-frozen-3998d9c
```

For portable replay of the second finding's Python bodies in the bound ledger,
resolve the interpreter from the repository root and then select that export:

```powershell
$reviewPython = (Resolve-Path -LiteralPath .venv/Scripts/python.exe).Path
Push-Location -LiteralPath artifacts/tmp/CAP-04.S03.T02-review-frozen-3998d9c
# Pipe the selected original Python body to: & $reviewPython -
# Return after the probe with: Pop-Location
```

These probes create disposable canonical SQLite fixtures and clean them through
the existing test fixture cleanup. The review did not edit product files, commit
changes, change HEAD or collect final qualifying task evidence.

## F-EXACT-IMPACT-01 — exact-origin dependency runs never advance

**Severity: P2. Blocking: yes. Status: OPEN.**

**Criterion and contract.** CAP-04.S03.T02 C2/C3; approved S03 §9.2 persistence,
provenance and restart obligations; S03 §8 requires downstream updates to use
the dependency graph and be resumable. The task-start map's Atomic dependencies
and Durable operation rows require restartable propagation without a post-commit
gap and honest pending/stale state.

**Frozen-candidate location and defect.**
`services/core-api/src/research_observatory_core/reconciliation_repository.py:758`
starts `SOURCE_VERSION` dependency runs when an exact addition advances a Work.
The composed worker at `reconciliation_worker.py:590` calls
`advance_review_impacts()`. Its selection at
`reconciliation_repository.py:1503` is restricted to run IDs in
`reconciliation_review_decisions.outcome_json`. Exact-created runs have no such
human decision and are never selected. Existing impact items correctly deny
fresh use, but affected exact-origin propagation remains pending indefinitely.

**Portable reproduction.** From the frozen candidate, run the first Python body
in the bound ledger through `.venv/Scripts/python.exe -` from the repository
root, with `services/core-api/src` on `sys.path`. Instantiate
`tests.reconciliation.test_repository.ReconciliationRepositoryTests`; reconcile
source A; append an evidence consumer from A's Work; exact-link another source
with the same DOI; invoke `advance_review_impacts()`; inspect the saved run and
consumer impact. The first exploratory invocation omitted the source import path
and failed before fixture setup; that setup failure is retained in the ledger.

**Exact observed output.** Successful probe exited 0 in 3.3268574 seconds:

```text
{"event": "intent.draft.saved", "level": "INFO", "reasonCode": "intent-draft-saved", "timestamp": "2026-09-27T09:52:24.717Z", "traceId": "11111111111111111111111111111111"}
exact-linked: exact-linked ; worker advancement: False
run: [('SOURCE_VERSION', 1, 'started')]
consumer impact: [('stale',)]
```

**Required remediation and closure proof.** Authenticate exact-origin runs
against immutable owner publication/command and Work predecessor/replacement
authority, and advance them through the existing bounded worker. Add a regression
with an old Work consumer, an exact addition and worker restart. Require eventual
completed propagation while preserving stale/fresh-only denial, old source and
decision receipts, and the original adverse result. Append independent closure
evidence; this document claims no closure.

## F-IMPACT-GRAPH-02 — later graph growth strands pending review intent

**Severity: P2. Blocking: yes. Status: OPEN.**

**Criterion and contract.** CAP-04.S03.T02 C2/C3; approved S03 §9.2 persistence,
restart and recoverable-failure obligations; S03 §8 resumable downstream updates;
the task-start Atomic dependencies and Durable operation rows.

**Frozen-candidate location and defect.** The new advancement call at
`services/core-api/src/research_observatory_core/reconciliation_repository.py:1542`
delegates to the existing impact guard. At `repositories.py:4263`–`4270`, that
guard recomputes the current graph and requires its hash to equal the saved
run snapshot. `dependency_impacts.py:349`–`356` hashes every project graph edge,
including unrelated outputs. An independent later output makes a correctly
selected `HUMAN_DECISION` run unadvanceable. The new worker has no authenticated
recovery/repreview path and keeps selecting the same pending run. Repeated failure
also prevents later eligible runs from being serviced.

This differs from F-EXACT-IMPACT-01: the run is selected, but its checkpoint
cannot advance. Fresh-only denial remains intact; resumable completion fails.

**Portable reproduction A.** In the frozen export above, execute the review
probe's Python body from the bound ledger through the resolved
`.venv/Scripts/python.exe`. Instantiate
`tests.reconciliation.test_review_repository.ReviewRepositoryTests`; append
evidence derived from Work A; human-merge A/B; append unrelated evidence with
no source inputs before propagation; call `advance_review_impacts()` twice;
inspect durable run state.

**Exact observed output A.** Probe exited 0 in 4.3343519 seconds:

```text
{"event": "intent.draft.saved", "level": "INFO", "reasonCode": "intent-draft-saved", "timestamp": "2026-09-27T09:55:26.015Z", "traceId": "11111111111111111111111111111111"}
worker attempt 1 RepositoryConflict dependency propagation graph or authority changed; a fresh preview is required
worker attempt 2 RepositoryConflict dependency propagation graph or authority changed; a fresh preview is required
runs: [('HUMAN_DECISION', 1, 'started'), ('HUMAN_DECISION', 0, 'completed')]
```

**Portable reproduction B.** In the same frozen export, execute the batch probe's
Python body from the bound ledger through the resolved `.venv/Scripts/python.exe`.
Instantiate `tests.reconciliation.test_batch_publication.BatchPublicationTests`;
reconcile the first source and derive an evidence consumer from its Work; publish
the batch containing the second exact source; select its nonempty impact run and
invoke `_SqliteDependencyImpactRepository.advance()` with the current checkpoint.
The batch creates its impact run before candidate-set publication adds further
graph edges, so no concurrent or external later write is needed.

**Exact observed output B.** Probe exited 0 in 3.432057 seconds:

```text
{"event": "intent.draft.saved", "level": "INFO", "reasonCode": "intent-draft-saved", "timestamp": "2026-09-27T09:55:48.387Z", "traceId": "11111111111111111111111111111111"}
exact batch impact advancement: RepositoryConflict dependency propagation graph or authority changed; a fresh preview is required
batch outcome: succeeded
```

**Required remediation and closure proof.** Retain and authenticate original
saved intent, graph authority, impact items and processed checkpoints. Provide a
lawful continuation/recovery path under later append-only graph growth while
detecting mutation or invalidated authority. Do not weaken frozen-snapshot
validation or silently mark the pending run completed. Add regressions for human
review followed by unrelated output; restart after partial propagation and graph
growth; progress of later runs; and exact-run creation before candidate-set
publication. Preserve every prior impact, fresh-only denial and adverse audit
round. Append independent closure evidence; this document claims no closure.
