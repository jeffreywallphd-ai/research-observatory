# Live and published planning review

Read only the section for the current review-site operation: navigation, feedback,
approval, generation or change control. Ordinary implementation does not require
this guide merely because a generated page exists. The site is a review surface;
backlog and Markdown plans remain canonical.

## Live review

Run `python tools/plan_review_server.py --repo .` and open
[the live review center](http://127.0.0.1:57003/) or
[W3](http://127.0.0.1:57003/waves/W3.html). The running server reads canonical
backlog YAML and selected capability/slice Markdown frontmatter. Stable Wave,
capability, slice, task, gate, correction and historical amendment/recovery
routes need no generated detail pages. Refresh or the visible-page periodic
refresh reads current bytes; malformed or changing sources show an error rather
than stale successful data. The API at `/api/review` and `/api/review/<ID>` is a
read-only display projection, separate from the product Core API.

The server binds only to `127.0.0.1`, accepts GET/HEAD, checks Host/Origin,
serves fixed assets, and exposes no arbitrary repository files or mutation.
Imported plan text is rendered inertly. Local owner/session/runtime fields are
not included in the structured ledger projection. Byte-identical display input
parsing may be reused in memory; no readiness, test, approval or review result
is cached. No Node build or static generator is needed to start the server.
Restart it after server-code or asset changes; those inputs are pinned for the
running instance and drift produces a bounded unavailable response.

Focused checks are `python -m unittest -v tests.foundation.test_plan_review_server
tests.foundation.test_workflow_guidance` and, with installed Chromium,
`python tests/foundation/planning_review_browser.py -v`. The explicit browser
check covers navigation, inert text, gate conditions, keyboard landmarks,
real periodic updates, focus/disclosure continuity and invalid-data recovery;
it is not part of unrelated foundation discovery.

Routine status/worksheet changes need no tracked HTML regeneration. Continue
normal backlog mutations and Markdown view checks. The static exporter below
remains the complete qualified publication route for explicit approval/evidence
snapshots, frozen-packet handoffs and static-renderer changes. Never substitute
a live HTTP response for approval, readiness or commit-bound evidence.

## Entry points and navigation

- `planning/review-site/index.html` - Wave packets and capability detail views.
- `planning/review-site/waves/WN.html` - the complete pre-Wave approval packet:
  every Wave-binding capability decision, inherited/future decisions as
  nonbinding context, ordered slice plan, review/testing cadence, progress,
  and exit/activation gate decision.
- `planning/review-site/CAP-XX/index.html` - decision register and approval surface.
- `planning/review-site/CAP-XX/CAP-XX.SYY.html` - individual slice plan.
- `planning/review-site/enablers/index.html` - ECR/amendment register.
- `planning/review-site/enablers/ECR-NNNN.html` - proposal, immutable approval,
  base/amendment authority, execution state, alternatives, and resume condition.

The left navigation is a two-tab planning switcher on every page:

- **Waves** is the default on the review-center and wave pages. It exposes the
  primary execution sequence and each wave's exit/activation gate.
- **Capabilities** is the default while reviewing a capability or one of its
  ordered slices. It preserves the product-outcome view without obscuring wave
  placement.

The tabs support pointer activation plus Left/Right, Home, and End keyboard
navigation. Switching tabs changes only the navigation view; it never changes
approval or backlog state.

Use the live server for current inspection. For a qualified static publication,
use `python tools/planctl.py --repo . wave review WN` to regenerate and print
the directly openable exported Wave link.

In handoffs, present the exact generated destination as a directly openable link
supported by the active client, plus its repository-relative path. In Codex,
prefer absolute local Markdown links. Retain a literal browser `file://` URI
only where useful and permitted; CLI URI output need not be copied into an
unsupported link format. Link the relevant capability/slice/prerequisite packets,
not every page. Gate decisions also require the
[decision-complete handoff](project-automation-guide.md#31-decision-complete-stopped-gate-handoff).

Capability aliases and descriptive slice labels are the default presentation.
Canonical `CAP-XX` and `CAP-XX.SYY` values remain visible because they are
immutable evidence keys; slice numbers also preserve the declared sequence.

## Decision controls

Every decision contains:

- the documented candidate options;
- the preselected best-in-class recommendation;
- an `Other` option;
- a brief Other-description input, visible and required only when Other is selected; and
- a separate detailed feedback/rationale textarea.

The Other brief description should name the proposed direction concisely. The detailed rationale should explain why it is preferable, constraints, required evidence, and any approval conditions.

## Feedback format

The site exports `capability-decision-feedback` schema `1.1`.

A documented choice resembles:

```json
{
  "id": "CAP-XX-D01",
  "selected_option": "A documented candidate",
  "other_option": null,
  "accepted_recommendation": false,
  "rationale": "Detailed reason for the override"
}
```

An Other choice resembles:

```json
{
  "id": "CAP-XX-D01",
  "selected_option": "__OTHER__",
  "other_option": "Use a hybrid local-first index with hosted overflow",
  "accepted_recommendation": false,
  "rationale": "Detailed constraints, tradeoffs, and validation conditions"
}
```

Other requires both `other_option` and rationale. The brief description is limited by the interface; detailed reasoning belongs in rationale.

## Applying feedback

The current feedback importer and `adopt-recommendations` operate on the entire
capability. Do not use them to clear pending future decisions in a rolling-wave
(`initiation-assessment-2.0`) packet. For a current-Wave-only override while future
decisions remain provisional, edit only the unapproved binding decisions in the
canonical capability plan: record the selected candidate (or described Other),
rationale and status, and remove only their resolved blocker IDs. Preserve future
and already binding decision bytes; keep global completion pending if appropriate.
Regenerate `wave review WN` and validate the complete upcoming Wave before approval.
This supported planning-edit route adds no execution authority or approval gate.

Use the whole-capability importer below only when intentionally resolving the
complete still-mutable decision set; it is not a scoped rolling-wave editor.

```bash
python tools/planctl.py --repo . apply-feedback CAP-XX <downloaded-json>
```

For Other, `planctl`:

1. validates schema, plan hash, complete decision coverage, description, and rationale;
2. creates the canonical candidate `Other: <brief description>` if not already present;
3. records that candidate as `selected_option` and marks the decision accepted;
4. archives the original JSON, preserving detailed rationale;
5. regenerates the review site; and
6. leaves capability and slice approval pending.

Feedback is never implicit approval.

## Approval

Before approval, reviewers confirm that the contributing capability plans show
the applicable initiation assessment: current implementation baseline, Vision
and best-practice fit, earlier-Wave changes, and necessary redesign/support work.
Unapproved planning has no 15% cap. Review the final upcoming-Wave atomic-task
estimate and planned refactoring allocations; distant contributions remain
provisional. Deterministic validation checks coverage, identities, units and
duplicates; reviewers assess product fit and required architectural authority.
Approval freezes the scope and estimate. Subsequent supplemental refactoring
uses the shared [locked-Wave budget](../../planning/README.md#locked-wave-refactoring-budget),
including earlier-Wave work. This is part of the existing packet/review workflow,
not another approval; historical immutable approvals remain unchanged.

After all capability feedback has been applied, approve the complete Wave packet:

```bash
python tools/planctl.py --repo . wave approve WN --by "<reviewer>" --commit <git-sha>
```

Approval applies once to every decision-complete capability contribution and
every ordered slice plan in `WN` at the same immutable commit. A subset cannot
start execution. Future-Wave plans remain outside the approval. Historical
approvals remain immutable evidence. The approval command is shown only for a
genuinely pending, uninterrupted Wave. An approved Wave cannot be reapproved;
its generated page shows immutable authority and links any interrupting ECR.

## Generation and validation

```bash
python tools/plan_review_site.py --repo .
python tools/plan_review_check.py --repo . --report artifacts/planning-review-site-validation.json
node --check planning/review-site/assets/review.js
```

The validator must confirm page/plan hashes, decision IDs, internal links, and the presence of Other controls on every capability decision.

## Change control

Do not edit generated decision cards by hand. Change `tools/plan_review_site.py`, canonical plans, or shared site assets, regenerate, and validate. A site generated from stale plan hashes cannot authorize feedback or approval.
