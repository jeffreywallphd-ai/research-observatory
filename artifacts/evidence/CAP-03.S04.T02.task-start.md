# CAP-03.S04.T02 task-start acceptance closure

## Frozen authority and scope

- **Claim:** `CAP-03.S04.T02`, owner `codex`, branch
  `codex/w1-windows-local-runtime`, base
  `9d734971fc5cf3fdb20b2c8d6f5a51d0cfb9887b`.
- **Dependency:** independently approved `CAP-03.S04.T01`; its exact workflow
  definition, snapshot, transition, idempotency, checkpoint, artifact, and
  compatibility contracts remain authority.
- **Approved outcome:** SQLite-backed queue, fenced leases, concurrency-class
  admission, heartbeat, retry, checkpoint, cooperative cancellation, and
  crash recovery under the local executor profile.
- **Non-goals:** no Task Center or other governed UI (T03), no server/Temporal
  runtime, no arbitrary executable jobs, no renderer database access, no S05
  scientific-compute scheduler, and no redefinition of the aggregate
  `workflows` subtype.

## Acceptance-closure map

| Dimension | Required invariant | Focused proof |
|---|---|---|
| Exact authority | Persist and reopen the exact canonical T01 definition and snapshot bytes and their reviewed hashes. | Real SQLite enqueue/reopen test; schema profile fingerprint. |
| Claim fencing | Claim is one short writer transaction; authority is exact project/job/attempt/worker/token-digest/generation/expiry. Raw lease tokens are never persisted. | Two concurrent claimers; digest-only database assertion; forged token/worker and stale recovered lease denial. |
| At-least-once output | Physical attempts may repeat, but exactly one attempt can commit the logical job output. Accepted references must bind an existing same-project immutable aggregate revision and its canonical ledger content hash. Same completion replay is stable only for the original fenced claimant; changed or forged replay conflicts. | Expired-attempt recovery followed by one successful output and one replay; nonexistent-output denial; forged-token replay denial; one canonical ledger event/entity, legacy projection, outbox row, and committed-output row. |
| Transactions | No database transaction remains open while activity code runs. Completion writes acceptance, canonical provenance, legacy projection, outbox, attempt, job, and history atomically; a losing candidate remains an ordinary unaccepted immutable revision. | Supervisor integration, injected failure at the provenance/completion boundary with complete rollback, and WAL reader snapshot during queue mutation. |
| Retry | Only declared retryable codes schedule a bounded deterministic retry while attempts remain. | Retry-policy integration test with due-time denial before backoff expires. |
| Checkpoint/restart | Checkpoints are immutable, contiguous per attempt, selected by run-global history order, and bind a canonical artifact staged by the current attempt. A fresh supervisor performs bounded expired-lease recovery before admission and resolves the checkpoint back to that immutable revision/hash. | Nonexistent/unassociated payload denial; spawned worker process stages and checkpoints a canonical artifact then exits; fresh supervisor abandons it and resolves the exact committed checkpoint artifact; equal-timestamp cross-attempt checkpoint-order test. |
| Cancellation | Cancellation wins before completion; late output is denied. Claimed cancellation is terminal and idempotent, running cancellation converges at a safe point, and losing artifacts receive the approved partial-artifact disposition. Safe-point polling is read-only. Security lock is not ordinary restart authority and never auto-resumes. | Claim/start and safe-point/completion race tests, cancellation/output race, explicit artifact-disposition assertions, polling under an unrelated writer transaction, and security-lock expiry recovery tests. |
| History | Every durable state/progress/checkpoint transition uses the complete T01 event shape and one contiguous run sequence. Retry activation is `retry-scheduled -> runnable -> claimed`; attempt progress is bound to the approved unit/total and cannot regress. | Exact event-field inventory, contract transition replay, repeated-cancellation idempotence, and progress drift/regression denials at the real SQLite boundary. |
| Migration/recovery | Exact v7 databases migrate backup-first to v8; fresh v8 and migrated v8 fingerprints match; every material failpoint rolls back and retries. | Full affected migration test module across v1-v7 fixtures, recovery manifests, and failpoint matrix. |
| Admission/read responsiveness | Class selection cannot claim another class, competing workers cannot double-claim, recovery is bounded, and WAL readers remain available during queue mutation. | Concurrency-class denial, two-thread claim race, bounded two-job recovery, and open-reader snapshot tests. |
| Packaging/architecture | New core/port/migration modules are packaged; database imports remain in the approved Core adapter boundary. | Focused sidecar-contract test, architecture checker, repository-structure checker, and governed Python quality. |
| Governed experience | Not applicable: no route, component, copy, focus, theme, or visible state changes in T02. | Changed-path inventory; T03 deferral. |

## Risk-selected verification

Selected task checks:

1. `tests.workflows.test_local_workflow_executor` for the real queue,
   supervisor, process-exit, denial, cancellation, and WAL boundaries.
2. `tests.data.test_sqlite_schema` for fresh v8 inventory, immutable/mutable
   policy, exact profile, and database capability behavior.
3. `tests.data.test_sqlite_migrations` for every supported predecessor,
   backup/restore authority, v7-to-v8 parity, and material failpoints.
4. The focused sidecar build-contract test, Python quality, architecture, and
   repository-structure checks for changed integration surfaces.

Deferred by the repository's risk-based policy:

- the complete `service`, `data`, and `e2e-local` profile inventories are not
  replayed automatically for this task;
- T03 owns governed Task Center behavior and accessibility;
- slice review owns accumulated contract/executor/UI adversarial integration;
  and
- the complete affected/full matrix, packaging artifact, performance budgets,
  and Windows x64 qualification remain mandatory at W1 exit.

## Preflight disposition

The read-only task-start preflight found no unmet authority, dependency,
design, safety, or feasibility gate. It narrowed the implementation to the
existing Core port/SQLite adapter, exact v7-to-v8 migration, content-free
provenance/outbox binding, and local supervisor boundaries above. A later
adversarial implementation preflight identified five in-scope defects:
supervisor-driven recovery was missing, output references bypassed canonical
artifact/provenance authority, checkpoint selection could regress across
attempts, completion replay was not claimant-fenced, and recovery/cancellation
used unnecessarily broad writer transactions. The implementation and focused
tests now close each defect without expanding approved scope or adding a gate.
A second adversarial pass found four further acceptance-bound defects: invalid
retry/cancellation history and mutable progress authority, unbound checkpoint
payloads, missing dispositions for losing side-effect artifacts, and supervisor
cancellation races. The executor, schema, and focused fault tests close those
findings through contract-valid retry activation, monotonic definition-bound
progress, current-attempt canonical artifact association, atomic disposition
changes, and terminal/idempotent cancellation convergence.
A final focused review identified three narrower contract gaps: subset completion
could over-commit unmanifested staged candidates, checkpoint restart authority
did not expose the exact immutable revision through the public executor port,
and a heartbeat before start could record an invalid claimed self-transition.
Completion now commits only exact manifest members, the checkpoint record carries
its complete bound artifact record, and heartbeat authority begins only after
the attempt enters running state. Focused probes cover all three corrections.
