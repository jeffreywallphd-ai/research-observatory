# CAP-05.S04.T02 — durable source links and anchor inspection

Claim base: `780e1d8e79ad7136f9c362535e642adbfdeb5437` on
`codex/w2-implementation`, owned by `codex-w2-implementation`.
CAP-05.S04.T01 is DONE, independently approved and integrated into local main.
The approved W2 campaign remains active.

Authority: the backlog's three T02 criteria, S04 sections 4–9.2,
accepted ADR-0001/0013/0024/0029, existing protected source/anchor contracts,
and the inherited Reader in RO-UI-ACADEMIC-MINIMAL-1.9. LT01 changes only the
representative first-page target to 3.0 seconds; its fresh T01 proof remains
bound to its own candidate. This task introduces no model, resource tier,
framework change, new actor authority or overwrite of historical anchors.

| Material outcome or risk | Implementation boundary | Planned proof |
|---|---|---|
| Criterion 1: portable links after restart/relocation | Versioned opaque project, attachment, original/accepted revision and ordered anchor IDs; fresh resolution after explicit project open/unlock. No root, session, token, quote or cached source metadata in the link. | Strict Python/TypeScript value and URI cases; actual Native/Core retained anchors and shipping Reader after restart and confined relocation. |
| Criterion 1: distinguish multiple anchors | Bounded context window, numbered keyboard list and markers, exact code-point context highlight, validated rotated page geometry with visible fallback. | Mounted Reader cases for two anchors, Unicode, inert text, page/zoom, keyboard/focus, reflow, themes and geometry mismatch. |
| Criterion 1: missing/broken context | Authenticated canonical revision metadata and a real return to the selected source for review; no later-revision substitution or invented repair. | Actual retained-anchor resolution and broken-context provenance; mounted repair/return and separate unavailable/denied state. |
| Exact identity and current authority | Current source identity, project/session/human/Intent/privacy, original and accepted revision, anchor ID and inspect/derive rights at read and delivery. | Real SQLCipher/encrypted repository and private API substitution, changed rights, stale session and late-delivery cases; actual Native binding. |
| Linked revision replacement | A new link for the same original but a different normalized revision replaces the Reader session and its context, with or without a prior source handoff. | Mounted regression first fails on the stale revision, then verifies fresh exact revision metadata and both contexts; independent finding replay. |
| Allocation and physical settlement | Viewer-only resolver shares the scoped repository and cumulative protected-artifact allowance. Shared main allowance contains bounded retained context; issued unknown Native drain retains admission across unmount/retry. | Admission before protected reads; maximum-source accounting, context eviction, known/unknown settlement and decoder-generation regression cases. |
| Criterion 2: meaningful success/failure coverage | Tests precede product changes where practical. | Preserve first failing Core/Reader cases, then fresh affected candidate checks and one real vertical principal proof. |
| Criterion 3: compatibility, contracts, audit | Additive link value/route and fixed private resolver; reuse canonical anchor metadata/invalidation. Database/envelope/anchor formats stay unchanged. Diagnostics and persisted link projection carry no research text. | Schema drift/strict decoding, existing anchor compatibility, output-free invalidation/denial checks, affected type/architecture and package conformance. |
| Workflow continuity | Reader navigation/return preserves the selected Work/version and supporting workflow context; lock clears protected state and restart requires fresh authority. | Mounted journey and actual restart/relocation; no workflow completion or acceptance from inspection. |

Read-only independent preflight: incorporated the existing bounded retained-context
resolver, exact source/delivery fence, and structured Native terminal-versus-unknown
model. Ordinary nullable anchor IPC cannot prove physical settlement. At most two
contexts are visible; remaining selected anchors are opaque IDs. No whole accepted
IR is loaded merely to resolve a retained anchor.

First tests target two exact retained anchors, a later accepted head, substitution,
derive denial, broken context and resource admission. Broader unchanged profiles,
full history audits, parser/model runs and percentile benchmarks are deferred to
their required slice/checkpoint/Wave boundaries. No 8/16 GiB variant is run.

Primary guidance rechecked on 2026-10-09: [Web Annotation selectors](https://www.w3.org/TR/annotation-model/#selectors),
[target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html),
and [focus visibility](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html).
Equivalent list controls remain available when page regions overlap or are too
small for a useful on-page target. Source selectors remain exact immutable
revision selectors under the accepted repository contract.

Mandatory gate discovered: none. Task completion and W2 release remain pending.

Independent review identified omitted linked-revision session identity at candidate
`98f7fea87a88c359ea73d867e5472697ac2c45e6`. The first mounted regression preserved
the failure before the bounded correction. This refines criterion 1's exact-link
risk; it does not introduce a new scope or acceptance target.
