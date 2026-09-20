# CAP-04.S01.T03 migration-02 independent disposition

**APPROVED for the bounded storage increment; `T03-MIGRATION-01-F01` closed.**
Reviewer: `w2_document_packet_preflight`.
Candidate: `3603e6dfd7b0e6780266520688c95660fe032b9d`.
Prior adverse candidate: `8c314560e2d5fafb1d89716181a3475e3de21908`.
Scope: prior finding plus incremental index/pin risk, not whole-task approval.

Reviewed the exact Git snapshot. The non-unique partial index covers project,
manifest revision and source-record revision where `included=1`; it is included
once in the exact index inventory. It changes no membership or uniqueness rule.
The focused regression requires exact-record index use, and the remediation note
preserves its red-to-green result and the earlier adverse disposition.

Independent narrow replay used the exact candidate production DDL and explicitly
synthetic parent tables in memory, not a product database or a suite rerun. The
full original trigger join now plans its prior-member lookup as:

```text
SEARCH prior USING COVERING INDEX import_manifest_source_record (project_id=? AND manifest_revision_id=? AND source_record_revision_id=?)
```

This closes the residual predecessor scan. New v13 schema pins agree across
storage, migration and recovery/profile contracts:
`13e54503130f8e40036beed26659c5bda2787928c56444987619366e4310b064`.
Independent canonical profile hashing matches
`9ef28bc5d42188c63b50f31eb714c69d040a685311c1dcc5aaf1e89faec42e0b`.
No historical schema, fixture, migration implementation or approved threshold
changed in this remediation. No remaining material blocker found in this scope.

Owner-reported fresh exact-candidate checks: 19 focused constraint, v12 migration,
protected rollback and current-schema tests PASS in 2.922 seconds; Ruff/format
three files, mypy two files and architecture PASS. Broader completed suites were
not rerun by this review. The original migration-01 finding remains preserved.

Canonical repository publication, current rights/draft/lease authority, worker
completion, cancellation/restart, API/UI integration, native-principal and full
packaging/performance qualification remain pending T03/slice/Wave work. This
disposition does not mark CAP-04.S01.T03 complete.
