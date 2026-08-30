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

## R01 remediation

Independent review at `df41ee045a4816e53a92180f1df58fa6196e36f1`
returned `CHANGES_REQUESTED` in
`artifacts/evidence/governance-maintenance-review-site-task-drilldown-1.0.review.md`.
The remediation preserves the approved projection boundary and closes only the
four recorded findings:

1. support both repository-authored task-heading forms, reject duplicates, and
   require every one of the 337 authored tasks to have a non-empty,
   hash-bound plan projection;
2. project and validate the authoritative ordered `dependencies` inventory;
3. project and validate top-level task owner, branch, and base-commit claim
   fields; and
4. place the focused regression suite inside the existing governed Python
   quality scope.

The selected checks are the focused task-drill-down regression suite, the
affected planning-review regression suite, deterministic full-site validation,
the governed Python quality boundary, and `git diff --check`. Broader visual,
keyboard, and assistive-technology confirmation remains a disclosed manual
check because the in-app browser policy denied control of the local `file://`
surface. Product runtime and the protected W1.A04 witness remain outside scope.

## R02 remediation

The exact R02 review closed `PRTD-R01-F01` through `PRTD-R01-F04` and recorded
one new blocking validator finding, `PRTD-R02-F01`: parallel metadata markers
could remain truthful while reviewer-visible plan, dependency, or claim text was
falsified. The remediation adds one generic deterministic byte comparison of
the complete generated site, seeded only with the retained `generated_at`
value, and an adverse regression that alters all three visible surfaces while
leaving manifest values and `data-*` markers intact. The validator must reject
that tampered copy. This strengthens an existing check; it creates no new
controller, approval, task, or mandatory review step.
