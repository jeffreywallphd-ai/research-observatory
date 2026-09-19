# CAP-04.S01.T02 — native recovery and runtime composition checkpoint

Base: `09c99d1346ef1e67cf8e2f490a22d55bdfa9a271`. Bounded in-progress
implementation; no new product scope, sign-in setting, canonical import or task
completion. Approved ADR-0018/0025 lock and recovery authority remains intact.

Native startup now pre-arms a strict private recovery marker and hands trusted
epoch/launch context to Core through the inherited authentication pipe. Legacy
startup still works but cannot enable the import worker. Core composes actual
project/Intent/privacy/protected-storage/queue/admission adapters, starts the
worker pump and drains it before project close or process shutdown.

Read-only lifecycle preflight found a concrete race in the initial design:
publishing Ordinary when only Core stopped could erase a concurrent lock's
interruption if the native process died before its finalizer. The correction
keeps Active for the entire native session. Actual lock admission atomically
latches interruption under the same mutex as terminal close; no disk write
delays immediate termination. Only irreversible native exit, after command,
lock and start fences plus verified process drain, can publish an ordinary
restart marker. Uncertain stop or failed startup keeps the marker active.
The existing close handler had allowed window destruction before its asynchronous
stop completed; close now keeps UI dispatch alive until that work is drained.

Exploratory checks exposed missing generated frontend assets/dependencies in the
isolated checkout, small Rust test typing/import omissions, and a test assuming
201 where the existing project-create contract returns 200. Expanded typing also
found that the unavailable Intent adapter needed an explicit `project_identity`
implementation returning None after the checkpoint-04 port addition. These were corrected
without changing a valid acceptance test or dependency lock. No full W1 replay.

Selected candidate checks: native recovery marker, changed lock/protected-action
boundaries, supervisor/process-stop tests, strict/legacy startup parsing,
authenticated real protected-project runtime composition, affected service
compatibility, formatting/type/architecture/build metadata. Synthetic keys and
deterministic capacity observations in service tests are not Windows credential
or measured platform capacity proof. The process-stop regression uses only a
test-owned child and Job Object, never a user process.

Still pending: selected-file intake, public import API/native/generated client,
duplicate projection, desktop preview/mapping/exclusion/report UI, actual native
end-to-end, accessibility and large-page checks; formal independent task R01.
