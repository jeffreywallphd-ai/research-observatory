# Governance maintenance increment: dynamic planning-review task drill-down

- **Predecessor commit:** `3e05ca07fc669a8d45cf3cc843ea8387d7757d0d`
- **Authority:** User request in the active repository session on 2026-08-29.
- **Risk tier:** High. The generated planning-review site is a review and evidence surface.
- **Quiescent boundary:** W1 task `CAP-03.S04.T01` remains claimed but product implementation is paused. This increment changes no product runtime, task state, approval state, or execution authority.

## Intended projection delta

1. Generate one task page for every task derived from `planning/backlog.yaml` and its authored slice plan.
2. Link capability pages to slice pages and slice pages to task pages, retaining immutable numeric identities.
3. Render each Wave's capability, slice, and task hierarchy as nested, keyboard-native collapsible cards.
4. Display an optional task-start worksheet when the exact task-keyed worksheet exists at `artifacts/evidence/<TASK-ID>.task-start.md`; absence remains non-blocking.
5. Extend the generated manifest and validator so task and Wave inventories, pages, links, and optional worksheet hashes must match repository data exactly.

## Invariants that must not change

- The backlog and approved plans remain authoritative; generated HTML is a projection only.
- No Wave, capability, slice, or task identity is hard-coded into the generator.
- The maintenance increment creates no task state, approval gate, controller, or mandatory worksheet.
- Existing append-only task review history remains truthful and commit-bound.
- The protected untracked witness `artifacts/evidence/W1.A04.B00.json` is outside scope and must remain byte-identical.

## Verification and integration boundary

- Focused generator and validator tests must prove dynamic task-page inventory, nested Wave hierarchy, task navigation, and optional worksheet projection.
- The full generated site must pass `tools/plan_review_check.py` and repository planning checks plausibly affected by the changed surface.
- A browser-level keyboard/navigation inspection must be attempted. If the local
  browser security policy denies control of the generated `file://` surface,
  record that limitation truthfully, retain the native-details/HTML/link
  validation, and leave visual confirmation as an explicit manual check rather
  than bypassing the browser policy.
- Because this changes an evidence/control surface, an independent reviewer must approve the exact candidate commit before integration or W1 product work resumes.
