# CAP-04.S01.T03 migration-01 independent disposition

**CHANGES REQUESTED — one P2 blocker in the bounded storage increment.**
Reviewer: `w2_document_packet_preflight`.
Candidate: `8c314560e2d5fafb1d89716181a3475e3de21908`.
Base: `6596136cdb268aa3391fc09c782f00fac9f4da87`.
This is not a formal whole-task review round or task-completion disposition.

## P2: Index the predecessor-membership constraint lookup

Finding ID: `T03-MIGRATION-01-F01`.
Location: `services/core-api/src/research_observatory_core/storage.py:2552-2555`;
the current index set ends at line 2582 without a source-record membership index.

The new member trigger checks each non-null previous-record reference against
the explicit predecessor's included membership. Its available indexes constrain
only project and manifest, not `source_record_revision_id`. Publishing N compared
records therefore repeatedly scans the predecessor's N-member range: quadratic
work inside the required atomic writer transaction. This is a concrete impact on
CAP-04.S01 section 11's 100k-record bounded-resource requirement and the task's
changed-file comparison path, not a claim about an unmeasured latency threshold.

Independent reproduction used only the exact candidate's production DDL and its
explicitly synthetic parent-table definitions in an in-memory SQLite connection.
`EXPLAIN QUERY PLAN` for the trigger's predecessor query returned:

```text
SEARCH m USING INDEX sqlite_autoindex_import_manifests_1 (revision_id=? AND project_id=?)
SEARCH p USING INDEX sqlite_autoindex_import_commit_preparations_2 (attempt_id=? AND project_id=?)
SEARCH prior USING INDEX import_manifest_doi (project_id=? AND manifest_revision_id=?)
```

The prior source-record equality is a residual range scan. No product database,
user data, runtime import or broad suite was executed by this review.

Smallest closure: add a non-unique index covering project, manifest revision and
source-record revision, optionally partial on `included=1`; register it in the
schema's exact index inventory and update only the new v13 fingerprints. Add a
focused production-DDL query-plan regression showing the source-record equality
is an indexed lookup, while retaining the existing membership denial tests.

## Closed advisory gaps and reviewed boundaries

- Published membership now matches the exact prepared inclusion, decision,
  warning, raw-digest and null-safe DOI values. The new substitution tests retain
  isolated savepoints and positive insertion coverage.
- Predecessors must be sealed; prior-record references must belong to their
  included membership. Both earlier relational advisory gaps are closed.
- The additive migration, registry and recovery/profile changes preserve the
  exact v12 endpoint. Literal v11/v12 fixtures and the historical v12 migration
  are unchanged. Successor test changes extend current history expectations,
  without rewriting predecessor authority or removing rollback assertions.
- The new migration module is present in build-contract, hidden-import and
  verifier/test inventories. Schema/SQLCipher tests remain distinct from runtime
  authority and Windows-principal qualification.

Owner-reported fresh exact-candidate checks: 48 focused schema/migration/storage
and packaging-contract tests PASS in 29.784 seconds, no skips; mypy three product
files and architecture PASS. Those checks do not cover the identified lookup
shape. The migration note retains prior red runs, setup failures and fixes.

Repository current-rights/draft/lease checks, atomic canonical/provenance/worker
publication, runtime/API/UI behavior and whole-task qualification remain pending
and are not inferred from this schema increment.
