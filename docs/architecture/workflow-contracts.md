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
reordering, illegal transitions, projection mismatch, decreasing progress,
terminal transitions, and security-lock auto-resume. A canonical JSON round
trip into a new reducer must reproduce every current projection exactly.

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
while binding it to one UUIDv7 workflow run and snapshot revision. The bridge
is not canonical history and does not change the current Core API schema in
T01.

T01 adds no SQLite migration: the current `workflows` table is a canonical
aggregate subtype, not a queue/history table. CAP-03.S04.T02 owns the real
SQLite migration, durable reducer/queue, leases, supervisor, atomic
provenance/outbox integration, and process-restart proof. CAP-03.S04.T03 owns
the governed Task Center projection and interactions.
