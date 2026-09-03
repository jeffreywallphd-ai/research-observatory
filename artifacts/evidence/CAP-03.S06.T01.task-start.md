# CAP-03.S06.T01 task-start acceptance closure

## Frozen authority

- Task: `CAP-03.S06.T01`
- Claim base: `f97003d34fc32b705195d518487bd40b79a2545d`
- Claim-state commit: `db896aca`
- Approved Wave authority: W1 packet and approval, plus adopted `W1.A06` exact fourteen-profile criterion correction.
- Governing decisions: `CAP-03-D04`, ADR-0022 immutable Research Intent references, ADR-0025 separation of portable executor workflows from legacy analytical-operation state, and CAP-03.S06 Sections 4-9.1.
- Governed source: `RO-UI-ACADEMIC-MINIMAL-1.5`; `WORKFLOW_CATALOG.json` SHA-256 `2f9f27334e38e090088551433ff5f156257f02f8fd0545a5c735fed8762c39ca`; fourteen distinct profile IDs.
- Non-goals: no project-creation or intent-revision service flow (T02), no adaptive desktop navigation (T03), no durable stage-progress service (T04), no SQLite queue/history reuse, no governed-reference edit, and no hosted executor.

## Current implementation and predecessor facts

- Research Intent v1 already records `primaryUseCase` and produces an immutable accepted-revision reference, but it does not bind a workflow profile version or profile-catalog hash.
- The executor-neutral workflow contract owns analytical definition/run/job/attempt history. It must remain a separate authority from researcher workflow-profile selection and stage navigation state.
- No earlier workflow-profile contract or released profile-state rows exist. The exact predecessor is the approved v1.5 workflow catalog and page-contract inventory, not an inferred runtime model.

## Material acceptance rows

| Dimension | Observable closure | Planned proof |
|---|---|---|
| Fourteen governed profiles | One portable catalog snapshot represents exactly the fourteen approved IDs, exact ordered page-contract steps, titles, purposes, outputs, cycle flags, reference ID/version, and source hash. | Deterministic generator drift check plus exact catalog fixture assertions in TypeScript and Python. |
| State separation | Profile stages represent ordered/optional/cyclical/supporting roles; project stage status represents current/completed/attention/stale and related states without executor job/attempt fields. | Schema inventory assertions and negative tests denying analytical-job fields and invalid state/role combinations. |
| Immutable selection authority | Each selection revision binds project, accepted Research Intent reference, exact profile/catalog reference, actor/time, and immediate predecessor when revised. | Valid first/revised fixtures; reject skipped/self/substituted lineage and mismatched profile/catalog references. |
| Change impact | A profile change binds the prior selection and prior stage-state references, emits an impact preview, and never embeds or rewrites prior history. | Migration/impact fixture plus rejection of missing prior-state coverage, duplicate substitutions, or automatic history replacement. |
| Compatibility and migration | Contract v1 fails explicitly on unknown versions; future profile revisions require an exact from/to migration plan with explicit retain/map/stale/review/drop disposition. | Version rejection and migration-map closure tests; no SQLite migration because no durable profile rows exist before T02. |
| Failure/recovery | Unapproved catalog drift, unknown profile/page identity, unsafe keys, malformed hashes/UUIDv7/time, and ambiguous mappings fail closed without producing a decoded snapshot. | Negative fixtures and immutable owned-snapshot decoder tests in both languages. |
| Principal boundary | Canonical Draft 2020-12 schema produces hash-bound checked-in TypeScript and Python decoders and an exact governed catalog snapshot. | Generator `--check`, TypeScript contract tests, Python contract tests, and Core sidecar packaging inventory/import proof. |
| Governed experience | N/A for rendered UI: T01 consumes the already approved v1.5 catalog and page contracts but changes no governed reference or user-facing behavior. | UI-reference integrity plus negative Git scope check; T03 owns conformance. |
| Evidence truth | Task evidence maps each criterion to schema semantics, exact fixture/catalog hashes, cross-language behavior, packaging, and selected service/data checks. | Focused contract/packaging tests first; affected service/data profile commands only after the narrow checks pass. |

## First tests before product code

1. Add Python contract tests that initially fail because the workflow-profile decoder/catalog module does not exist.
2. Add TypeScript contract tests that initially fail because the workflow-profile export does not exist.
3. Require valid catalog, initial selection, changed-selection impact, cyclical stage-state, strict rejection, immutable snapshots, and cross-language canonical/hash parity.

## Deferred broader coverage

- Project creation and intent acceptance integration: T02.
- Desktop navigation, accessibility, and reference conformance: T03.
- SQLite persistence, restart, checkpoint, provenance, and impact propagation: T04.
- All-profile end-to-end and complete service/data/desktop union: T05, slice review, checkpoints, and W1 exit.

## Bounded inventory note

- Registering the generated Python decoder required revalidating the exhaustive `quality-scope.json` inventory. That check exposed one pre-existing tracked test, `tests/service/test_recalculation_api.py`, which was absent from the inventory. This task adds only that missing inventory entry; it does not change the prior recalculation implementation or tests.

Adversarial preflight: not separately requested; this task follows the established strict-schema/generated-decoder boundary and receives deep independent commit-bound review.

Mandatory gate discovered: none.
