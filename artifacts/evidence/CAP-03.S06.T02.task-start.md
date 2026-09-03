# CAP-03.S06.T02 task-start acceptance closure

## Frozen authority

- Task: `CAP-03.S06.T02`
- Claim base: `288cca7cc4cd380360f10879caea619007b71088`
- Claim-state commit: `fc572c58`
- Approved authority: W1 packet; CAP-03.S06 Section 9.2; CAP-03-D04; ADR-0022 immutable Research Intent revisions; ADR-0026 governed workflow profiles and history-preserving navigation state.
- Governed experience: `RO-UI-ACADEMIC-MINIMAL-1.5`, especially `new-project.html`, `intent-contract.html`, and the exact fourteen-profile `WORKFLOW_CATALOG.json` represented by the T01 generated catalog.
- Non-goals: no adaptive application-frame navigation (T03), no durable stage progress/checkpoint service or stale propagation (T04), no all-profile end-to-end qualification (T05), no governed-reference change, and no change to evidence/provenance policy authority.

## Current implementation and exact predecessor facts

- Project creation currently sends a hard-coded `theory-synthesis` template and does not require a scholarly objective or a researcher-selected primary use case.
- Research Intent v1 already persists `primaryUseCase` in immutable revisions and enforces exact revision/idempotency/provenance/outbox relationships, but its impact preview exposes only coarse workflow/output labels and warnings.
- The desktop intent workspace duplicates fourteen use-case labels, workflows, and defaults rather than consuming the exact governed T01 catalog.
- No service persistence currently stores or authenticates T01 `ProjectWorkflowSelection` and `WorkflowProfileMigration` records. Exact lookup of their referenced hashes was intentionally assigned to T02 by the T01 R02 review.
- Exact predecessors are the T01 approved catalog and valid initial/change/migration fixtures, existing Research Intent revisions in the append-only `settings` ledger, and schema-v10 project databases that contain no workflow-selection rows.
- Implementation preflight exposed one validator defect rather than a new authority decision: T01 compared a profile-change target intent directly with the older intent cited by the parent *selection*. That makes a later profile change impossible after valid same-profile intent-only revisions. ADR-0026 requires immediate selection lineage and an immediate prior/target intent pair in the migration, not identical revision cadence across those independent chains. T02 therefore corrects both generated decoders to bind the migration's actual consecutive intent revisions while retaining the immediate parent selection and exact lookup. Cross-runtime regression tests cover the intervening-intent case.

## Material acceptance rows

| Dimension | Observable closure | Planned proof |
|---|---|---|
| Project creation | The public Core create command requires a non-empty scholarly objective and one exact governed profile ID. Before the staged package is published, it commits Research Intent revision 1 and workflow selection revision 1; any bootstrap failure removes staging and publishes no project. | Core API/generated-client contract tests plus a real filesystem/SQLite project-creation integration test for success, missing/unknown profile denial, and injected bootstrap failure. |
| Governed preview | The desktop selection surface consumes the service projection of the exact T01 catalog and displays profile purpose, expected output, linear/revisitable process form, and every ordered stage before creation. | Focused catalog service tests and desktop rendering/interaction tests covering all fourteen profiles without a duplicated UI profile registry. |
| Intent revision impact | A profile change preview identifies affected schemas, checkpoints, outputs, autonomy defaults, stopping logic, and currently known stale artifacts before save can proceed. It also states that all registered tools remain available and evidence/provenance authority is unchanged. | Service tests for each structured impact field, unchanged-profile behavior, exact acknowledgement binding, and desktop disclosure/confirmation tests. |
| Immutable selection authority | Initial creation writes one valid T01 selection bound to the exact intent revision/profile/catalog. A profile change writes the immediate next selection, exact migration, and human acceptance in the same SQLite transaction as the new intent revision. | Decode every stored record with the generated T01 validators; substitute migration/profile/intent/actor/hash fields and require fail-closed reads or writes. |
| Historical preservation | Profile revision never updates or deletes earlier intent, selection, migration, or stage history. Retained stages map only to the same governed stage/page; unmapped prior stages require review. | Query the real append-only ledger before/after a profile change and validate both selection revisions plus the complete migration mapping. |
| Idempotency/concurrency | Replaying the same intent command returns the committed revision and exact workflow-selection authority; changed command/actor or stale revision is denied without partial records. | Existing competing-writer/restart tests extended to count and authenticate selection/migration rows. |
| Compatibility | A schema-v10 project with Research Intent history but no T01 selection remains readable. The next governed save establishes explicit selection authority without rewriting predecessor intent bytes; an unknown catalog/profile fails closed. | Exact prior-database fixture/characterization test and a restart read after governed selection establishment. |
| Principal boundary | Desktop generated client -> authenticated Core route -> lifecycle staging or intent service -> canonical SQLite ledger works without mocked persistence. | Focused native/local Core integration covering project creation and later profile revision, followed by process/service restart readback. |
| Governed experience | Existing v1.5 pages already specify the selector, ordered preview, impact warning, all-tools disclosure, and human authority. T02 restores product behavior to that reference and introduces no new experience decision. | UI-reference integrity plus focused DOM semantics, keyboard-native controls, live status/error, and both-theme token conformance; broad adaptive navigation/accessibility remains T03/T05. |
| Evidence truth | Task evidence must bind the exact candidate and distinguish actual stale-artifact lookup from an explicit empty/no-recorded-artifacts result. | Criterion-linked service, data, desktop, generated-client, restart, denial, and exact-range results; broader slice and Wave qualification remain deferred. |

## Authority-bearing fields

- Governed catalog/reference: reference ID/version, workflow/page-contract hashes, profile-catalog version/hash, profile ID/version/revision, and source workflow hash.
- Intent: intent ID, revision ID/number/content hash, project ID, human actor, primary use case, autonomy, stopping rule, and immutable parent revision.
- Selection: selection ID, selection revision ID/number/content hash, exact intent/profile references, human selector, parent selection, impact preview, and accepted migration reference.
- Migration/acceptance: migration ID/content hash, exact from/to profiles, prior/target intent references, complete stage mappings, decision ID/content hash/time, and human decision maker.
- Repository/idempotency: manifest/domain project bridge, command hash, idempotency key, event/outbox IDs, and atomic record hashes.

## First tests before product code

1. Add service and generated-client tests that fail because project creation does not yet require/return a governed workflow selection or initialize Research Intent.
2. Add Research Intent tests that fail because the current preview omits schemas, checkpoints, autonomy, stopping logic, stale artifacts, all-tools availability, and explicit evidence/provenance invariance.
3. Add real SQLite tests that fail because selection/migration records and hash lookup do not yet exist or commit atomically with the intent revision.
4. Add desktop tests that fail because project creation is hard-coded and the intent workspace uses a duplicated profile registry instead of the exact service catalog.

## Deferred broader coverage

- Adaptive ordered application navigation and supporting-tool return: T03.
- Durable stage-state/checkpoint history and actual dependency-driven staleness propagation: T04; T02 reports only artifacts already known to the current persistence boundary and must label an empty result truthfully.
- All fourteen profile paths, broad accessibility/visual coverage, and complete desktop/service/data qualification: T05, slice review, checkpoint, and W1 exit.

Adversarial preflight: incorporated from the T01 R02 findings by explicitly testing current-primary identity, retain/map semantics, immediate intent lineage, exact migration lookup, and human acceptance substitution at the new persistence boundary.

Mandatory gate discovered: none. The required experience is already approved in reference 1.5, and the task implements the approved service/data/desktop authority without expanding it.
