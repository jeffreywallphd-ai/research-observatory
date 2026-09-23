# CAP-04.S01.T03 — first protected 100k commit diagnostic

Candidate: `3d87c3545c6908512054c5cbdb08e0445a488d8d`.
Outcome: **failed first attempt; interrupted during automatic retry**. Not
performance qualification or task completion. The original ignored report still
says running because process interruption ended the runner before finalization;
that stale field is not completion evidence.

The opt-in `tests.service.test_import_commit_scale_windows` ran 100,000 generated
CSV metadata records with the production 30-second worker lease unchanged.
Project/intake took 5.338 seconds and parsing took 81.825 seconds. The first
publication writer exited after 29.876 seconds. The production worker started a
second attempt; the owner interrupted this diagnostic instead of waiting through
another expensive retry. No product deadline or test assertion was relaxed.

Read-only inspection of the same protected fixture after interruption confirmed:

- 100,001 parse rows (including the CSV header).
- First commit attempt `abandoned`, diagnostic `lease-expired`.
- Second attempt left running in retained storage after process interruption.
- 112,801 provisional commit rows across attempts.
- Zero canonical import source records, manifests, members and seals: the first
  writer rolled back, not a partially published import.

Source and HEAD were not edited while the run was active. This was real DPAPI
and SQLCipher under the execution principal, not proof of the interactive
researcher's principal or packaged/native execution. A native build and separate
tiny desktop fixture ran concurrently; timing is diagnostic, not an uncontended
reviewed baseline. The fixture and original log remain ignored under
`artifacts/tmp/`; do not commit account/path or runtime material.

## Narrow next step

The independent follow-up found repeated fixed-query SQLAlchemy compilation in
draft-row reads and canonical creation; query-plan inspection did not substantiate
an index mismatch or quadratic ordinal-MAX scan. Profile the bounded writer before
choosing a remedy. Preserve all authority, provenance, atomicity and lease checks.

Improve only this diagnostic to distinguish preparation, verification, writer
entry/exit and failure code; fail on an **observed** retry and retain its attempt
history. A polling observer cannot promise that a retry never started. Add exact
commit-output/source/manifest counts and truthful interrupted/failed finalization.
No unrelated completed suite needs replay.

## Focused profile after the failure

The same 1,000-record synthetic protected path, with `cProfile` wrapping only
the final writer, passed in 23.815 seconds at the unchanged candidate. This is
an instrumented diagnostic rerun justified by the observed 100k failure, not
fresh performance qualification. The measured writer was 10.410 seconds with
profiling overhead (the earlier uninstrumented pilot was 4.307 seconds).
Its cumulative profile attributes about 6.976 seconds to aggregate provenance
and 2.073 seconds to SQLAlchemy statement execution/compilation. These overlap
with enclosing calls and must not be summed into elapsed time. Compilation
alone is not demonstrated to close the large-writer lease failure. Keep the
default lease and final publication authority unchanged until a reviewed
contract-preserving implementation is established.

## Bounded measured-hot-path and diagnostic increment

The adapter now compiles its fixed aggregate lookup/insert statements once with
the existing SQLAlchemy dialect and binds fresh values at execution. Draft reads
likewise compile their fixed ordinal lookup once. No caller values, repository
results or authority decisions are cached. Existing transactions, source checks,
provenance, replay and lease fences are unchanged. The two focused regressions
first failed on repeated compilation, then passed after the change.

Development checks: 36 hot-path/publication/shared-repository cases passed in
32.401 seconds, including all aggregate kinds, conflict/idempotency, rights denial
and atomic rollback. The initial new test imported another TestCase class and
therefore also discovered its publication cases; the import now uses the module
to avoid accidental duplicate collection. Ruff and mypy on the two changed
product modules passed. These are pre-commit checks, not a final-candidate claim.

The diagnostic now reports bounded, thread-safe entry/exit/activity/failure
counters for staging, identity verification and atomic publication. It fails
on the first observed retry, including success on a second attempt, and records
commit-specific accepted outputs, source/manifests/members/seals and attempt
dispositions. Its three regressions first errored on absent helpers and then
passed in 1.025 seconds. A hard process kill still cannot execute finalization;
an interrupted `running` report remains nonqualifying. The completed summary
runner and all production deadlines are unchanged. This bounded evidence-control
repair preserves its predecessor diagnostic as historical failure evidence.

The 100k test has not been rerun at this increment. Query compilation is only
one measured contributor; the large atomic-writer lease/cancellation issue
remains open. Do not mark CAP-04.S01.T03 or its slice complete from these checks.

## Renewable atomic publication and stop-only interruption

A follow-up independent read-only preflight established that the 30 seconds is
a renewable lease interval, not a whole-activity duration cap. Publication now
reuses the queue's exact heartbeat predicates/progress/history on its own writer
connection. A live lease can renew at the unchanged interval; a genuinely expired
claim still fails and rolls back. No second writer is opened inside publication.

The service registers the current binding, command and exact claim. Authenticated
cancel/close routes signal matching work before the outer lifecycle mutex, with
a one-second drain bound. The signal only requests interruption: after rollback,
the ordinary cancellation path revalidates and persists the request before a new
admission. Rollback also discards in-transaction heartbeats; existing bounded
expired-attempt recovery handles that case without reviving the old claim.
Long SQL receives a scoped storage-owned stop hook, cleared before rollback.
Native security lock remains unchanged. Unconfirmed project-action errors no
longer claim that no canonical import was published.

Development regressions cover renewable lease crossing, genuine expiry denial,
concurrent authenticated cancel and close during publication, cancellation after
uncommitted renewals are rolled back, wrong command/current-binding rejection,
bounded drain timeout, interruption inside an adapter's SQL statement, and the
commit-winning race retaining accepted results. The first renewable-lease and
pre-mutex interruption regressions failed before their respective implementation.
The protected scale run, independent committed disposition and ordinary-read
responsiveness during the writer remain pending. This is not task completion.

The first planning-site check overlapped generation and reported an old worksheet
projection. After generation finished, the unchanged generated result passed its
full check. Preserve the failed invocation as orchestration error, not a product
or source-authority defect; run generation and its validator sequentially.
