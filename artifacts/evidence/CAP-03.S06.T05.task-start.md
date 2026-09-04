# CAP-03.S06.T05 task-start acceptance closure

## Frozen authority

- Task: `CAP-03.S06.T05`
- Claim base: `b6c33dd67a4c219efbc7856b21653f2fdc2db3d4`
- Objective: verify profile selection, exact navigation order, supporting-tool access, durable restart, profile revision, accessibility, and expected-output handoffs across all fourteen approved scholarly workflows.
- Dependency: independently approved `CAP-03.S06.T04` at review commit `c6ca6d7096b5db60c5ea655d80ecb86fa1abdfe6`.
- Governing authority: approved W1 packet; amended CAP-03.S06 Section 9.5; accepted ADR-0026; `docs/architecture/workflow-profile-contracts.md`; Systems Design Sections 3, 9, 12-19; approved `RO-UI-ACADEMIC-MINIMAL-1.5` workflow catalog and page contracts.
- Authority reconciliation: the slice frontmatter retains its historical 1.3 approval marker, while the later accepted ADR-0026 and approved W1.A06 amendment bind this task to the exact fourteen-profile Academic Minimal 1.5 catalog. T05 tests the current binding and does not rewrite historical plan metadata.
- Non-goals: no new or revised workflow profile, route, page contract, output, use-case label, navigation pattern, research interpretation, downstream workspace implementation, sign-in behavior, or release authority; no synthetic completion from route visits or analytical jobs; no replacement of full W1-exit qualification.

## Implemented baseline and exact predecessor fixtures

- T01's generated portable catalog fixture `packages/contracts/workflow-profile/fixtures/approved-workflow-profile-catalog.v1.json` is a deterministic projection of the exact `design/ui-reference/WORKFLOW_CATALOG.json` bytes. It binds `RO-UI-ACADEMIC-MINIMAL-1.5`, catalog hash `sha256:2f9f27334e38e090088551433ff5f156257f02f8fd0545a5c735fed8762c39ca`, fourteen ordered profiles, per-profile source hashes/revisions/outputs, linear or revisitable process form, and access to all 33 registered tools.
- T02 persists the selected profile as immutable Research Intent and workflow-selection authority, performs history-preserving profile revision through an exact accepted migration/impact preview, and reconstructs the same authority through a fresh Core composition.
- T03 renders catalog-driven project creation and adaptive workflow navigation. It preserves the full implemented workbench as supporting tools, but its focused tests exercise representative rather than exhaustive profile identities.
- T04 persists researcher-controlled stage heads and immutable history, distinguishes navigation authority from analytical jobs, provides exact supporting-tool return context, and permits selected earlier-stage revisits only for revisitable profiles. Its real SQLite and assembled-browser coverage is deep but intentionally not the fourteen-profile T05 matrix.
- Existing `tests/contracts/test_workflow_profile_contracts.py` validates the complete catalog structurally; `tests/service/test_workflow_progress.py` validates restart, migration, linear denial, and revisitable history with representative profiles; `tools/desktop_app_check.py` validates the built application using theory, systematic, and manuscript-review examples. No current test proves the complete creation-to-restart browser contract for every approved profile.

## Material acceptance rows

| Dimension | Observable closure | Planned proof |
|---|---|---|
| Exact catalog/test identity | Every case identifies reference ID/version, catalog hash, profile ID/version/revision/source hash, exact ordered stage keys/page contracts, cycle policy, expected output, and full-tool policy from the generated contract. | One immutable data-driven case inventory derived from the generated fixture; strict equality with the governed catalog and a mutation test that rejects stale reference/hash/order/output/tool-policy bytes. |
| Project creation | Each of the fourteen approved profile IDs can be selected at project creation; the accepted Core projection binds the selected profile and starts at that profile's first exact stage. | Real Core/SQLite table-driven test plus assembled production-renderer project-creation interaction for every profile. |
| Navigation order | Project Home, sidebar, and workflow context render the selected profile's complete primary order, including repeated page contracts as distinct stage keys, without inferring completion from a visit. | Playwright DOM assertions against exact stage labels/keys/order for all fourteen cases and route-visit no-mutation checks. |
| Supporting tools | All registered tools remain accessible for every profile; opening a non-primary implemented tool creates an exact server-issued return handoff to the current primary revision and return does not advance it. | Contract equality for all 33 tool IDs plus table-driven assembled browser open/return assertions and one-field stale-return denial. |
| Restart/durable authority | A new Core service composition and a reloaded production frame reconstruct the same project, selection/profile revision, current stage/pass, and immutable history. | Real SQLite close/reopen per profile and browser reload using the persisted projection; exact identity/hash equality before and after restart. |
| Profile revision | A human-accepted change preserves the prior selection/stage records, binds the exact migration/impact preview, and presents the target profile's ordered path/output after restart; substitution or stale acknowledgement leaves authority unchanged. | Representative cross-family real-SQLite revision plus table-driven catalog target assertions, history count/content checks, and stale/substituted denial. |
| Cycle semantics | `living-review`, `hermeneutic-inquiry`, and `manuscript-review-revision` append a selected earlier-stage pass without erasing history. Every other profile, including `critical-problematization`, remains linear; systematic review preserves exact reproducible order and ends at audit lineage. | Explicit catalog classification assertion, three positive revisit cases, eleven linear denials, preserved prior-pass checks, and exact systematic endpoint assertion. |
| Expected-output handoff | Creation preview and Project Home expose the exact nonempty expected output from the bound profile rather than generic or invented prose. | Exact text/accessible-name assertions for all fourteen generated cases and output-substitution rejection in the case inventory. |
| Accessibility/recovery | Each case exposes semantic navigation/current-step/output regions with unique accessible names, keyboard traversal, focus recovery, light/dark parity, and bounded loading/error/unimplemented-step behavior. | Table-driven Playwright keyboard/ARIA assertions plus existing full workflow/accessibility conformance; a delayed or malformed profile response clears stale context and fails closed. |
| Principal boundary | The same strict generated catalog and Core projections drive real SQLite persistence and the built renderer; tests do not maintain an independent application registry. | Catalog-hash equality across governed source, generated Python/TypeScript contract, Core response, and browser-observed metadata; built-frame run against production bundle. |
| Evidence truth | Commit-bound evidence names every profile/case and maps all three criteria to deterministic reports/checks. | Machine-readable T05 report with per-profile results and reference metadata, selected-check rationale, affected-profile selection, taskctl validation, and independent task/slice review. |

## Authority-bearing fields and failure boundaries

- Governed catalog: reference ID/version, workflow-catalog hash, page-contract hash, profile-catalog version, profile ID/version/revision/source hash, ordered stage key/page/order/optionality/checkpoint truth, cycle policy, expected outputs, registered tool IDs, and return policy.
- Project selection: project/root, Research Intent revision ID/hash, selection aggregate/revision/revision number/hash, exact profile reference, actor, predecessor selection, accepted migration, impact acknowledgement, and idempotency key.
- Stage progress: stage aggregate/revision/hash, current head, stage/page, pass, status, completion evidence, selected revisit source, displaced active-head compare-and-swap fields, supporting return identity, and immutable history.
- Failure cases: unknown/stale catalog identity; wrong stage order or repeated-page collapse; unsupported profile; profile/intent/selection substitution; failed or stale migration acknowledgement; delayed project response; missing/unimplemented route; stale supporting return; process/frame restart; linear revisit attempt; and absent/incorrect output or accessibility metadata.

## First tests before product code

1. Add a deterministic test/case generator that enumerates exactly fourteen cases from the generated portable catalog and fails on any governed source/reference/profile/order/output/cycle/tool-policy mismatch.
2. Add real SQLite table-driven tests that create and restart a project for every profile, compare exact selection/progress identity before and after restart, and prove all supporting-tool policy and expected-output metadata are retained.
3. Add cycle-family tests for the exact three revisitable IDs, all eleven linear denials, preserved pass history, and the systematic-review audit endpoint.
4. Extend the production built-frame Playwright checker with fourteen data-driven project-creation/navigation/output/support/reload cases, exact accessible semantics, and a machine-readable per-profile result map carrying the approved reference/catalog version and hashes.
5. Add hostile mutations for stale reference/hash, reordered/missing/repeated stages, changed expected output, reduced tool access, delayed project switch, and stale supporting return. Change product code only if one of these acceptance-bound tests exposes a real implementation defect.

## Deferred broader coverage

- T05 runs the affected desktop/service/data contract union because its purpose is exhaustive cross-layer verification; unrelated capability profiles remain deferred.
- CAP-03.S06 slice review will replay the combined T01-T05 integration/adversarial surface and decide whether an additional risk-cluster checkpoint is due.
- W1 exit remains responsible for the complete repository and Windows x64 matrix, packaging/install/upgrade, recovery/security, full accessibility/visual/performance suites, and release-authoritative smoke.

Adversarial preflight: the current implementation and prior T01-T04 findings were inspected directly. A separate preflight agent is not required because T05 adds verification first and changes no production authority unless a failing acceptance test exposes a bounded defect. Independent commit-bound task and slice review remain mandatory.

Mandatory gate discovered: none. Academic Minimal 1.5 already governs the required fourteen-profile behavior. Any test result that requires a new workflow identity, route, output, interaction, or authority will stop at the existing design/amendment boundary rather than being silently encoded in T05.
