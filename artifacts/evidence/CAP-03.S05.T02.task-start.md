# CAP-03.S05.T02 task-start acceptance closure

## Frozen authority

- Task / claim base: `CAP-03.S05.T02` at `d9de5b58b3cdd218cab50b5ed3504e8430fb9dfe`; claimed by `codex` on `codex/w1-windows-local-runtime`.
- Approved authority: CAP-03 decision `CAP-03-D02`, the approved CAP-03.S05 plan sections 4, 5.2-5.3, 8, 9.2, and 11-14 at planning commit `c5bbd97c0cdc665eecb973f5862478ef7be97752`, Systems Design sections 9.4 and 13.4, and Vision principle DP11.
- Objective: preview and persist bounded downstream impact when an exact revision or configuration dependency changes, without rewriting immutable revisions or touching unrelated outputs.
- Acceptance criteria: changing the fixture extraction marks exactly the expected matrix, graph, synthesis, and dossier outputs stale; unrelated outputs remain fresh; cycles terminate safely; expected and material failure paths are automated; contracts, migration, fixtures, documentation, and audit behavior change only as required.
- Dependency: `CAP-03.S05.T01` is `DONE` after independent R02 approval; it supplies exact typed direct dependency authority in schema v9.
- Approval/readiness: `planctl wave ready W1 --require-approved` passes for the immutable W1 packet and all 488 generated review pages after this claim.
- Governed experience: N/A. T02 owns a portable Core contract and persistence/query boundary, not a route, page, interaction, or visible-copy change. A later UI consumer must conform to `RO-UI-ACADEMIC-MINIMAL-1.3`.
- Non-goals: no automatic recomputation, candidate replacement, comparison, rollback, or restoration (T03); no UI or public HTTP route; no mutation of historical aggregate revisions or material edges; no reinterpretation of v9 `legacy-unreported` rows as complete.

## Current implementation and exact predecessor

- Schema v9 records one immutable dependency-coverage row per aggregate revision and exact typed direct edges to revision or configuration endpoints. Downstream revision and configuration indexes exist, while transitive impact and stale propagation are explicitly deferred.
- `MaterialDependencyRepository` can read one output registration and content-free missing-registration diagnostics. No stale-state, impact-preview, propagation-run, or checkpoint authority exists yet.
- Aggregate revisions and dependency edges are immutable. Stale authority must therefore be separate and append-only; marking an output stale must not update its historical knowledge status or manufacture transitive direct edges.
- Existing Research Intent impact acknowledgement demonstrates a canonical digest pattern but is not graph authority and must not be reused as a substitute for a graph-snapshot-bound preview.
- Exact compatibility predecessor: the populated governed SQLite v9 fixture, including complete/not-applicable registrations, `legacy-unreported` migrated rows, provenance/workflow facts, and current schema/profile fingerprints.

## Material acceptance rows

| Dimension | Observable closure | Planned proof |
|---|---|---|
| Criterion / outcome | Superseding the exact fixture-extraction revision discovers and marks only its reachable matrix, graph, synthesis, and dossier revisions stale; an unrelated branch remains untouched. Preview is read-only and presents the same ordered impact before mutation. | Real SQLite vertical fixture with exact expected revision IDs, zero preview writes, apply/reopen assertions, and unchanged aggregate/dependency rows. |
| Relation policy | `direct` edges propagate; `non-material` edges remain informational and stop propagation; `conditional` edges propagate only through an explicit versioned policy disposition and otherwise remain review-required/unknown rather than fresh. | Focused traversal table covering all three relation types and denial when conditional policy authority is missing or substituted. |
| State / invariant | Stale state and cause facts are separate from immutable revisions, idempotent per project/change/output/policy, and retain reason, origin, bounded path/SCC summary, confidence or unknown impact, review requirement, detected time, and open resolution state. | Persistence tests reject duplicate/substituted authority, prove stable replay, and show aggregate revisions and direct edges are byte-for-byte unchanged. |
| Identity / authority | Bind project, immutable change ID/idempotency key, exact prior and replacement revision or configuration identity/version, prior/new fingerprint or explicit unavailable state, reason, propagation policy ID/version, actor/event/trace, timestamp, graph watermark, and canonical preview digest. Never resolve a mutable "latest" endpoint. | Shape tests plus cross-project, endpoint, fingerprint, policy, actor, and stale-preview substitution denials. |
| Graph snapshot / preview | Preview ordering and digest are deterministic over the exact reachable edge snapshot. Propagation with a changed graph or mismatched preview digest fails closed or requires a fresh preview. A bounded prefix is never represented as complete. | Repeat preview equality, graph-change conflict, traversal-limit result, and no-write query tests. |
| Cycles / bounds | Traversal has stable ordering, visited/frontier bounds, node/edge/depth/path-sample limits, and deterministic SCC identities. Cycles terminate and each affected revision receives one cause. | Pure traversal-seam SCC fixture; no foreign-key or immutability weakening merely to construct an impossible truthful v9 cycle. |
| Compatibility / unknown history | Exact populated v9 migrates without adding stale facts or changing dependency rows. `legacy-unreported` remains explicit unknown-impact authority and prevents a false no-impact conclusion. Older migration chains still terminate at the exact successor schema. | v9-to-v10 fixture, retained hashes/counts, legacy uncertainty preview, full chain plan, failpoint rollback, and retry. |
| Failure / recovery | Propagation is bounded, cancellable before a commit boundary, and resumable from a durable compare-and-swap checkpoint. Failure before or after one batch cannot mark unrelated outputs or duplicate causes; concurrent/replayed runs converge. | Deterministic write/checkpoint failpoints, cancellation, reopen/resume, concurrent/replay, and canonical post-failure assertions. |
| Audit / diagnostics | Content-free audit facts record run/change/trace identity, visited counts, SCCs, stale counts/reasons, checkpoint/restart/cancel outcome, and failures without labels or research content. | Reopened audit-query assertions and redaction checks. |
| Principal boundary | The portable service and SQLite adapter operate across the real canonical connection/migration boundary with project scoping and no renderer/database coupling. | Focused real-database integration test after close/reopen; architecture/import checks for the new port/module seam. |
| Evidence truth | Narrow traversal, repository, migration, restart, contract, static-quality, and affected-selection checks prove T02. | Complete service/data/graph profiles and the quantitative slice/W1 matrix remain deferred unless a failure cannot be localized. |

## First tests before product code

1. A pure deterministic traversal fixture covers direct, conditional, non-material, unrelated, duplicate-path, and SCC/cycle behavior with explicit bounds and stable preview digest/order.
2. A real v9-derived SQLite project models extraction -> matrix -> graph -> synthesis -> dossier plus an unrelated branch and configuration dependency. Preview performs no writes; propagation persists one stale cause per expected output; reopen/replay changes nothing; aggregate revisions and direct edges remain unchanged.
3. A stale graph watermark/digest, substituted project/change/endpoint/fingerprint/policy, missing conditional disposition, traversal exhaustion, cancellation, injected checkpoint/write failure, and concurrent/replayed run fail closed or resume without false-fresh or partial unrelated state.
4. The exact populated v9 predecessor migrates to v10 with no invented stale facts, preserves `legacy-unreported`, retains prior dependency/provenance/workflow authority, rolls back at each material failpoint, and retries successfully.

## Adversarial preflight

Requested from `agent:t02-adversarial-preflight` and incorporated. The preflight confirmed the approved task is sufficient authority and identified graph-snapshot-bound previews, explicit relation-policy semantics, legacy unknown impact, separate append-only stale/cause state, durable bounded checkpoint/restart authority, SCC-safe traversal, exact v9 migration, and content-free audit as the material closure points. It found no unmet approval or design gate.

## Mandatory gate

None discovered. Stop only if implementation requires a governed experience change, automatic recalculation or replacement authority reserved for T03, expansion of product/security authority, or reinterpretation of immutable v9 history.
