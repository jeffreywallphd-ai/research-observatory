# CAP-04.S01.T03 — atomic worker completion boundary

The import publisher accepts canonical records, manifest and job output in one
transaction. The worker now supports an explicit already-committed result and
authenticates its exact attempt/output using the existing idempotent queue port.
It does not restage accepted artifacts or run a cancellation check after success.
An uncommitted marker or mismatched receipt raises an observable protocol error;
accepted durable state is not rewritten and errors are not swallowed as success.

Three focused regressions were added first. The initial RED was the missing
`WorkflowAtomicCompletion` import. After implementation all three passed in
0.478s; affected lint, formatting and module typing passed. These are exploratory
results; fresh committed-candidate verification is recorded separately.

Verification selection: these three cases plus existing ordinary-handler and
cancellation-race supervisor tests. No historical full workflow/profile replay.
This is worker protocol coverage, not import activity/API/native wiring or
large-import performance qualification. CAP-04.S01.T03 remains in progress.
