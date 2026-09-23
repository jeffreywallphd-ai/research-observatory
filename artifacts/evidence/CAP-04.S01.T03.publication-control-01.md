# CAP-04.S01.T03 — atomic-publication control increment

Candidate: `c136912f8d115d50cfc84a9d65d518431a301019`.
Base: `3d87c3545c6908512054c5cbdb08e0445a488d8d`.
Task and 100k qualification remain open; this is not a completion submission.

Fresh checks with committed HEAD and selected inputs unchanged:

- 65 cases passed in 78.241 seconds: `ImportCommitHotPathTests`,
  `ImportCommitPublicationTests`, `ImportCommitActivityTests`,
  `ImportCommitServiceTests`, `ImportCommitInterruptionTests`,
  `ImportCommitDiagnosticReportingTests`, `SqliteRepositoryTests`.
- Five existing queue/storage cases passed in 0.716 seconds: expired-worker
  fencing/recovery, progress-authority rejection, runtime history/idempotent
  cancellation, supervisor cancellation races, and sealed ordinary connection.
- Mypy on nine changed product modules and architecture check passed.
- Ruff format passed on all 13 changed Python files. Ruff lint **failed** with
  E501 on the new project-action error string. The successor splits only that
  literal, preserving its runtime bytes; rerun affected lint and the truthful
  drain-error check, not unrelated completed suites.

Selection covers the changed shared-query, transaction/lease, local interruption,
SQL interruption, API lifecycle and evidence-reporting boundaries. Development
adverse attempts and the protected 100k failure remain in `scale-01`. No claim is
made that development SQLite tests prove production SQLCipher/native packaging.
The protected small pilot, 100k diagnostic, ordinary-read latency and independent
committed disposition remain pending. Existing slice/Wave full-profile, native
and packaging obligations are not replaced by this increment.
