# CAP-03.S05.T01 task-start acceptance closure

## Frozen authority

- Task / claim base: `CAP-03.S05.T01` at `f56d16070637147177c05c3406b5669eb1707cf0`; claimed by `codex` on `codex/w1-windows-local-runtime`.
- Approved authority: CAP-03 decision `CAP-03-D02`, the approved CAP-03.S05 plan section 9.1 at planning commit `c5bbd97c0cdc665eecb973f5862478ef7be97752`, Systems Design sections 9.4 and 13.4, and Vision principle DP11.
- Objective: record typed material dependencies for recalculable outputs and deny completion when dependency coverage is absent.
- Acceptance criteria: every recalculable output declares dependencies before completion; missing coverage fails a stable development invariant and appears in content-free audit diagnostics; expected and material failure paths are automated; contracts, v8-to-v9 migration, fixtures, documentation, and audit behavior change only as required.
- Dependency: `CAP-03.S04.T03` is DONE and its slice is independently APPROVED.
- Governed experience: N/A. T01 is a service/data contract and persistence task; it does not change approved routes, pages, interactions, or visible copy.
- Non-goals: no stale-state propagation or impact preview (T02), no recalculation scheduler or historical replacement flow (T03), no new UI/API route, and no reinterpretation of legacy v8 outputs as fully covered.

## Current implementation and exact predecessor

- `AggregateRevisionDraft.provenance_inputs` can express revision lineage but cannot distinguish source-like records from recalculable outputs or carry dependency type, materiality, governing policy, creation source, or configuration fingerprints.
- The v8 provenance relation projection stores generic PROV relations. It remains provenance authority and must not be misrepresented as the complete staleness graph.
- Aggregate append already commits revision, provenance, and outbox facts in one explicit unit of work. That is the transaction boundary to extend with dependency registration.
- Workflow completion validates staged canonical output revisions and atomically commits completion provenance, outbox, output manifest, artifact disposition, attempt state, and job state, but currently does not verify dependency coverage.
- Exact compatibility predecessor: the governed current SQLite v8 schema and the existing populated v8/v7 migration fixtures. Existing rows migrate as `legacy-unreported`; the migration must not fabricate dependency edges.

## Material acceptance rows

| Dimension | Observable closure | Planned proof |
|---|---|---|
| Criterion / outcome | A recalculable aggregate revision commits a bounded, canonical, typed edge set in the same transaction as its revision, provenance, and outbox; a source-like revision explicitly declares dependency coverage not applicable. | Focused repository test over a real SQLite database, then close/reopen and query exact edge projections. |
| State / invariant | Coverage is one of `not-applicable`, `complete`, or migration-only `legacy-unreported`; only `complete` accepts a nonempty dependency set. Transitive impact is derived later and is not stored as a direct edge. | Positive/negative invariant table in unit/integration tests; stable failure codes rather than optimizable Python `assert`. |
| Identity / authority | Bind output project/aggregate/revision/kind, exact revision or configuration endpoint, endpoint kind, purpose-specific fingerprint, materiality, governing policy version, creation provenance event/activity, actor, and timestamp. | Reject cross-project, substituted revision/kind/fingerprint, self-dependency, duplicate semantic edge, and changed idempotent replay. |
| Configuration endpoints | Prompt, model, parameter, schema, template, and code versions use a typed configuration endpoint rather than masquerading as aggregate kinds. | Contract tests cover both exact-revision and immutable-configuration endpoint variants. |
| Compatibility / predecessor | v8 rows retain their exact canonical/provenance/workflow facts and become diagnostically `legacy-unreported`; v7 migrates through v8 to v9. | Exact populated v8-to-v9 fixture, existing v7 chain fixture, schema/profile fingerprint checks, and restart. |
| Failure / recovery | A late dependency insert, provenance, or outbox failure rolls back revision and all edges; retry succeeds. A missing workflow-output registration leaves the job non-succeeded and is diagnosable after reopen. | Deterministic failpoint/constraint tests and real reopened repository diagnostics. |
| Principal boundary | Workflow completion accepts only staged outputs whose exact revisions have complete dependency coverage; every output in a multi-output manifest is checked. | Focused real workflow-queue + aggregate repository + SQLite completion test, including one uncovered output denial. |
| Evidence truth | Narrow contract/repository/migration/workflow tests, focused Ruff/format/mypy, generated/schema parity, and affected architecture checks prove T01. | Full service/data and complete Windows qualification remain deferred to the slice/checkpoint or W1 exit unless a localized failure cannot be resolved. |

## First tests before product code

1. A real aggregate revision with revision and configuration endpoints commits exact edges atomically, reopens, and exact replay does not duplicate them.
2. Missing, duplicate, self, cross-project, substituted-kind, and substituted-fingerprint dependencies fail without partial canonical state; the missing case exposes a stable diagnostic code.
3. Workflow completion succeeds only for completely covered outputs, denies one uncovered member of a multi-output manifest, leaves the job/attempt unsucceeded, and exposes the same content-free diagnostic after restart.
4. The exact populated v8 predecessor migrates to v9 without invented edges, reports `legacy-unreported`, preserves workflow/provenance facts, and retries after each material migration failpoint.

## Adversarial preflight

Requested from `agent:t02-adversarial-preflight` and incorporated. The preflight identified explicit output classification, a separate typed dependency contract, exact endpoint and policy identities, purpose-specific fingerprints, canonical-set idempotency, per-output workflow completion coverage, deterministic post-rollback diagnostics, and exact populated v8/v7 migration fixtures as the material gaps. It found no unmet authority gate.

## Mandatory gate

None discovered. The approved task authorizes the bounded v9 contract/persistence increment. Any need to change governed experience, expand product authority, or reinterpret accepted historical dependencies would stop and use the existing amendment path.
