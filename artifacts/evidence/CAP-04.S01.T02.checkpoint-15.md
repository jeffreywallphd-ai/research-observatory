# CAP-04.S01.T02 — durable summary worker composition

Increment from approved `ddaed2c22d64b2893426032ced015766e0e90184`.
Task remains IN_PROGRESS. The new local summary activity reuses the existing
durable queue, supervisor, admission, project lifecycle guards and atomic
provenance ports. No new runner, database, network/model access or canonical
SourceRecord writes. Its exact schema/configuration binds source/parser, accepted
parse, immutable draft/default authority, record count, actual Intent context,
privacy policy, native recovery epoch and summary algorithm.

Each bounded operation revalidates project session and reconstructed authority.
Pages publish compact rows with running-attempt checks; cancellation safe points
and heartbeats retain existing cooperative/fenced semantics. Receipt/completion
publication still requires the exact current draft. Ordinary close is retryable;
new attempts begin at zero. A new native epoch cancels queued old work before
claim. A later explicit calculation uses new authority, never an automatic resume
of the interrupted job. Cancelling summary alone preserves the editable preview.

Common one-step definition/job assembly was extracted without changing legacy
parser schema, configuration or definition bytes; the exact retained comma-job
fixture passes. This is composition for the planned activity, not a broad workflow
refactor. New summary jobs use a separate input schema/activity and exact-input
idempotency. Terminal retries reuse the existing Task Center continuation command.
Their binder loads the real unsuccessful predecessor, validates exact scientific
authority and new execution identities, and accepts only that predecessor's retry
command fingerprint. Pending/completed continuations appear under their actual
job IDs instead of the unsuccessful original. No speculative recursive recovery
controller or new approval gate is introduced.

The first real-composition test failed on the absent scheduling method before
implementation. Focused tests now cover actual project/Intent/queue/provenance
success, duplicate requests, ordinary restart, stale edits, security-epoch
cancellation, preserved draft cancellation, closed project denial, material input/
claim substitutions, continuation and retry-of-continuation, forged predecessor,
changed policy between pages and retryable interrupted computation. A linter
flagged the immediately invoked page lambda's loop capture; it now binds its
cursor explicitly. Commit-bound checks and independent review follow.

Selected: new worker tests, affected original parser workflow/service/activity,
historical queued-job fixture, packaging inventory, lint/type/architecture and
clean build identity. Full W1 replay is not selected. API/renderer/native-window,
packaged execution and actual 100k-project qualification remain next task work;
these service fixtures do not establish those broader claims.
