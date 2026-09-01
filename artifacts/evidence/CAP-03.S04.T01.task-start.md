# CAP-03.S04.T01 task-start acceptance closure

## Frozen authority

- **Task / claim base:** `CAP-03.S04.T01` was originally claimed by `codex`
  from `c9260e1e981fea84a651dd59104aad12e1fb8d8e` on
  `codex/w1-windows-local-runtime`. The exact task was resumed after the
  approved and adopted W1.A05 interruption at repository commit
  `08f35d9d5efedda4400835182d0511348f401974`; taskctl intentionally retains the
  original claim base.
- **Approved scope:** define the versioned, portable workflow definition and
  execution-state contracts for workflow runs, steps, jobs, attempts,
  checkpoints, immutable artifacts, retries, cancellation, progress, and
  auditable human tasks.
- **Dependencies:** independently completed `CAP-03.S03.T02` and
  `CAP-02.S02.T03`. The complete W1 approval packet validates, and W1.A05 is
  independently approved and adopted.
- **Governing architecture:** CAP-03-D01 through D03; Systems Design sections
  3.3, 3.4, 5.2, 6, 13, 16, Appendix B, and Appendix C.1; ADR-0011,
  ADR-0013, ADR-0014, and ADR-0024; the exact CAP-03.S04 Section 4 selections.
- **Non-goals:** no SQLite queue/tables, leases, scheduler, worker process,
  crash recovery adapter, or resource-pool implementation (T02); no Task
  Center or other user-facing experience change (T03); no Temporal/server
  infrastructure (W10); no arbitrary executable commands, raw research
  content, local paths, credentials, provider SDK types, or persistence handles
  in a portable contract.

## Current implementation and predecessor boundaries

- The current `OperationRegistry` is an explicitly bounded in-memory transport
  seam. Its `queued/running/succeeded/failed/cancelled` status and SSE replay
  remain compatible UI/API projections, but it is not durable workflow
  authority and must not be relabeled as one.
- The canonical domain contract supplies UUIDv7 aggregate/revision identities;
  ADR-0013 retains the exact legacy project UUIDv4 reader bridge. The workflow
  contract must not create a second identity convention.
- ADR-0024 supplies content-minimized activity/provenance identities and exact
  immutable artifact-revision references. T01 defines binding seams and audit
  identities; T02 owns atomic persistence with the provenance/outbox ledger.
- ADR-0014 fixes SQLite as the local canonical adapter, but neither SQLite nor
  Temporal types may appear in the portable definition. A local and a server
  executor must accept the same exact definition bytes and produce conformant
  state histories.
- No workflow contract, compatibility fixture, or restart reconstruction
  validator currently exists. T01 therefore adds an initial v1 contract rather
  than migrating released workflow records. Exact current fixtures are the
  existing operation projection, domain identity, and provenance event
  contracts; persistence migration begins in T02.
- W1.A05 changed authentication/settings authority while this task was paused.
  Those committed paths are outside T01 and will be disclosed as intervening
  approved scope in commit-bound evidence rather than attributed to this task.

## Material acceptance-closure map

| Dimension | Observable outcome and invariant | Planned proof |
|---|---|---|
| Definition portability | A workflow definition is strict versioned data containing schema references and registered activity/human-step declarations, with no executor, SQLite, Temporal, path, URL, shell, or provider implementation field. | Draft 2020-12 validation plus generated Python/TypeScript decoder tests; substitute forbidden fields and path/command-like values. |
| Exact definition authority | A run binds one definition ID, immutable revision ID, semantic version, and canonical content hash. Local/server executor metadata exists only on the run snapshot and cannot change definition bytes. | One definition fixture validates against both local and server snapshots; identity/hash substitutions fail closed. |
| State reconstruction | Ordered, contiguous transition history reconstructs the exact current workflow, step, job, attempt, and human-task projections after serialization/reload. Each entity begins in its declared initial state; terminal states have no outbound transitions. | Canonical JSON restart round trip and history-reducer assertions; missing, reordered, wrong-from, wrong-final, and terminal-outbound events are rejected. |
| Identity/reference closure | Workflow/run/step-run/job/attempt/checkpoint/artifact/human-task/event/decision identities are unique in their namespaces and every cross-reference resolves to the exact owning entity. | Table-driven substitution tests for unknown/wrong owner, duplicate identity, step-key, attempt number, artifact, checkpoint, and human-decision references. |
| At-least-once retry | A logical job carries one stable idempotency key and an exact command fingerprint across physical attempts; changed-payload reuse conflicts. Attempts are contiguous and may repeat execution, but at most one attempt succeeds and a succeeded job binds that exact attempt and its committed outputs. No exactly-once side-effect claim appears. | Valid retry fixture plus changed-fingerprint reuse, duplicate/gapped attempt, two-success, mismatched-current-attempt, and uncommitted-output negative tests. |
| Checkpoint/restart | Checkpoints bind an exact attempt, monotonic checkpoint sequence, immutable state/payload hashes, and a history position. They contain references, not inline research content. | Restart fixture with a running-progress self-transition and checkpoint; reordered, duplicate, missing, and foreign-attempt checkpoints fail. |
| Progress | Progress is explicitly quantified, unknown, or not-applicable. Quantified progress is bounded and monotonic within an attempt; final success reaches the declared total when known. | Positive unknown/not-applicable fixtures and decreasing/over-total/incomplete-success negatives in both runtimes. |
| Cancellation/failure | Definitions declare cooperative cancellation and partial-artifact disposition. Runtime histories allow only the approved cancelling/cancelled/failure paths; retained partial artifacts remain explicitly incomplete and never become committed outputs. | Transition-matrix tests and partial-artifact substitution cases; T02 owns real process interruption. |
| Human authority and audit | Human tasks are durable entities with requester, required role, evidence references, assignee state, and an immutable typed decision. Completion binds the exact decision ID/actor/time in ordered history; replay cannot infer or overwrite approval. | Completed and pending human-task fixtures; missing decision, actor/decision substitution, completed-without-event, and overwritten-history forms fail closed. |
| Policy/configuration authority | Every run pins exact intent revision, policy revision/hash, and configuration reference. Every human task binds its exact run, definition revision, and step run; late or cross-run decisions fail closed. | Identity/hash substitution tests for intent, policy, configuration, human run/definition/step, required role, deciding actor, and decision evidence. |
| Audit/provenance boundary | Workflow history records execution transitions; scholarly provenance records accepted transformations; telemetry is operational and retention-bounded. Failed/cancelled attempts cannot claim committed artifacts or accepted provenance outputs. | Contract field inventory and negative fixtures for provenance output on unsuccessful attempts and inline telemetry/research payloads. |
| Legacy operation bridge | Existing `op-*` status and bounded SSE replay remain a transport projection. A bridge record binds one legacy operation ID to one UUIDv7 workflow run without treating the legacy ID or five-state projection as canonical workflow history. | Strict bridge schema/decoder tests, identity substitution and replay-gap characterization; no Core API route change in T01. |
| Security-lock interruption | Ordinary process crash/restart may reconstruct resumable state. Application lock remains a distinct security cancellation boundary: protected work cannot auto-resume without a future explicit checkpointed allowlist and compatible ADR. | Definition/snapshot denial for implicit lock-resume authority and explicit interruption-reason classification; native policy behavior remains unchanged. |
| Trust boundary | Portable values are bounded, strict, content-minimized references. Dangerous object keys, unknown fields, filesystem locations, inline payloads, and unregistered execution directives are denied before persistence/execution. | Hostile structural/schema fixtures and immutable-snapshot tests in generated runtimes. |
| Compatibility | Contract/history/executor compatibility versions are explicit. Unsupported major versions and unknown state/step kinds fail explicitly; an exact v1 fixture remains canonical and hash-stable. | Generator drift check, schema hash assertion, exact checked-in v1 fixtures, and local/server conformance tests. |
| Principal boundary | The same checked-in JSON fixtures are validated by the Draft 2020-12 schema and by independently generated TypeScript and Python runtimes. | Contract package type/test/check commands plus focused Python contract tests. T02 will add the real SQLite restart boundary. |
| Governed experience | N/A: T01 changes no route, component, copy, focus behavior, or visible workflow state; T03 owns the approved Task Center experience. | Changed-path inventory and UI-reference deferral in evidence. |
| Evidence truth | Narrow contract, generation, type, hostile-input, transition, restart, and packaging-inventory checks prove T01. Real SQLite kill/restart, renderer behavior, and full W1 qualification are not claimed early. | Criterion-linked manifest records selected checks and explicit T02/T03/slice/W1 deferrals. |

## First tests before product code

1. Add Python contract tests that demand strict definition/snapshot decoding,
   local/server definition equivalence, canonical restart reconstruction, and
   immutable caller-owned snapshots.
2. Add transition/invariant tests for illegal terminal transitions, decreasing
   progress, broken identities, invalid retries/checkpoints/artifacts, and
   incomplete or substituted human decisions.
3. Add TypeScript tests over the same checked-in fixtures so portability is a
   real cross-runtime boundary rather than a Python-only model.
4. Add exact authority-substitution tests for definition/intent/policy/config,
   job fingerprint, human run/step/actor/decision, unsuccessful output,
   legacy-operation bridge, and security-lock interruption.
5. Run the tests once while the workflow package/runtime is absent and retain
   the failing result as the test-first boundary; then implement only enough
   schema, generator, documentation, and generated runtime to close them.

## Deferred broader coverage

- T02 owns the SQLite migration, atomic queue/provenance transactions, leases,
  worker kill/reclaim, real process restart, resource isolation, and queue-load
  behavior.
- T03 owns the Task Center, SSE/operation projection integration, cancellation
  interaction, human-gate UI, accessibility, and governed reference evidence.
- CAP-03.S04 slice review owns the integrated contract/executor/UI adversarial
  union. The complete Windows-x64 packaging, performance, recovery, security,
  accessibility, and cross-capability matrix remains mandatory at W1 exit.

## Preflight and gate

- **Read-only adversarial preflight:** incorporated. It confirmed there is no
  unresolved authority decision and added exact job/fingerprint replay,
  intent/policy/config binding, audit-versus-provenance separation, the legacy
  operation projection bridge, security-lock interruption semantics,
  cancellation/commit-race disposition, and cross-runtime historical-fixture
  parity to the acceptance surface.
- **Mandatory gate discovered:** none at the initial pass. The capability packet
  already selected versioned data contracts, at-least-once execution,
  idempotency, checkpoints, explicit identities, cooperative cancellation, and
  local/server conformance. A material contradiction found by the preflight
  would still stop the task rather than be silently decided here.
