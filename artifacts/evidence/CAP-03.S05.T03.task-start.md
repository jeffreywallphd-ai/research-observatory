# CAP-03.S05.T03 task-start acceptance closure

## Authority and scope

- Governing outcome: `planning/slice-plans/CAP-03/CAP-03.S05-dependency-graph-staleness-and-controlled-recalculation.md`, especially decisions 2, 4, 5, and 6 and task 9.3.
- Architecture: Systems Design 9.4 and 13.4 require exact dependency versions, selective durable work, new immutable output versions, before/after comparison, and no silent replacement of accepted judgment.
- Existing boundaries to reuse: immutable aggregate revisions and atomic provenance/dependency registration; durable portable workflow authority and local queue; durable open stale causes from T02.
- UI: no route, component, interaction, or visual change. The existing Task Center and Audit Lineage reference already establish durable jobs and revision/staleness history.

## Acceptance-closure map

| Dimension | Required closure | First proof |
|---|---|---|
| Selective work | Generate one portable durable recalculation job per exact current stale output; bind the stale causes and exact input/configuration authority; do not enqueue unrelated outputs. | Contract/unit test validates generated definition and snapshot and reconstructs only the selected target. |
| Verified reuse | Include unchanged exact dependency revisions as reusable inputs only when their canonical status is `verified` or `adjudicated`; exclude stale or substituted revisions. | Boundary tests for verified/adjudicated reuse, open-stale exclusion, and current-revision CAS failure. |
| Versioning | A recomputed candidate appends revision N+1 under compare-and-swap and retains revision N; it never updates an earlier revision. | Real SQLite integration test reads exact revision history before and after candidate commit and process reopen. |
| Researcher authority | Replacing/restoring an adjudicated result requires an explicit human event. Restore appends N+2 from the exact prior adjudicated revision and current predecessor; it never rewinds history. | Denial test for non-adjudicated restore and stale expected-current authority; successful restore comparison and lineage assertions. |
| Comparison | Compare two exact revisions of the same aggregate and report typed changed fields without exposing content or accepting cross-aggregate substitution. | Unit/integration tests for exact comparison and cross-aggregate denial. |
| Failure/recovery | Workflow authority and queued work survive repository reopen; failed validation or stale authority leaves canonical state unchanged. | SQLite restart test plus before/after revision counts on denied operations. |
| Identity/authority | UUIDv7 identities, project boundary, exact target revision, workflow actor, stale cause IDs, policy/intent/config hashes, material dependencies, expected revision, and event idempotency are bound. | Validation and substitution tests; canonical plan fingerprint equals workflow configuration and command fingerprint. |
| Rights/security | Recalculation remains behind project-scoped repositories, makes model/network access policy-controlled, carries exact rights status, and emits bounded diagnostics. | Contract assertions and project/cross-aggregate denial tests. |

## Compatibility and deferral

- No schema migration is needed: workflow definitions/snapshots, aggregate revision history, provenance, and dependency registrations already store the required durable authority.
- Existing aggregate callers remain source-compatible; exact-revision/history reads extend the repository port.
- Full `service` and `e2e-local` profiles are deferred to slice/checkpoint/Wave qualification unless focused checks expose credible shared-profile impact. Task checks will cover the changed contract, repository, workflow, restart, and quality boundaries.
- Accessibility and new governed experience states are not applicable because this task changes no user interface.
