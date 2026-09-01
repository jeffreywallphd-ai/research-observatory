# CAP-03.S04.T03 task-start acceptance closure

## Authority and scope

- Approved task: build the governed desktop Task Center projection and its Core API interactions for durable workflow status, progress, checkpoints, resource use, bounded diagnostics, cancellation, retry/continuation, and human decisions.
- Governing architecture: ADR-0025 and `docs/architecture/workflow-contracts.md`; the renderer consumes a strict generated Core API client and never reads SQLite, workflow authority JSON, lease capabilities, or project files directly.
- Governed experience: `RO-UI-ACADEMIC-MINIMAL-1.3`, specifically `design/ui-reference/task-center.html` and the Task Center page contract in `design/ui-reference/CAPABILITY_COVERAGE.md`. This task restores that approved experience; it does not revise the reference.
- Dependencies: CAP-03.S04.T01 and T02 are DONE and integrated. Their immutable definition/snapshot, append-only history, queue, lease, retry, checkpoint, cancellation, artifact-disposition, and restart contracts remain authoritative.
- Non-goals: workflow-authoring UI, server/Temporal infrastructure, direct renderer persistence, research-content logs, a new product/design decision, or a full-profile run at task scope.

## Acceptance-closure map

| Dimension | Required closure | Focused proof |
|---|---|---|
| Active compute versus human wait | The projection distinguishes queued, claimed/running/cancelling, waiting-human, failed, cancelled, and succeeded work without treating a human gate as active compute. | Real SQLite projection tests plus strict client and renderer state tests. |
| Exact authority | Every item and human task binds project, workflow run, immutable definition revision/version, and snapshot ID/revision. Mutating commands carry the exact expected authority and fail closed on stale or substituted values. | Service precondition tests and hostile generated-client decoder tests. |
| Progress/checkpoints | Quantified progress is bounded and monotonic; unknown/not-applicable progress stays explicit. Latest checkpoint identity/time and retained artifact disposition come only from durable records. | Repository/service tests against queued, running, checkpointed, cancelled, and recovered fixtures. |
| Cancellation | UI cancellation requests cooperative cancellation. The response distinguishes request/cancelling from safe-point cancellation and reports retained-incomplete, quarantined, or discarded artifacts; it never claims immediate termination. | Real queue request plus safe-point convergence test and renderer action-state assertions. |
| Retry/continuation | Terminal failed/cancelled work is never reopened in place. An explicit retry creates a new continuation/run identity bound to the original immutable definition authority and makes the relationship visible. | Domain/service test for new identity, exact definition binding, and stale-request denial. |
| Human decision | Only the assigned human with the required role may complete a requested/claimed task. A decision binds exact run/definition/snapshot/task authority, evidence, disposition, consequence, actor, and time; approval resumes only the new immutable snapshot/continuation authorized by that decision. | Success plus wrong-role, wrong-revision, duplicate/late, and unsupported-disposition tests at the real persistence boundary. |
| Logs/resource use | The public projection exposes bounded content-free state events, worker/concurrency class, attempts, progress, and checkpoint metadata. It excludes claim tokens, raw authority JSON, filesystem paths, secrets, research content, and unrestricted logs. | Response-shape and negative leakage tests. |
| Project boundary | Read requires an open project; mutation requires a compatible read-write session. Project identity is derived by Core from the governed project package, never trusted from renderer input. | Core API closed/read-only/write tests. |
| Experience states | Loading, empty, offline, denied, failed/recovery, populated, running, waiting-human, cancelled, and retained-artifact states have keyboard-usable controls, status announcements, semantic headings/table/labels, focus recovery, and light/dark token use. | Focused Vitest accessibility/interaction tests and existing UI conformance checks for changed paths. |
| Restart/recovery | A fresh Core instance reads the same canonical projection and preserves cancellation, continuation, decisions, checkpoints, and artifact dispositions. | Reopen-the-project service integration test using the same SQLite fixture. |

## Implementation boundaries

1. Extend the workflow repository port with bounded read-model and command methods rather than exposing SQL or executor lease internals.
2. Add a project-scoped Task Center application service and typed Core API models/routes. All project-root validation and write authority remain inside `ProjectLifecycleService.perform_open_project_action`.
3. Regenerate the OpenAPI and strict TypeScript client; reject unknown or contradictory response fields before rendering.
4. Add a dedicated `TaskCenterWorkspace` to the implemented application shell, using shared tokens/components and the approved page vocabulary.
5. Preserve append-only/terminal workflow semantics. Retry is a new continuation identity; a human decision writes a new immutable authority revision/continuation rather than changing approved history in place.

## Risk-selected verification

Selected at task scope:

1. Focused workflow Task Center repository/service tests using a real canonical SQLite project.
2. Focused Core API route and strict generated-client tests for projection and command preconditions.
3. Focused desktop Task Center Vitest tests for state distinction, cancellation, decision/retry, keyboard/focus, announcements, and boundary states.
4. Contract-generation parity, TypeScript typecheck/lint for affected packages, Python format/lint/type checks for changed modules, architecture checking, and changed-path UI-reference conformance.
5. One restart/reopen integration path and one cancellation safe-point path across the actual repository/service boundary.

Deferred by the risk-based policy:

- complete `desktop`, `service`, and `e2e-local` profile replay is deferred to the CAP-03.S04 slice boundary immediately after this final slice task;
- the complete affected/full repository, packaging, performance, Windows x64, and release matrix remains mandatory at W1 exit.

## Preflight disposition

The read-only adversarial preflight found one acceptance-blocking authority gap: a portable human-task definition named allowed dispositions, but did not bind each disposition to its immutable execution consequence. That made a syntax-valid substituted consequence possible at decision time. The task closes the gap in the existing workflow contract rather than trusting the renderer: every allowed disposition now has exactly one definition-bound consequence, Core derives that consequence from the exact definition revision, the client cannot submit it, and the Task Center discloses the mapping before a decision.

The same boundary inspection showed that the packaged renderer's generated request still crosses the native Rust supervisor before reaching Core. The task therefore includes a narrow allow-list for only the generated Task Center routes, exact request bodies, canonical IDs/query encoding, precondition ETags, and idempotency headers. This is required transport closure for the approved UI, not a new public interface.

No unmet approval, dependency, design, safety, external-service, credential, or hardware gate remains. The approved reference already defines the intended experience. The implementation must stop only if the real persistence boundary cannot support immutable continuation/human-decision authority without a material conflict with ADR-0025; ordinary implementation defects are remediated within this task.
