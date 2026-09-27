# CAP-04.S03.T02 — durable worker and lifecycle checkpoint

Development progress after `bda0ce91`, on the same approved W2 claim. This is
not qualifying evidence or independent task disposition; local main remains at
the independently approved T01 integration.

The service persists immutable batch requests, captures the complete accepted
source snapshot, and schedules the existing executor-neutral durable job. The
worker enumerates actual source owners and binds current project, full accepted
Intent, policy, actor and session authority again before atomic publication.
Production composition shares the document admission lane with imports and
connectors. A saved request can recover after enqueue failure and a same-session
restart; a changed session cancels queued authority before any attempt.

Cancellation reaches the writer before waiting for its lifecycle lock. Task
Center commands retain the exact run/snapshot/history preconditions. An independent
advisory identified that stale requests must be rejected before discarding
provisional lease renewals. Valid cancellation persists first, then uses existing
expired-lease recovery where needed. Accepted publication survives a lost return.

The same advisory exposed two composition gaps. Task Center GET previously waited
behind publication, preventing a real refresh/cancel journey; it now reads the
committed WAL projection while the already-authorized publication fence remains
pinned. Project close previously drained one worker before signalling another;
all composed workers now receive stop signals before any drain, for close,
failed-open cleanup and shutdown. A failed drain retains the project session.

Retained development observations in ignored `artifacts/tmp/` include:

- `CAP-04.S03.T02-batch-request-01.log`: one persistence/replay/substitution case
  passed in 1.969 seconds after the missing-method test.
- `CAP-04.S03.T02-batch-worker-01.log`: three initial worker cases passed in
  10.374 seconds.
- `CAP-04.S03.T02-lifecycle-before-01.log`: both real API interruption tests
  failed before the routes were wired; `lifecycle-02.log` passed both.
- `CAP-04.S03.T02-worker-races-01.log`: eleven passes and two fixture errors
  reported as waits; the diagnostic identified a nonexistent lease field on the
  public job projection. The corrected test reads the actual stored lease.
- `CAP-04.S03.T02-read-before-01.log`: the real GET/cancel journey failed and
  valid cancellation exposed missing expired-lease convergence. Stale cancellation
  after the durable lease expired already passed.
- `CAP-04.S03.T02-stop-order-before-01.log`: active import close did not receive
  its stop signal before idle reconciliation attempted to drain.
- `CAP-04.S03.T02-worker-races-02.log`: all fourteen worker/API/race cases passed
  in 52.049 seconds after the fixes. These use real local owners, persistence,
  queue, service and HTTP boundary with development plaintext canonical storage;
  they are not protected Windows/native/UI qualification.
- `CAP-04.S03.T02-worker-types-03.log`: targeted types passed for worker, service
  and Task Center after a lambda annotation issue was corrected. Affected lint
  and architecture checks passed.
- `CAP-04.S03.T02-lifecycle-regressions-01.log`: eighteen affected import
  interruption/lifecycle, Task Center API and protected Windows source-slice
  integration tests passed in 141.319 seconds. The source-slice case exercises
  four providers, cache/failure/denial/cancellation and restart using retained
  local fixtures; it is not qualification of the new reconciliation UI.

The incremental source-only advisory found no further material blocker in the
three lifecycle remediations. This is not independent task approval.

The same checkpoint adds bounded candidate inspection and authenticated batch
prepare/schedule/status/cancel routes. The saved request's complete definition,
snapshot, Intent, policy and configuration are authenticated before returning
status. Historical scores remain identical after a human split; current membership
and existing/pending dependency warnings are separate projection fields.
`candidate-inspection-before-01.log` retains the missing-method failure;
`candidate-inspection-02.log` passes the split/history case in 2.233 seconds.
`batch-api-before-01.log` retains the missing-route failure. The first wired API
run exposed an invalid activity-field assumption on the public job record;
`batch-api-03.log` passes both corrected real service/queue/API journeys in
7.035 seconds, including cancelled/no-output and request substitution denial.
Generated OpenAPI, TypeScript types and four portable batch/candidate schemas
are updated; client methods/decoders and native admission remain to be connected.
`CAP-04.S03.T02-worker-api-dev-01.log` then passed all twenty request, worker,
API, split/history and portable contract cases in 63.091 seconds. These remain
development observations. Current targeted types (five changed production files),
affected lint, generated-contract drift and architecture checks pass; the quality
inventory accounts for all 392 governed Python files.

The subsequent candidate/API advisory exposed a batch status read taking a writer
transaction while pinning the stop mutex. `batch-status-before-01.log` retains
the failed real poll/cancel journey. Job state and accepted output now come from
one authenticated read-only WAL transaction. An attempted `query_only` PRAGMA
was rejected by existing canonical storage protection (`batch-status-02.log`);
the implementation preserves that protection and uses a normal read transaction.
`batch-status-03.log` passes the real poll/cancel case in 3.857 seconds.
Candidate pages now expose authenticated frozen/current inventory fingerprints
and an explicit changed-inventory state without rewriting historical scores.
`candidate-inventory-before-01.log` retains the missing-field failure;
`candidate-inventory-02.log` passes eight inventory, corruption, history and
newly accepted unrelated import cases in 16.941 seconds. Targeted types,
affected lint and generated-contract checks pass after these changes.
`worker-api-dev-02.log` subsequently passed all twenty worker/API/contract cases
in 71.447 seconds. The independent read-only advisory replay inspected these logs
and source, closing both findings with no material incremental defect. It did not
run duplicate tests or provide formal task approval.

Generated client methods/native admission, governed review UI, dependency propagation/recovery,
fresh committed qualification, independent disposition and integration remain.
Full S03 and W2 qualification, including the previously retained type and Windows
symlink-token obligations, remain outstanding.
