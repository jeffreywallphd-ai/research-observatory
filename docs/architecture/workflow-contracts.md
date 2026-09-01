# Portable workflow contracts

ADR-0025 governs the first portable workflow-plan and execution-history
boundary. The JSON Schema in `packages/contracts/workflow/` is the
language-neutral authority; its generator binds the exact schema SHA-256 into
immutable TypeScript and Python decoders.

## Definition and execution separation

`WorkflowDefinition` is versioned declarative data. It owns the acyclic step
graph, exact input/output schema references, activity-port or human-task kind,
retry and idempotency policy, checkpoint and cooperative-cancellation policy,
bounded permissions, and explicit progress units. It never names a database,
queue, process, local path, server product, shell command, or provider SDK.

`WorkflowSnapshot` is the restart/replay document. It binds exact project,
definition, Research Intent, policy, configuration, and executor-contract
authority. The same definition bytes validate with local and server executor
profiles; only the adapter reference differs.

## Identities and state

The contract deliberately separates:

| Entity | Authority |
|---|---|
| Definition/revision | Immutable process meaning and compatibility range. |
| Workflow run | One execution/continuation under exact governing references. |
| Step run | Runtime instance of one definition-local step key. |
| Logical job | Stable idempotency key and canonical command fingerprint. |
| Physical attempt | One at-least-once execution with its own progress and provenance activity. |
| Checkpoint | Attempt-owned state hash and immutable payload reference at one history position. |
| Artifact | Immutable content/revision reference with explicit committed/incomplete/quarantined/discarded disposition. |
| Human task/decision | Exact run/definition/step, role, actor, evidence, disposition, consequence, and immutable completion. |

Each stateful entity has its own transition table. One append-only global event
sequence records exact from/to state, actor, reason, and any progress,
checkpoint, decision, or interruption binding. The reducer fails on gaps,
reordering, duplicate event identities, illegal transitions, projection
mismatch, decreasing progress, terminal transitions, and security-lock
auto-resume. Human-task request and claim events bind the recorded requester,
request time, and assignee; a completed disposition must be allowed by the
exact bound definition. A canonical JSON round trip into a new reducer must
reproduce every current projection exactly.

## Retry, cancellation, and artifacts

Workers remain at-least-once. Physical attempts reuse the logical job's stable
idempotency key and command fingerprint. Changed-command key reuse conflicts;
only one attempt may become the accepted success. A succeeded job binds that
attempt's exact committed outputs. Failed/cancelled attempts cannot claim
accepted provenance outputs.

Cancellation is request, cooperative safe point, then terminal disposition. An
output/cancellation race is resolved by the durable revision/precondition at
the T02 adapter boundary; losing artifacts remain explicitly incomplete,
quarantined, or discarded. Application lock is a distinct security
interruption and cannot be treated as ordinary restart authority.

## Compatibility boundary

The checked-in legacy operation bridge retains ADR-0011's `op-*` identity,
five-state projection, cancellation flag, sequence, ETag, and replay behavior
while binding it to one UUIDv7 workflow run and snapshot revision. Its
operation sequence is the exact workflow history sequence, and the ETag is
derived from that bound projection rather than supplying independent
authority. The bridge is not canonical history and does not change the current
Core API schema in T01.

T01 added no SQLite migration: the existing `workflows` table remains a
canonical aggregate subtype, not a queue/history table. T02 adds schema v8 with
immutable definition and snapshot authority, append-only history/checkpoints,
mutable queue and physical-attempt projections, and one immutable accepted
output per logical job. Queue claims use an opaque token digest plus a monotonic
generation fence inside one short writer transaction. Activity execution holds
no database transaction; heartbeat, checkpoint, cancellation, retry, crash
recovery, and completion each revalidate the exact project/job/attempt/worker
lease tuple. Completion commits the accepted output and its content-free
canonical provenance-ledger/outbox records atomically, and it accepts only an
existing immutable aggregate revision whose canonical content hash matches the
output reference. Completion replay revalidates the original attempt's opaque
claim capability before returning a receipt. The local worker supervisor
performs bounded expired-lease recovery before admission and enforces separate
concurrency-class limits. Cancellation safe-point polling is read-only, and
recovery updates a bounded batch so maintenance cannot monopolize the SQLite
writer. Process-restart tests prove that an abrupt worker exit is recovered by
a fresh supervisor, rejects its stale lease, and resumes from the latest global
history checkpoint without duplicate accepted output.

CAP-03.S04.T03 owns the governed Task Center projection and interactions; T02
does not introduce Task Center UI or server workflow infrastructure.
