# CAP-04.S01.T02 — renderer review journey checkpoint

Increment from approved `1510e7be7a9dea4ad73931e3d47e6b0e8bdd6d85`.
Task remains IN_PROGRESS. No approval, scope or frozen-plan mutation.

Implements the approved ingestion route with native selected-file intake,
explicit local store/inspect rights, bounded saved-preview discovery, current
worker status, CSV column mapping, cross-page group corrections/exclusions,
raw/candidate/effective comparison and cancellation. Uses shared controls and
tokens. Core authenticates all routes, binds the current open project and
rechecks inspection rights. Discovery advances over inaccessible items without
returning their names or source values. Read-only/closed projects cannot mutate.

No canonical records or resolved works are fabricated. Source text is inert;
raw fields remain immutable. Mapping/decisions append exact-revision changes.
Old component responses cannot restore a navigated-away protected preview.
The generated client snapshots requests and validates bounded response identity.

## Advisory findings and acceptance closure

Read-only reviewer `w2_ux_plan_review` found three P2 issues in the uncommitted
renderer delta: automatic mappings appeared unmapped, returning to the first
record page discarded unsaved mappings, and dismissing inline cancellation lost
focus and lacked Escape behavior. These findings are retained, not a formal
candidate approval. Immediate causes: only explicit mappings were projected;
pagination reused initialization; dismissal removed the focused control.

Added focused regressions before remediation. The Core mapping test and built
UI test reproduced missing automatic targets. Remediation shares the parser's
target-name function with the review projection without changing normalization;
initialization runs only on reload/revision change; Keep/Escape restore focus.
Acceptance now explicitly includes unchanged mapping Apply, a single-column edit
preserving other fields, duplicate-header pagination retaining pending edits,
and keyboard dismissal in both themes. Permission denial and late response after
navigation are also exercised at their real Core/renderer boundaries.

## Selected proof and limits

- Focused Core discovery/status/cancel and mapping/review tests; parser
  characterization because its target lookup is now shared.
- Generated import-client contract tests, intake adapter and workspace rendering
  tests; affected type/lint/format, schema/architecture and inventory checks.
- Built renderer plus generated client plus authenticated Core, actual project,
  encrypted object port, parser/worker and protected draft repository. Synthetic
  55-row duplicate-header data proves cross-page mapping/corrections/exclusions,
  durable decisions, raw preservation, both themes, Tab/Enter/Escape focus,
  and late-response suppression. Native chooser/host are explicit doubles and
  the database is the existing plaintext test fixture, not DPAPI/SQLCipher proof.
- Narrow native allowlist regression: public list/status/cancel admitted, private
  routes remain denied. No full W1/profile replay.

Development mapping/keyboard/late-response journey and Core mapping regression
passed together (two tests, 7.983s). Inspection-denial discovery/status/cancel
passed separately. These observations are not exact-candidate qualification;
fresh selected checks and independent review follow the commit.

Remaining task work: native complete diagnostic report publication, duplicate/
count/coverage projection, scalable undo, explicit CSV delimiter support and
real native/100k/packaging qualification. CAP-04.S01.T03 owns canonical import
commit; CAP-04.S03 owns new Work/Version reconciliation.
