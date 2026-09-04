# CAP-03.S06.T03 task-start acceptance closure

## Frozen authority

- Task: `CAP-03.S06.T03`
- Claim base: `3c434794e144e186afc21e53933263653fb3fbe0`
- Objective: render the selected governed workflow as numbered primary navigation, expose current/previous/next context and rationale, and retain a secondary complete inventory of currently functional tools.
- Dependencies: independently approved `CAP-03.S06.T02`, `CAP-01.S02.T01`, and `CAP-01.S02.T02`.
- Governing authority: W1 packet; CAP-03.S06 Section 9.3; CAP-03-D04; ADR-0026; `docs/architecture/workflow-profile-contracts.md`; generated Core workflow-catalog projection; Academic Minimal reference `RO-UI-ACADEMIC-MINIMAL-1.5` style-guide workflow-navigation region.
- Non-goals: no durable stage-state/checkpoint command or completion assertion, no analytical-job coupling, no stale/recalculation propagation, no new project migration, no activation of unimplemented future workspaces, and no governed-reference change. Those duties remain with T04, T05, later capability tasks, slice review, and W1 exit.

## Implemented baseline and predecessor facts

- The functional desktop currently has a flat eight-workspace button list. It neither consumes the selected workflow for shell navigation nor preserves primary context when a supporting workspace opens.
- T02 provides the shape-strict Core workflow-catalog projection and the current versioned Research Intent projection. Intent guidance values and selection authority are independently reviewed and hash-bound. The adversarial preflight found that the generated client does not yet bind the navigation-bearing catalog projection to the advertised approved catalog hash; T03 must close that prerequisite before rendering those values.
- ADR-0026 already defines exact portable stage-state and support-return identities, but T04 owns their durable persistence and commands. A route visit must not be relabeled as scholarly completion or checkpoint approval.
- The product currently implements only the functional workspaces exposed by `ApplicationRuntime`; the governed catalog also names future page contracts. T03 may show future primary stages as unavailable/upcoming context, but must not route to reference-only pages or claim that an unimplemented capability works.
- Current application-lock, project lifecycle, and application-settings focus boundaries are established behavior and must remain unchanged.

## Material acceptance rows

| Dimension | Observable closure | Planned proof |
|---|---|---|
| Catalog authenticity | Every registered-tool and navigation-bearing projection value is bound at the generated-client boundary to the approved catalog identity. A retained-valid-hash substitution cannot reach the shell. | First add failing substitutions for tool inventory, profile metadata, expected outputs, process form, and every stage field; then compare the exact decoded wire projection with a generator-derived approved projection identity. |
| Profile order | The primary rail is built from the exact selected Core profile, preserves stage order/rationale/optionality, and visibly identifies revisitable profiles. Switching to a different persisted current Intent profile replaces the order without a UI-owned workflow registry. Unsaved form selection never changes shell authority. | Pure model tests over at least systematic-review and theory-synthesis plus rendered shell tests; exact selected-profile lookup and missing-profile denial. |
| Stage semantics | Current, upcoming, completed, attention-required, blocked/stale, optional, and cyclical presentation states have distinct semantic labels and token-driven styling. Live T03 never infers completed/attention authority from a route visit; those states render only from an explicit authoritative input added for T04. | Model and DOM tests exercise every display state; a regression proves navigation alone does not mark a stage complete. |
| Context and movement | Every functional workspace retains a workflow context region naming the selected profile, exact current stage, position, rationale, previous stage, next stage, expected output, and the catalog's exact checkpoint state/rationale, including whether a route is not yet implemented. Primary navigation changes current context without asserting completion or a passed gate. | ApplicationRuntime interaction/model tests for current, prior/next, unavailable-stage denial, unknown checkpoint truth, expected output, focus, and announcements. |
| Supporting tools | One immutable implementation-capability map classifies each functional workspace relative to the selected profile, drives primary navigation, All tools, commands, availability, and return validation, and never creates an unregistered page-contract identity. Opening an out-of-sequence tool retains an exact in-memory return snapshot and shows one Return-to-current-step action. Distinct stage keys remain distinct when one page contract occurs twice. | Success test plus profile-relative primary/supporting fixture, manuscript-review-revision duplicate-page fixture, and substitutions of project ID, intent revision/hash, catalog hash, profile, stage key/page, and stale current-primary state; mismatch denies return and keeps context visible. |
| Failure/recovery | No project, no current Intent, closed/incompatible project, catalog/intent loading failure, missing profile, changed project/profile while supporting, reordered late responses, application lock, failed/successful Intent save, and unimplemented primary routes remain truthful and recoverable without fabricated progress. | Empty/loading/error/unavailable tests, request-generation project-A/project-B race, project close/replacement, lock clearing, persisted-save callback, and focus-preserving retry/return behavior. |
| Keyboard/screen reader | Ordered navigation is a labelled list of native buttons; current page uses `aria-current`; status text is not color-only; All tools uses native disclosure; focus is visible; actions and live announcements are keyboard operable at responsive widths and both themes. | Static semantic assertions, interaction tests, exact-reference UI gate, assembled-browser keyboard/focus checks, and light/dark responsive conformance. |
| Principal boundary | Packaged renderer consumes strict generated-client catalog/Intent responses, updates shell context after project or Intent change, and preserves local Core/Tauri denial behavior. | Built production frame workflow scenario plus configured Node 24 native Core/SQLite workflow scenario; no reference-only page is imported into product output. |
| Evidence truth | Task evidence binds exact candidate paths and maps each criterion to named tests. Full persisted progress, all-profile end-to-end, performance, packaging/platform, and Wave matrices stay explicitly deferred. | Criterion manifest, governed affected-path report, taskctl/backlog/site validation, and independent commit-bound review. |

## Authority-bearing navigation fields

- Project: project ID, canonical root, compatibility/access state, open state.
- Intent: intent ID, revision ID/number/content hash, current primary use case, accepted/draft status.
- Catalog/profile: governed reference ID/version, catalog version/hash, guidance version/hash, profile ID, process form, ordered stage key/order/page contract/rationale/optional flag.
- Primary context: project ID, Intent revision ID/hash, catalog hash, profile ID, exact stage key/page and position.
- Supporting return: the complete primary-context snapshot plus the supporting workspace identity. Any replacement of the project, Intent, catalog, profile, or current stage makes the return stale and must be denied/rebuilt rather than silently redirected.

## First tests before product code

1. Add model tests that fail against the current flat shell: two profiles produce different exact ordered rails; every display state has text semantics; a route visit cannot create completed authority.
2. Add generated-client tests that retain the valid advertised catalog hash while substituting the registered tool inventory and each navigation-bearing value; every substitution must be rejected before shell work begins.
3. Add a supporting-tool test that opens an out-of-sequence functional workspace, exposes one return action, classifies the same workspace differently by profile, preserves duplicate-page stage keys, and rejects a one-field-substituted or stale primary snapshot.
4. Add ApplicationRuntime semantic/interaction tests for the labelled ordered list, native All tools disclosure, current/previous/next rationale, expected output, unknown quality-gate truth, keyboard focus, responsive/theme classes, request races, loading/error/no-project truth, and no reference-only routing.
5. Extend the built-frame scenario to prove the assembled product changes its navigation only after persisted selected-project/Intent context changes and returns from a supporting tool without losing the primary step.

## Deferred broader coverage

- T04 owns durable `WorkflowStageState` persistence, completion evidence, human checkpoints, attention/stale causes, restart, handoff, and recalculation integration. T03 provides the rendering/input boundary but records no scholarly progress.
- T05 owns exhaustive fourteen-profile selection/navigation/supporting-tool/state/accessibility and expected-output handoff qualification.
- Slice review and W1 exit retain full failure, denial, recovery, security, accessibility, visual, performance, packaging, and release-authoritative Windows x64 qualification.

Adversarial preflight: completed by an independent agent because this high-risk change crosses generated client, shell navigation, focus/accessibility, supporting-return identity, and assembled-browser boundaries. It found the catalog-authentication prerequisite and the coherent-snapshot, canonical-route, initial-stage, race/invalidation, duplicate-page, and expected-output/quality-gate closure rows recorded above.

Mandatory gate discovered: none. The task restores the already approved Academic Minimal 1.5 workflow-navigation contract; any required experience change outside that reference will stop for governed design review.
